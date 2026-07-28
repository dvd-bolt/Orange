import asyncio
import socket

import pytest


def _address_info(address: str, port: int = 443):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return [(family, socket.SOCK_STREAM, 6, "", (address, port))]


def test_public_url_validation_rejects_credentials_ports_and_private_dns(
    monkeypatch,
):
    from core import research

    monkeypatch.setattr(
        research.socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: _address_info("93.184.216.34", port),
    )
    assert research.is_public_http_url("https://example.com/path")
    assert not research.is_public_http_url("https://user:secret@example.com/path")
    assert not research.is_public_http_url("https://example.com:8443/path")
    assert not research.is_public_http_url("http://service.local/path")

    monkeypatch.setattr(
        research.socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [
            *_address_info("93.184.216.34", port),
            *_address_info("127.0.0.1", port),
        ],
    )
    assert not research.is_public_http_url("https://example.com/path")


def test_research_collection_bounds_result_and_page_counts(monkeypatch):
    from core import research
    import ddgs

    calls = {"max_results": 0, "pages": 0}

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def text(self, _topic, *, max_results):
            calls["max_results"] = max_results
            return [
                {
                    "title": f"Source {index}",
                    "href": f"https://example.com/{index}",
                    "body": "Real provider snippet",
                }
                for index in range(10)
            ]

    async def fake_fetch(url):
        calls["pages"] += 1
        return f"Fetched {url}"

    monkeypatch.setattr(ddgs, "DDGS", FakeDDGS)
    monkeypatch.setattr(research, "is_public_http_url", lambda _url: True)
    monkeypatch.setattr(research, "fetch_public_page", fake_fetch)

    payload = asyncio.run(
        research.collect_web_research(
            "bounded query",
            max_results=999,
            max_pages=999,
        )
    )

    assert calls == {"max_results": 20, "pages": 5}
    assert len(payload["sources"]) == 5


def test_research_rejects_oversized_query():
    from core.research import ResearchProviderError, collect_web_research

    with pytest.raises(ResearchProviderError):
        asyncio.run(collect_web_research("x" * 2_001))
