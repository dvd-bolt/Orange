# Сборка orange_core (Rust → Python модуль)

Модуль `orange_core` — нативное расширение Python на Rust через PyO3/Maturin.  
Обеспечивает быструю работу с файловой системой и HTTP прямо из Python без GIL-ограничений.

## Требования

| Инструмент | Установка |
|-----------|-----------|
| **Rust toolchain** | https://rustup.rs/ (установить `rustup`, затем `rustup default stable`) |
| **maturin** | `pip install maturin` |

## Быстрая сборка (режим разработки)

```bash
cd orange_core
maturin develop --release
```

После этого модуль `orange_core` будет доступен в активном `.venv` без установки колеса.

## Production сборка (wheel)

```bash
cd orange_core
maturin build --release
pip install target/wheels/orange_core-*.whl
```

## Структура Cargo.toml

```toml
[package]
name = "orange_core"
version = "0.1.0"
edition = "2021"

[lib]
name = "orange_core"
crate-type = ["cdylib"]   # ОБЯЗАТЕЛЬНО для PyO3

[dependencies]
pyo3 = { version = "0.21", features = ["extension-module"] }
```

## Экспортируемые функции (src/lib.rs)

| Функция | Сигнатура | Описание |
|---------|-----------|---------|
| `scan_vault_fast` | `(path: str) -> str` | Рекурсивный поиск всех `.md` файлов, возвращает JSON-список путей |
| `read_file_fast` | `(path: str) -> str` | Быстрое чтение файла в UTF-8 |
| `fetch_website_fast` | `(url: str) -> str` | HTTP GET запрос, возвращает тело ответа как строку |

## Пример использования в Python

```python
import orange_core

# Список всех .md файлов в vault
notes_json = orange_core.scan_vault_fast("C:/Users/user/ObsidianVault")

# Чтение файла
content = orange_core.read_file_fast("C:/orange/test_vault/MyNote.md")

# HTTP запрос
html = orange_core.fetch_website_fast("https://example.com")
```

## Troubleshooting

**Ошибка `ModuleNotFoundError: No module named 'orange_core'`**  
→ Убедитесь что `.venv` активирован и выполните `maturin develop --release` заново.

**Ошибка линковки на Windows**  
→ Установите [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) с компонентом "C++ Build Tools".

**Устаревший модуль после изменений Rust-кода**  
→ Выполните `maturin develop --release` снова — maturin автоматически пересоберёт.
