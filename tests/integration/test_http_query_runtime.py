import asyncio
import http.client
import json
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from types import SimpleNamespace


class FakeAgentAPI:
    def __init__(self, response="ok", delay=0.0):
        self.response = response
        self.delay = delay
        self.calls = []

    async def _async_run_http_query(self, profile, prompt, query):
        self.calls.append((profile, prompt, query))
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.response


@contextmanager
def running_http_server(tmp_path, api):
    from main import ObsidianQueryHandler

    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(
        target=lambda: (asyncio.set_event_loop(loop), loop.run_forever()),
        daemon=True,
    )
    loop_thread.start()

    server = ThreadingHTTPServer(("127.0.0.1", 0), ObsidianQueryHandler)
    server.daemon_threads = True
    server.deps = SimpleNamespace(obsidian_vault_path=str(tmp_path))
    server.api = api
    server.background_loop = loop
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=2)
        loop.close()


def post_json(port, payload, *, accept="application/json", extra_headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
        "Accept": accept,
    }
    headers.update(extra_headers or {})
    connection.request(
        "POST",
        "/query",
        body=body,
        headers=headers,
    )
    response = connection.getresponse()
    response_body = response.read()
    connection.close()
    return response.status, response.getheader("Content-Type"), response_body


def test_query_handler_returns_success_json_and_routes_on_user_query(tmp_path):
    api = FakeAgentAPI("real answer")
    with running_http_server(tmp_path, api) as port:
        status, content_type, body = post_json(
            port,
            {
                "note_title": "Roadmap",
                "content": "# Roadmap",
                "query": "исправь Python тест",
            },
        )

    payload = json.loads(body)
    assert status == 200
    assert content_type.startswith("application/json")
    assert payload == {"status": "success", "answer": "real answer"}
    assert api.calls[0][0] == "auto"
    assert api.calls[0][2] == "исправь Python тест"
    assert api.calls[0][1].count("исправь Python тест") == 1


def test_query_handler_maps_agent_markers_to_stable_json_errors(tmp_path):
    api = FakeAgentAPI("[NOT_CONFIGURED] GOOGLE_API_KEY is required.")
    with running_http_server(tmp_path, api) as port:
        status, _content_type, body = post_json(
            port,
            {"note_title": "", "content": "", "query": "hello"},
        )

    payload = json.loads(body)
    assert status == 503
    assert payload == {
        "status": "error",
        "error_code": "NOT_CONFIGURED",
        "message": "GOOGLE_API_KEY is required.",
    }


def test_query_handler_enforces_body_and_field_limits(
    tmp_path,
    monkeypatch,
):
    import main

    monkeypatch.setattr(main, "MAX_HTTP_QUERY_BYTES", 128)
    api = FakeAgentAPI("must not run")
    with running_http_server(tmp_path, api) as port:
        status, _content_type, body = post_json(
            port,
            {"query": "x" * 200},
        )

    payload = json.loads(body)
    assert status == 413
    assert payload["error_code"] == "VALIDATION_ERROR"
    assert api.calls == []


def test_query_handler_cancels_timed_out_agent_run(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "HTTP_QUERY_TIMEOUT_SECONDS", 0.05)
    api = FakeAgentAPI("late answer", delay=1.0)
    with running_http_server(tmp_path, api) as port:
        status, _content_type, body = post_json(
            port,
            {"query": "slow"},
        )

    payload = json.loads(body)
    assert status == 504
    assert payload["error_code"] == "TIMEOUT"


def test_query_handler_rejects_dns_rebinding_host_and_external_origin(tmp_path):
    api = FakeAgentAPI("must not run")
    with running_http_server(tmp_path, api) as port:
        bad_host_status, _content_type, bad_host_body = post_json(
            port,
            {"query": "hello"},
            extra_headers={"Host": "attacker.example"},
        )
        bad_origin_status, _content_type, bad_origin_body = post_json(
            port,
            {"query": "hello"},
            extra_headers={"Origin": "https://attacker.example"},
        )

    assert bad_host_status == 403
    assert bad_origin_status == 403
    assert json.loads(bad_host_body)["error_code"] == "VALIDATION_ERROR"
    assert json.loads(bad_origin_body)["error_code"] == "VALIDATION_ERROR"
    assert api.calls == []
