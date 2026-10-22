use serde::Deserialize;
use std::collections::BTreeMap;

#[derive(Deserialize)]
pub struct Schema {
    pub dataset: String,
    pub columns: BTreeMap<String, Column>,
    pub rules: BTreeMap<String, String>,
}

#[derive(Deserialize)]
pub struct Column {
    #[serde(rename = "type")]
    pub kind: String,
    #[serde(default)]
    pub required: bool,
    pub min: Option<String>,
    pub max: Option<String>,
    pub warn_above: Option<String>,
    pub unit: Option<String>,
    pub domain: Option<String>,
    pub pattern: Option<String>,
}

pub type Mappings = BTreeMap<String, BTreeMap<String, Vec<String>>>;
