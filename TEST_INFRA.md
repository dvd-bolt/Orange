# Orange Framework Test Infrastructure

> Архивный отчет предыдущей реализации. Он не описывает текущий runtime и не является подтверждением прохождения тестов. Актуальные команды и покрытие находятся в `README.md` и `.github/workflows/ci.yml`.

This document outlines the testing architecture, methodology, and execution instructions for the Orange local AI assistant framework.

## Testing Methodology (4-Tier)

The test suite is built on a 4-tier testing model designed to guarantee functionality, safety, and reliability under Windows:

1. **Tier 1: Feature Coverage (55+ test cases)**
   - Covers individual component functionality (FSM Graph transitions, ScenarioEngine parser, ContextCondenser, TriggerRegistry, SecurityAnalyzer, CDP Playwright browser automation, and Vision annotator).
2. **Tier 2: Boundary & Corner Cases (55+ test cases)**
   - Focuses on limits: empty/None inputs, syntax errors, security gate rejection loops, high-volume message truncation, port collision fallbacks, and directory traversal rejections.
3. **Tier 3: Cross-Feature Combinations (11+ test cases)**
   - Exercises flows involving multiple components (e.g., ScenarioEngine steps triggering the security override dialog, or Web automation selectors routing actions through FSM nodes).
4. **Tier 4: Real-World Application Scenarios (6+ test cases)**
   - Mimics real user sessions, such as OSINT research queries paired with context compression, file edits inside local vaults triggering automatic git backups, and multi-profile session recoveries.

---

## Test Directory Structure

All test resources are located in `scratch/`:

- `scratch/run_e2e_tests.py` — Main entry point to run all unit and E2E tests, sets test-mode environment variables, and cleans up temporary folders and databases.
- `scratch/test_bugfixes.py` — Core unit tests fixing network/subprocess hangs on Windows.
- `scratch/test_e2e_fsm.py` — E2E tests for the agent graph profile transitions (`base`, `coder`, `deep_research`, `project_manager`) and SQLite checkpoints.
- `scratch/test_e2e_scenario.py` — Declarative ScenarioEngine steps YAML/JSON parsing, schema validation, and conditional routing.
- `scratch/test_e2e_condenser.py` — Dynamic message history folding, head/tail protection, and token compression.
- `scratch/test_e2e_triggers.py` — Registry and event loops for `CronTrigger`, `FileWatchTrigger`, and `WebhookTrigger`.
- `scratch/test_e2e_web.py` — Playwright CDP connectivity, interactive DOM element parser, and vision annotations.
- `scratch/test_e2e_combinations.py` — Cross-feature combination checks, security risk ranking, and approval dialogs.
- `scratch/test_e2e_workloads.py` — Integrated real-world OSINT research, coding sandbox loops, and PM task routing scenarios.

---

## Execution Instructions

To run the full test suite including all unit and E2E tests, execute:

```powershell
python scratch/run_e2e_tests.py
```

The script will automatically configure environment variable overrides (`ORANGE_TEST_MODE=1`) to bypass PyQt modal loops during automated runs, discover and execute all `test_*.py` files, and clean up temporary vaults and test databases on completion.
