mod domain;
mod pipeline;
mod profile;
mod schema;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyfunction]
fn process_dataset(
    py: Python<'_>,
    input: String,
    output: String,
    schema: String,
    codes: String,
    today: String,
) -> PyResult<String> {
    py.detach(|| pipeline::process(&input, &output, &schema, &codes, &today))
        .map_err(|error| PyValueError::new_err(error.to_string()))
}

#[pymodule]
fn adapter_engine(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(process_dataset, module)?)?;
    Ok(())
}
