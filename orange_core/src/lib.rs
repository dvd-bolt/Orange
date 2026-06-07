use pyo3::prelude::*;
use std::fs;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};
use reqwest::blocking::get;

// Вспомогательная рекурсивная функция для обхода всех подпапок
fn visit_dirs(dir: &Path, files_list: &mut String) -> std::io::Result<()> {
    if dir.is_dir() {
        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.is_dir() {
                let _ = visit_dirs(&path, files_list); // Рекурсивно ныряем в подпапку
            } else if let Some(ext) = path.extension() {
                if ext == "md" {
                    // Обязательно сохраняем полный путь, чтобы агент мог его прочитать
                    if let Some(path_str) = path.to_str() {
                        files_list.push_str(&format!("- {}\n", path_str));
                    }
                }
            }
        }
    }
    Ok(())
}

#[pyfunction]
fn scan_vault_fast(path: String) -> PyResult<String> {
    let dir_path = Path::new(&path);
    if !dir_path.exists() || !dir_path.is_dir() {
        return Ok(format!("Ошибка: Директория не найдена: {}", path));
    }

    let mut files_list = String::new();
    let _ = visit_dirs(dir_path, &mut files_list);
    
    if files_list.is_empty() {
        Ok(format!("В директории и подпапках {} нет .md файлов.", path))
    } else {
        // Предохранитель от переполнения: отдаем максимум 50 файлов
        let lines: Vec<&str> = files_list.lines().collect();
        if lines.len() > 50 {
            let truncated = lines[..50].join("\n");
            Ok(format!("Найдены сотни заметок. Вот первые 50 абсолютных путей:\n{}\n...[остальные скрыты ради экономии контекста]", truncated))
        } else {
            Ok(format!("Найдены заметки:\n{}", files_list))
        }
    }
}

#[pyfunction]
fn read_file_fast(file_path: String) -> PyResult<String> {
    match fs::read_to_string(&file_path) {
        Ok(content) => Ok(content),
        Err(e) => Ok(format!("Ошибка при чтении файла {}: {}", file_path, e)),
    }
}

#[pyfunction]
fn write_file_safe(file_path: String, content: String) -> PyResult<String> {
    let path = Path::new(&file_path);
    if path.exists() {
        let timestamp = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
        let backup_path = format!("{}.{}.bak", file_path, timestamp);
        if let Err(e) = fs::copy(&path, &backup_path) {
            return Ok(format!("Ошибка при создании бэкапа: {}", e));
        }
    }
    match fs::write(&path, content) {
        Ok(_) => Ok(format!("Файл {} успешно сохранен (Бэкап создан).", file_path)),
        Err(e) => Ok(format!("Ошибка при записи файла {}: {}", file_path, e)),
    }
}

#[pyfunction]
fn fetch_website_fast(url: String) -> PyResult<String> {
    match get(&url) {
        Ok(response) => match response.text() {
            Ok(text) => Ok(if text.len() > 15000 { text[..15000].to_string() } else { text }),
            Err(e) => Ok(format!("Ошибка текста: {}", e)),
        },
        Err(e) => Ok(format!("Ошибка сети: {}", e)),
    }
}

#[pymodule]
fn orange_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(scan_vault_fast, m)?)?;
    m.add_function(wrap_pyfunction!(read_file_fast, m)?)?;
    m.add_function(wrap_pyfunction!(write_file_safe, m)?)?;
    m.add_function(wrap_pyfunction!(fetch_website_fast, m)?)?;
    Ok(())
}
