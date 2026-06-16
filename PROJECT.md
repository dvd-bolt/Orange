# Project: Jarvis Upgrade (Phases 2, 3, and 4)

## Architecture
The system consists of the following components:
1. **Agent Core & FSM Graph** (`core/graph.py`):
   - Implements `OrangeGraphState` transitions using `pydantic-graph`.
   - Transitions are profile-specific: `base`, `coder`, `deep_research`, and `project_manager`.
   - Node-level plan checkpointing serializes state into SQLite.
2. **Scenario Engine & Context Condenser**:
   - Parses declarative YAML/JSON scenarios defining sequential or conditional steps and tool calls.
   - Condenses message context dynamically, protecting head (system prompt) and tail (recent messages) and summarizing the middle.
3. **Unified Trigger Registry & Security Gate**:
   - Central registry for `CronTrigger`, `FileWatchTrigger` (watchdog), and `WebhookTrigger`.
   - Risk classification in `SecurityAnalyzer` blocks command execution/file writes outside the vault until PyQt UI confirmation is received.
4. **Web Automation**:
   - Playwright CDP integration attaches to active Chrome instances.
   - Interactive DOM parser lists numbered interactive elements.
   - Screen annotator generates visual markup of the viewport.
5. **UI Integration**:
   - Drawflow visualizes scenario topologies.
   - Chat UI displays collapsible tool cards for cleaner logs.

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | E2E Test Suite | Build opaque-box E2E test suite (Tiers 1-4) and generate `TEST_READY.md` | None | DONE |
| 2 | Phase 2 Core | Profile Topologies, SQLite Checkpointing, Scenario Engine, Context Condenser | None | DONE |
| 3 | Phase 3 Registry & Gate | Unified Trigger Registry, Security Gate, secure `.env` credential load | M2 | DONE |
| 4 | Phase 3 Web Automation | Playwright CDP, DOM Parser, Vision Screen Annotator | M2 | DONE |
| 5 | Phase 4 UI Integration | Drawflow visualizer, chat collapsible tool cards | M3, M4 | DONE |
| 6 | Verification & Hardening | Pass 100% of E2E tests, run Tier 5 adversarial testing, write report | M1, M5 | DONE |

## Interface Contracts

### ScenarioEngine ↔ Graph
- Scenario YAML schema validation:
  ```json
  {
    "name": "string",
    "steps": [
      {
        "id": "string",
        "action": "string",
        "params": "dict",
        "approval_required": "boolean"
      }
    ]
  }
  ```
- Executed step-by-step by FSM graph, supporting conditional routing.

### SecurityGate ↔ Bridge/PyQt UI
- Risk assessment function: `analyze_risk(action_type: str, details: dict) -> str` (returns `"LOW"`, `"MEDIUM"`, `"HIGH"`)
- Approval request API: `request_override(action_text: str) -> bool` (async, pops PyQt modal, blocks execution without freezing UI loop)

### TriggerRegistry ↔ Agent Handler
- Register trigger: `register_trigger(trigger_id: str, trigger_type: str, config: dict, callback: Callable)`
- Triggers push events into agent execution queue.

## Code Layout
- `core/graph.py` — Profile graph topologies and step checkpointing.
- `core/scenario.py` — Scenario engine parser and runner.
- `core/condenser.py` — Multi-phase context condenser.
- `core/triggers.py` — Unified Trigger Registry.
- `core/security.py` — Risk analysis and PyQt dialog integration.
- `core/web_aut.py` — Playwright CDP, DOM parser, and annotator.
- `ui/` — pywebview files (chat UI, Drawflow scenario editor).
- `scratch/` — Unit and integration tests.
