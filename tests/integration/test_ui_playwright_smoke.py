from __future__ import annotations

import functools
import json
import threading
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return


@contextmanager
def static_project_server():
    handler = functools.partial(
        QuietStaticHandler,
        directory=str(PROJECT_ROOT),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def bridge_init_script(port: int) -> str:
    payloads = {
        "api_get_settings": {
            "language": "ru",
            "telemetry_stream": "ON",
            "telegram_daemon": "OFF",
            "auto_backup_enabled": "OFF",
            "auto_push_enabled": "OFF",
        },
        "api_get_system_status": {
            "status": "success",
            "http_base_url": f"http://127.0.0.1:{port}",
            "obsidian_vault_path": "examples/test_vault",
            "vault_status": "READY",
            "mcp_status": "READY",
            "watchdog_status": "READY",
        },
        "api_get_mcp_status": {
            "status": "success",
            "sqlite": {"status": "READY", "size_mb": 1},
            "mcp": {"status": "READY"},
        },
        "api_get_memory_items": {
            "status": "success",
            "items": [
                {
                    "id": 1,
                    "title": "Session",
                    "role": "user",
                    "content": "Pinned fact",
                    "timestamp": "now",
                    "is_pinned": 1,
                    "exclude_from_rag": 0,
                }
            ],
        },
        "api_get_inbox_proposals": {
            "status": "success",
            "items": [
                {
                    "filename": "idea.md",
                    "relative_path": "_Inbox/idea.md",
                    "file_path": "_Inbox/idea.md",
                    "category": "idea",
                    "confidence": 0.82,
                    "summary": "Inbox proposal",
                    "proposal_id": "proposal-1",
                }
            ],
        },
        "api_get_morning_dashboard": {
            "status": "success",
            "dashboard": {
                "date": "2026-07-28",
                "focus": ["Ship stable build"],
                "today_tasks": [
                    {"text": "Verify UI", "file_path": "Tasks.md", "line": 4}
                ],
                "overdue_tasks": [],
                "telegram_tasks": [],
                "orphan_notes": [
                    {"id": "notes/orphan", "path": "notes/orphan.md"}
                ],
            },
        },
        "api_get_project_pages_preview": {
            "status": "success",
            "preview_id": "project-preview",
            "plans": [
                {
                    "relative_path": "_Orange/Project Pages/demo.md",
                    "diff": "+demo",
                }
            ],
        },
        "api_get_weekly_review_preview": {
            "status": "success",
            "preview_id": "weekly-preview",
            "week": "2026-W31",
            "plan": {
                "relative_path": "_Orange/Reviews/2026-W31.md",
                "diff": "+review",
            },
        },
        "api_get_audit_log": {
            "status": "success",
            "items": [
                {
                    "id": 1,
                    "event_type": "write",
                    "status": "applied",
                    "timestamp": "now",
                    "summary": "Applied preview",
                    "details": "",
                }
            ],
        },
        "api_get_vault_time_machine": {
            "status": "success",
            "history_source": "git",
            "total_notes": 2,
            "recent_notes": 1,
            "generated_at": "now",
            "themes": [],
            "timeline": [],
            "activity_bursts": [],
            "quietest_notes": [],
        },
    }
    translations = {
        "ru": {"welcome_desc": "Добро пожаловать в Orange OS."},
        "en": {"welcome_desc": "Welcome to Orange OS."},
    }
    return f"""
        (() => {{
            const payloads = {json.dumps(payloads, ensure_ascii=False)};
            const translations = {json.dumps(translations, ensure_ascii=False)};
            function responseFor(name) {{
                if (['api_get_chats', 'api_search_chats', 'api_load_chat'].includes(name)) return [];
                if (name === 'api_get_current_chat_id') return '';
                if (name === 'api_get_http_base_url') return 'http://127.0.0.1:{port}';
                if (name === 'api_get_i18n') return JSON.stringify(translations);
                if (name === 'api_find_contradictions') return JSON.stringify({{status:'success',items:[]}});
                if (name === 'api_run_agent_debate') return JSON.stringify({{status:'error',error_code:'NOT_CONFIGURED',message:'Debate is unavailable'}});
                if (name === 'api_get_dormant_projects') return JSON.stringify({{status:'success',items:[]}});
                if (name === 'api_get_operating_manual') return JSON.stringify({{status:'success',manual:{{summary:'Vault-derived',signals:[],preferences:[]}}}});
                return JSON.stringify(payloads[name] || {{status:'success',message:'OK'}});
            }}
            window.pywebview = {{
                api: new Proxy({{}}, {{
                    get: (_target, name) => async () => responseFor(String(name)),
                }}),
            }};
            window.confirm = () => true;
        }})();
    """


@pytest.mark.parametrize("viewport", [(1200, 800), (1024, 700)])
def test_all_existing_ui_dialogs_render_without_errors(viewport):
    with static_project_server() as port, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": viewport[0], "height": viewport[1]}
        )
        errors = []
        page.on("pageerror", lambda error: errors.append(f"page: {error}"))
        page.on(
            "console",
            lambda message: (
                errors.append(f"console: {message.text}")
                if message.type == "error"
                else None
            ),
        )
        page.add_init_script(script=bridge_init_script(port))

        def route_api(route):
            if route.request.url.endswith("/api/graph"):
                body = {
                    "nodes": [
                        {
                            "id": "notes/a",
                            "label": "A",
                            "path": "notes/a.md",
                            "group": 1,
                            "type": "note",
                            "orphan": False,
                        }
                    ],
                    "links": [],
                }
            else:
                body = {
                    "title": "A",
                    "path": "notes/a.md",
                    "content": "# A",
                    "degree": 0,
                    "type": "note",
                    "suggested_links": [],
                }
            route.fulfill(
                content_type="application/json",
                body=json.dumps(body),
            )

        page.route(f"http://127.0.0.1:{port}/api/**", route_api)
        page.goto(
            f"http://127.0.0.1:{port}/ui/index.html",
            wait_until="networkidle",
        )
        page.wait_for_function(
            "() => typeof openMorningDashboard === 'function'"
        )
        visible = page.evaluate(
            """async () => {
                const shown = {};
                const check = id => !document.getElementById(id)?.classList.contains('hidden');
                await openSettings(); shown.settings = check('settings-modal'); closeSettings();
                await openMCPDashboard(); shown.mcp = check('mcp-dashboard-modal'); closeModal('mcp-dashboard-modal');
                openCommandPalette(); shown.palette = check('command-palette-modal'); closeCommandPalette();
                await openMemoryEditor(); shown.memory = check('memory-editor-modal'); closeModal('memory-editor-modal');
                await openSmartInbox(); shown.inbox = check('smart-inbox-modal'); closeModal('smart-inbox-modal');
                await openMorningDashboard(); shown.dashboard = check('morning-dashboard-modal'); closeModal('morning-dashboard-modal');
                await openProjectPages(); shown.projects = check('project-pages-modal'); closeModal('project-pages-modal');
                await openWeeklyReview(); shown.weekly = check('weekly-review-modal'); closeModal('weekly-review-modal');
                await openAuditLog(); shown.audit = check('audit-log-modal'); closeModal('audit-log-modal');
                await openVaultIntelligence('time-machine'); shown.intelligence = check('vault-intelligence-modal'); closeModal('vault-intelligence-modal');
                openModal('attachment-config-modal'); shown.pdf = check('attachment-config-modal'); closeModal('attachment-config-modal');
                showExecutionOverride('TEST'); shown.approval = check('execution-override-modal'); closeModal('execution-override-modal');
                triggerSystemPanic('TEST'); shown.panic = check('system-panic-modal'); closePanic();
                await toggleKnowledgeGraph(); shown.graph = check('knowledge-graph-overlay');
                window.__orangeXss = false;
                appendMessage('Orange', '<script>window.__orangeXss=true</script><svg onload="window.__orangeXss=true"></svg>', 'sys');
                return {
                    shown,
                    bodyOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
                    graphSvg: Boolean(document.querySelector('#graph-svg-container svg')),
                    dashboardLocation: document.body.textContent.includes('Tasks.md:4'),
                    literalWelcomeHtml: document.querySelector('[data-i18n="welcome_desc"]')?.textContent.includes('<strong>'),
                    xssExecuted: window.__orangeXss,
                };
            }"""
        )
        browser.close()

    assert errors == []
    assert all(visible["shown"].values())
    assert visible["bodyOverflow"] is False
    assert visible["graphSvg"] is True
    assert visible["dashboardLocation"] is True
    assert visible["literalWelcomeHtml"] is False
    assert visible["xssExecuted"] is False
