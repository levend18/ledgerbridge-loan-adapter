use crate::domain::{code_key, detect_unit, normalize_date, normalize_number, normalize_rate};
use crate::profile::Stats;
use crate::schema::{Mappings, Schema};
use regex::Regex;
use rust_decimal::Decimal;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::fs::File;
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::str::FromStr;

type Row = BTreeMap<String, String>;

#[derive(thiserror::Error, Debug)]
pub enum EngineError {
    #[error("{0}")]
    Input(String),
    #[error(transparent)]
    Io(#[from] std::io::Error),
}

#[derive(Default)]
struct Issues {
    details: Vec<Value>,
    counts: BTreeMap<String, u64>,
}

struct IssueInput<'a> {
    dataset: &'a str,
    row: usize,
    key: &'a str,
    column: &'a str,
    rule: &'a str,
    severity: &'a str,
    raw: &'a str,
    normalized: &'a str,
}
impl Issues {
    fn add(&mut self, v: IssueInput<'_>) {
        *self
            .counts
            .entry(format!("{}:{}", v.severity, v.rule))
            .or_default() += 1;
        if self.details.len() < 1000 {
            self.details
                .push(json!({"dataset":v.dataset,"row_number":v.row,"key":v.key,
                "column":v.column,"rule_id":v.rule,"severity":v.severity,
                "raw_value":v.raw,"normalized_value":v.normalized,"message":v.rule}));
        }
    }
}
macro_rules! issue {
    ($issues:expr,$dataset:expr,$row:expr,$key:expr,$column:expr,$rule:expr,$severity:expr,$raw:expr,$normalized:expr) => {
        $issues.add(IssueInput {
            dataset: $dataset,
            row: $row,
            key: $key,
            column: $column,
            rule: $rule,
            severity: $severity,
            raw: $raw,
            normalized: $normalized,
        })
    };
}

fn rows(
    path: &str,
    schema: &Schema,
) -> Result<Box<dyn Iterator<Item = Result<Row, EngineError>>>, EngineError> {
    let file = File::open(path)?;
    if path.ends_with(".csv") {
        let mut reader = csv::ReaderBuilder::new().delimiter(b';').from_reader(file);
        let headers = reader
            .headers()
            .map_err(|e| EngineError::Input(e.to_string()))?
            .clone();
        let mut names: Vec<_> = headers.iter().collect();
        names.sort_unstable();
        if names
            != schema
                .columns
                .keys()
                .map(String::as_str)
                .collect::<Vec<_>>()
        {
            return Err(EngineError::Input("SCHEMA_MISMATCH: CSV headers".into()));
        }
        Ok(Box::new(reader.into_records().map(move |record| {
            record
                .map(|r| {
                    headers
                        .iter()
                        .zip(r.iter())
                        .map(|(k, v)| (k.to_owned(), v.to_owned()))
                        .collect()
                })
                .map_err(|e| EngineError::Input(format!("SCHEMA_MISMATCH: {e}")))
        })))
    } else {
        Ok(Box::new(BufReader::new(file).lines().map(|line| {
            serde_json::from_str::<Row>(&line?)
                .map_err(|e| EngineError::Input(format!("SCHEMA_MISMATCH: {e}")))
        })))
    }
}

fn escape(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('\t', "\\t")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}

pub fn process(
    input: &str,
    output: &str,
    schema_text: &str,
    codes_text: &str,
    today: &str,
) -> Result<String, EngineError> {
    let schema: Schema =
        serde_yaml::from_str(schema_text).map_err(|e| EngineError::Input(e.to_string()))?;
    let mappings: Mappings =
        serde_yaml::from_str(codes_text).map_err(|e| EngineError::Input(e.to_string()))?;
    let mut dictionary = BTreeMap::new();
    for (domain, values) in mappings {
        for (canonical, variants) in values {
            for variant in variants
                .into_iter()
                .chain(std::iter::once(canonical.clone()))
            {
                dictionary.insert((domain.clone(), code_key(&variant)), canonical.clone());
            }
        }
    }
    let mut stream = rows(input, &schema)?;
    let sample: Vec<Row> = stream.by_ref().take(10_000).collect::<Result<_, _>>()?;
    let mut units = BTreeMap::new();
    let mut patterns = BTreeMap::new();
    let mut day_first = BTreeMap::new();
    let mut decimal_separator = BTreeMap::new();
    let mut issues = Issues::default();
    for (name, column) in &schema.columns {
        let evidence: std::collections::BTreeSet<_> = sample
            .iter()
            .filter_map(|r| r.get(name))
            .filter_map(|v| {
                let index = v.rfind([',', '.'])?;
                let tail = v[index + 1..].trim_end_matches("TL").trim();
                if (v.contains(',') && v.contains('.')) || tail.len() == 2 {
                    Some(v.as_bytes()[index] as char)
                } else {
                    None
                }
            })
            .collect();
        decimal_separator.insert(
            name.clone(),
            if evidence.len() == 1 {
                evidence.first().copied()
            } else {
                None
            },
        );
        if let Some(pattern) = &column.pattern {
            patterns.insert(
                name.clone(),
                Regex::new(pattern).map_err(|e| EngineError::Input(e.to_string()))?,
            );
        }
        if column.kind == "rate" {
            let values: Vec<_> = sample
                .iter()
                .filter_map(|r| r.get(name))
                .filter(|v| !v.contains('%') && !v.contains("bps"))
                .filter_map(|v| normalize_number(v).ok())
                .collect();
            let fallback = column.unit.as_deref().unwrap_or("fraction");
            let unit = detect_unit(&values, fallback);
            if unit != fallback {
                issue!(
                    issues,
                    &schema.dataset,
                    0,
                    "",
                    name,
                    "UNIT_MISMATCH",
                    "WARNING",
                    fallback,
                    &unit
                );
            }
            units.insert(name.clone(), unit);
        }
        day_first.insert(
            name.clone(),
            sample.iter().filter_map(|r| r.get(name)).any(|v| {
                v.contains('/')
                    && v.split('/')
                        .next()
                        .and_then(|x| x.parse::<u32>().ok())
                        .is_some_and(|n| n > 12 && n <= 31)
            }),
        );
    }
    let mut profiles: BTreeMap<String, Stats> = schema
        .columns
        .keys()
        .map(|k| (k.clone(), Stats::default()))
        .collect();
    let mut writer = BufWriter::new(File::create(output)?);
    let mut count = 0usize;
    let mut written = 0usize;
    for record in sample.into_iter().map(Ok).chain(stream) {
        let raw = record?;
        count += 1;
        let row_number = count + 1;
        if raw.keys().ne(schema.columns.keys()) {
            return Err(EngineError::Input(
                "SCHEMA_MISMATCH: unexpected columns".into(),
            ));
        }
        let key = raw
            .get("loan_account_number")
            .map(String::as_str)
            .unwrap_or("");
        let mut normalized: BTreeMap<String, Option<String>> = BTreeMap::new();
        let mut invalid = false;
        for (name, column) in &schema.columns {
            let value = raw[name].trim();
            if value.is_empty() {
                if column.required {
                    invalid = true;
                    issue!(
                        issues,
                        &schema.dataset,
                        row_number,
                        key,
                        name,
                        "REQUIRED",
                        "ERROR",
                        value,
                        ""
                    );
                }
                normalized.insert(name.clone(), None);
                continue;
            }
            let result = match column.kind.as_str() {
                "date" => normalize_date(value),
                "money" => {
                    let mut numeric = value.to_owned();
                    if value.matches([',', '.']).count() == 1
                        && value
                            .rsplit([',', '.'])
                            .next()
                            .is_some_and(|v| v.len() == 3)
                    {
                        if let Some(separator) = decimal_separator[name] {
                            if !value.contains(separator) {
                                numeric = value.replace([',', '.'], "");
                            }
                        }
                    }
                    normalize_number(&numeric).map(|v| v.normalize().to_string())
                }
                "int" => value
                    .parse::<i64>()
                    .map(|v| v.to_string())
                    .map_err(|_| "INVALID_INTEGER".into()),
                "rate" => normalize_rate(value, &units[name]).map(|v| v.normalize().to_string()),
                "code" => dictionary
                    .get(&(column.domain.clone().unwrap_or_default(), code_key(value)))
                    .cloned()
                    .ok_or("UNKNOWN_CODE".into()),
                _ => Ok(value.to_owned()),
            };
            let converted = match result {
                Ok(v) => v,
                Err(rule) => {
                    invalid = true;
                    issue!(
                        issues,
                        &schema.dataset,
                        row_number,
                        key,
                        name,
                        &rule,
                        "ERROR",
                        value,
                        ""
                    );
                    normalized.insert(name.clone(), None);
                    continue;
                }
            };
            if let Some(pattern) = patterns.get(name) {
                if !pattern.is_match(&converted) {
                    invalid = true;
                    issue!(
                        issues,
                        &schema.dataset,
                        row_number,
                        key,
                        name,
                        "INVALID_PATTERN",
                        "ERROR",
                        value,
                        &converted
                    );
                }
            }
            if ["money", "int", "rate"].contains(&column.kind.as_str()) {
                let n =
                    Decimal::from_str(&converted).map_err(|e| EngineError::Input(e.to_string()))?;
                let low = column.min.as_ref().and_then(|v| Decimal::from_str(v).ok());
                let high = column.max.as_ref().and_then(|v| Decimal::from_str(v).ok());
                if low.is_some_and(|v| n < v) || high.is_some_and(|v| n > v) {
                    invalid = true;
                    issue!(
                        issues,
                        &schema.dataset,
                        row_number,
                        key,
                        name,
                        "OUT_OF_RANGE",
                        "ERROR",
                        value,
                        &converted
                    );
                }
                if column
                    .warn_above
                    .as_ref()
                    .and_then(|v| Decimal::from_str(v).ok())
                    .is_some_and(|v| n > v)
                {
                    issue!(
                        issues,
                        &schema.dataset,
                        row_number,
                        key,
                        name,
                        "RATE_IMPLAUSIBLE",
                        "WARNING",
                        value,
                        &converted
                    );
                }
                if column.kind == "rate"
                    && units[name] != "fraction"
                    && !value.contains('%')
                    && !value.contains("bps")
                    && normalize_number(value).is_ok_and(|v| v > Decimal::ZERO && v <= Decimal::ONE)
                {
                    issue!(
                        issues,
                        &schema.dataset,
                        row_number,
                        key,
                        name,
                        "UNIT_AMBIGUOUS_VALUE",
                        "WARNING",
                        value,
                        &converted
                    );
                }
                if column.kind == "money"
                    && decimal_separator[name].is_none()
                    && value.matches([',', '.']).count() == 1
                    && value
                        .rsplit([',', '.'])
                        .next()
                        .is_some_and(|v| v.len() == 3)
                {
                    issue!(
                        issues,
                        &schema.dataset,
                        row_number,
                        key,
                        name,
                        "AMBIGUOUS_NUMBER",
                        "WARNING",
                        value,
                        &converted
                    );
                }
            }
            if column.kind == "date" && value.contains('/') && !day_first[name] {
                let first = value.split('/').next().and_then(|v| v.parse::<u32>().ok());
                if first.is_some_and(|v| v <= 12) {
                    issue!(
                        issues,
                        &schema.dataset,
                        row_number,
                        key,
                        name,
                        "AMBIGUOUS_DATE",
                        "WARNING",
                        value,
                        &converted
                    );
                }
            }
            if value != converted {
                issue!(
                    issues,
                    &schema.dataset,
                    row_number,
                    key,
                    name,
                    "NORMALIZED",
                    "CORRECTED",
                    value,
                    &converted
                );
            }
            normalized.insert(name.clone(), Some(converted));
        }
        let value = |name: &str| normalized.get(name).and_then(|v| v.as_deref());
        let number = |name: &str| value(name).and_then(|v| Decimal::from_str(v).ok());
        let mut violations = Vec::new();
        if let (Some(start), Some(end)) = (value("loan_start_date"), value("final_maturity_date")) {
            if end < start {
                violations.push(("MATURITY_AFTER_START", "final_maturity_date"));
            }
        }
        if let (Some(paid), Some(outstanding), Some(total)) = (
            number("paid_installment_count"),
            number("outstanding_installment_count"),
            number("total_installment_count"),
        ) {
            if paid + outstanding != total {
                violations.push(("INSTALLMENT_COUNT_SUM", "total_installment_count"));
            }
            if total == Decimal::ZERO {
                violations.push(("ZERO_INSTALLMENT_COUNT", "total_installment_count"));
            }
        }
        if let (Some(original), Some(outstanding)) = (
            number("original_loan_amount"),
            number("outstanding_principal_balance"),
        ) {
            if outstanding > original {
                violations.push(("OUTSTANDING_LE_ORIGINAL", "outstanding_principal_balance"));
            }
        }
        let closed = value("installment_status") == Some("CLOSED");
        if closed && value("actual_payment_date").is_none() {
            violations.push(("CLOSED_WITHOUT_PAYMENT", "actual_payment_date"));
        }
        if value("actual_payment_date").is_some_and(|date| date > today) {
            violations.push(("FUTURE_PAYMENT", "actual_payment_date"));
        }
        let components: Option<Vec<_>> = [
            "principal_component",
            "interest_component",
            "kkdf_component",
            "bsmv_component",
        ]
        .iter()
        .map(|name| number(name))
        .collect();
        if let (Some(parts), Some(amount)) = (components, number("installment_amount")) {
            if (parts.into_iter().sum::<Decimal>() - amount).abs() > Decimal::new(1, 2) {
                violations.push(("INSTALLMENT_COMPONENT_SUM", "installment_amount"));
            }
        }
        for (rule, column) in violations {
            if let Some(severity) = schema.rules.get(rule) {
                invalid |= severity == "ERROR";
                issue!(
                    issues,
                    &schema.dataset,
                    row_number,
                    key,
                    column,
                    rule,
                    severity,
                    raw.get(column).map(String::as_str).unwrap_or(""),
                    value(column).unwrap_or("")
                );
            }
        }
        if closed && schema.rules.contains_key("CLOSED_REMAINING") {
            for name in [
                "remaining_principal",
                "remaining_interest",
                "remaining_kkdf",
                "remaining_bsmv",
            ] {
                if normalized
                    .get(name)
                    .and_then(|v| v.as_deref())
                    .and_then(|v| Decimal::from_str(v).ok())
                    .is_some_and(|v| v != Decimal::ZERO)
                {
                    issue!(
                        issues,
                        &schema.dataset,
                        row_number,
                        key,
                        name,
                        "CLOSED_REMAINING",
                        "CORRECTED",
                        &raw[name],
                        "0"
                    );
                    normalized.insert(name.into(), Some("0".into()));
                }
            }
        }
        if invalid {
            continue;
        }
        written += 1;
        write!(writer, "{row_number}")?;
        for (name, column) in &schema.columns {
            let val = normalized[name].as_deref();
            profiles
                .get_mut(name)
                .expect("initialized profile")
                .add(val, &column.kind);
            write!(writer, "\t{}", val.map(escape).unwrap_or("\\N".into()))?;
        }
        writeln!(writer)?;
    }
    writer.flush()?;
    let stats: BTreeMap<_, _> = profiles
        .iter()
        .map(|(name, stats)| (name, stats.finish(&schema.columns[name].kind)))
        .collect();
    Ok(json!({"row_count":count,"written_count":written,"columns":schema.columns.keys().collect::<Vec<_>>(),
        "issues":issues.details,"counts":issues.counts,"profiles":stats,"unit_decisions":units}).to_string())
}
