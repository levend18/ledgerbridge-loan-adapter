use chrono::{Datelike, NaiveDate};
use rust_decimal::Decimal;
use std::str::FromStr;

pub fn normalize_date(raw: &str) -> Result<String, String> {
    let value = raw.trim().split('T').next().unwrap_or(raw);
    for format in ["%Y%m%d", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"] {
        if let Ok(date) = NaiveDate::parse_from_str(value, format) {
            if (1900..=2100).contains(&date.year()) {
                return Ok(date.format("%Y-%m-%d").to_string());
            }
        }
    }
    Err("INVALID_DATE".into())
}

pub fn normalize_number(raw: &str) -> Result<Decimal, String> {
    let value = raw
        .trim()
        .replace([' ', '\u{a0}', '₺'], "")
        .replace("TL", "");
    let last = value.rfind([',', '.']);
    let normalized = if let Some(index) = last {
        let left = value[..index].replace([',', '.'], "");
        format!("{}.{}", left, &value[index + 1..])
    } else {
        value
    };
    Decimal::from_str(&normalized).map_err(|_| "INVALID_NUMBER".into())
}

pub fn normalize_rate(raw: &str, unit: &str) -> Result<Decimal, String> {
    let value = raw.trim();
    let (number, divisor) = if let Some(number) = value.strip_suffix('%') {
        (number, 100)
    } else if let Some(number) = value.strip_suffix("bps") {
        (number, 10000)
    } else {
        (
            value,
            match unit {
                "percent" => 100,
                "bps" => 10000,
                _ => 1,
            },
        )
    };
    Ok(normalize_number(number)? / Decimal::from(divisor))
}

pub fn code_key(raw: &str) -> String {
    raw.trim()
        .chars()
        .map(|ch| match ch {
            'İ' | 'I' | 'ı' => 'i',
            'Ç' | 'ç' => 'c',
            'Ğ' | 'ğ' => 'g',
            'Ö' | 'ö' => 'o',
            'Ş' | 'ş' => 's',
            'Ü' | 'ü' => 'u',
            other => other.to_ascii_lowercase(),
        })
        .collect()
}

pub fn detect_unit(values: &[Decimal], fallback: &str) -> String {
    let nonzero: Vec<_> = values.iter().filter(|v| **v > Decimal::ZERO).collect();
    if nonzero.is_empty() {
        return fallback.into();
    }
    if nonzero.iter().all(|v| **v <= Decimal::ONE) {
        return "fraction".into();
    }
    if nonzero.iter().filter(|v| ***v > Decimal::from(100)).count() * 2 > nonzero.len() {
        return "bps".into();
    }
    "percent".into()
}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    #[test]
    fn normalizes_contract_examples() {
        for date in [
            "20240115",
            "15.01.2024",
            "2024-01-15",
            "15/01/2024",
            "2024-01-15T00:00:00",
        ] {
            assert_eq!(normalize_date(date).unwrap(), "2024-01-15");
        }
        assert!(normalize_date("30.02.2024").is_err());
        assert!(normalize_date("18000101").is_err());
        for number in ["1.234,56", "1,234.56", "1234.56", "1 234,56 TL"] {
            assert_eq!(
                normalize_number(number).unwrap(),
                Decimal::from_str("1234.56").unwrap()
            );
        }
        for rate in ["18.5%", "1850 bps", "18.5"] {
            assert_eq!(
                normalize_rate(rate, "percent").unwrap(),
                Decimal::from_str("0.185").unwrap()
            );
        }
        assert_eq!(code_key(" KAPALI "), code_key("Kapalı"));
        assert_eq!(code_key("AÇIK"), "acik");
    }

    proptest! {
        #[test]
        fn dates_round_trip(year in 1900i32..2101, month in 1u32..13, day in 1u32..29) {
            let date = NaiveDate::from_ymd_opt(year,month,day).unwrap();
            for format in ["%Y%m%d","%d.%m.%Y","%d/%m/%Y","%Y/%m/%d"] {
                prop_assert_eq!(normalize_date(&date.format(format).to_string()).unwrap(),date.to_string());
            }
        }
        #[test]
        fn explicit_units_override_column_unit(bps in 0i64..20001) {
            prop_assert_eq!(normalize_rate(&format!("{bps} bps"),"percent").unwrap(),Decimal::new(bps,4));
        }
    }
}
