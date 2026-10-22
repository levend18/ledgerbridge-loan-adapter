use crate::domain::normalize_number;
use rust_decimal::prelude::ToPrimitive;
use serde_json::{json, Value};
use std::collections::BTreeMap;

#[derive(Default)]
pub struct Stats {
    total: u64,
    count: u64,
    mean: f64,
    m2: f64,
    min: Option<f64>,
    max: Option<f64>,
    first: Option<String>,
    last: Option<String>,
    categories: BTreeMap<String, u64>,
    high: bool,
}

impl Stats {
    pub fn add(&mut self, value: Option<&str>, kind: &str) {
        self.total += 1;
        let Some(value) = value else {
            return;
        };
        self.count += 1;
        if ["int", "money", "rate"].contains(&kind) {
            if let Ok(number) = normalize_number(value) {
                if let Some(x) = number.to_f64() {
                    let delta = x - self.mean;
                    self.mean += delta / self.count as f64;
                    self.m2 += delta * (x - self.mean);
                    self.min = Some(self.min.map_or(x, |old| old.min(x)));
                    self.max = Some(self.max.map_or(x, |old| old.max(x)));
                }
            }
        } else if kind == "date" {
            if self.first.as_ref().is_none_or(|old| value < old.as_str()) {
                self.first = Some(value.into());
            }
            if self.last.as_ref().is_none_or(|old| value > old.as_str()) {
                self.last = Some(value.into());
            }
        } else if !self.high {
            if self.categories.contains_key(value) || self.categories.len() < 1000 {
                *self.categories.entry(value.into()).or_default() += 1;
            } else {
                self.high = true;
                self.categories.clear();
            }
        }
    }

    pub fn finish(&self, kind: &str) -> Value {
        let mut output = json!({"count":self.count,"null_count":self.total-self.count,
            "null_ratio": if self.total==0 {0.0} else {(self.total-self.count) as f64/self.total as f64}});
        if ["int", "money", "rate"].contains(&kind) {
            output["min"] = json!(self.min);
            output["max"] = json!(self.max);
            output["mean"] = if self.count > 0 {
                json!(self.mean)
            } else {
                Value::Null
            };
            output["stddev"] = if self.count > 1 {
                json!((self.m2 / (self.count - 1) as f64).sqrt())
            } else {
                Value::Null
            };
            output["precision"] = json!("f64");
        } else if kind == "date" {
            output["min"] = json!(self.first);
            output["max"] = json!(self.last);
        } else {
            output["high_cardinality"] = json!(self.high);
            output["distinct_count"] = if self.high {
                Value::Null
            } else {
                json!(self.categories.len())
            };
            let mut categories: Vec<_> = self.categories.iter().collect();
            categories.sort_by(|a, b| b.1.cmp(a.1).then(a.0.cmp(b.0)));
            output["most_frequent"] = json!(categories.first().map(|p| p.0));
            output["top"] = json!(categories
                .iter()
                .take(10)
                .map(|(v, n)| json!({"value":v,"count":n}))
                .collect::<Vec<_>>());
        }
        output
    }
}
