# Сборка orange_core (Rust → Python модуль)

Модуль `orange_core` — нативное расширение Python на Rust через PyO3/Maturin.
Он ускоряет рекурсивное сканирование vault. Проверка пользовательского пути выполняется общим Python `VaultPathResolver` до вызова модуля.

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
edition = "2024"

[lib]
name = "orange_core"
crate-type = ["cdylib"]   # ОБЯЗАТЕЛЬНО для PyO3

[dependencies]
pyo3 = { version = "0.28.3", features = ["extension-module"] }
```

## Экспортируемые функции (src/lib.rs)

| Функция | Сигнатура | Описание |
|---------|-----------|---------|
| `scan_vault_fast` | `(path: str) -> list[str]` | Рекурсивный поиск `.md` без перехода по symlink; возвращает стабильный список абсолютных путей |

## Пример использования в Python

```python
import orange_core

# Стабильный список абсолютных путей .md файлов
notes = orange_core.scan_vault_fast("examples/test_vault")

assert any(path.endswith("roadmap.md") for path in notes)
```

## Troubleshooting

**Ошибка `ModuleNotFoundError: No module named 'orange_core'`**  
→ Убедитесь что `.venv` активирован и выполните `maturin develop --release` заново.

**Ошибка линковки на Windows**  
→ Установите [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) с компонентом "C++ Build Tools".

**Устаревший модуль после изменений Rust-кода**  
→ Выполните `maturin develop --release` снова — maturin автоматически пересоберёт.
