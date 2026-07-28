use pyo3::exceptions::{PyFileNotFoundError, PyIOError};
use pyo3::prelude::*;
use std::fs;
use std::path::{Path, PathBuf};

fn visit_dirs(root: &Path, dir: &Path, files: &mut Vec<String>) -> std::io::Result<()> {
    let metadata = fs::symlink_metadata(dir)?;
    if metadata.file_type().is_symlink() {
        return Ok(());
    }
    let canonical_dir = fs::canonicalize(dir)?;
    if !canonical_dir.starts_with(root) {
        return Ok(());
    }
    if dir.is_dir() {
        let mut entries: Vec<PathBuf> = fs::read_dir(dir)?
            .map(|entry| entry.map(|item| item.path()))
            .collect::<Result<Vec<_>, _>>()?;
        entries.sort();

        for path in entries {
            let file_type = fs::symlink_metadata(&path)?.file_type();
            if file_type.is_symlink() {
                continue;
            }
            if file_type.is_dir() {
                visit_dirs(root, &path, files)?;
            } else if file_type.is_file() && path.extension().is_some_and(|ext| ext == "md") {
                files.push(path.to_string_lossy().into_owned());
            }
        }
    }
    Ok(())
}

#[pyfunction]
fn scan_vault_fast(path: String) -> PyResult<Vec<String>> {
    let dir_path = Path::new(&path);
    if !dir_path.exists() {
        return Err(PyFileNotFoundError::new_err(
            "Vault directory does not exist",
        ));
    }
    if !dir_path.is_dir() {
        return Err(PyIOError::new_err("Vault path is not a directory"));
    }

    let canonical_root = fs::canonicalize(dir_path)
        .map_err(|_| PyIOError::new_err("Vault directory could not be opened"))?;
    let mut files = Vec::new();
    visit_dirs(&canonical_root, &canonical_root, &mut files)
        .map_err(|_| PyIOError::new_err("Vault directory could not be scanned"))?;
    Ok(files)
}

#[pymodule]
fn orange_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(scan_vault_fast, m)?)?;
    Ok(())
}
