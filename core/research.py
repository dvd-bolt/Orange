from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Dict, List
from urllib.parse import urljoin, urlparse


class ResearchUnavailableError(RuntimeError):
    """Raised when the configured web-search implementation is unavailable."""


class ResearchProviderError(RuntimeError):
    """Raised when a real search provider fails or returns no usable results."""


@dataclass(frozen=True)
class ResearchSource:
    title: str
    url: str
    snippet: str
    content: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "content": self.content,
        }


async def collect_web_research(
    topic: str,
    *,
    max_results: int = 8,
    max_pages: int = 3,
) -> Dict:
    """Search the public web and fetch a bounded set of real source pages."""
    topic = str(topic or "").strip()
    if not topic:
        raise ResearchProviderError("Research query is empty.")
    if len(topic) > 2_000:
        raise ResearchProviderError("Research query exceeds the 2,000 character limit.")
    max_results = max(1, min(int(max_results), 20))
    max_pages = max(1, min(int(max_pages), 5))

    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise ResearchUnavailableError(
            "Web search is not installed. Install dependencies from requirements.txt."
        ) from exc

    def run_search() -> List[Dict]:
        with DDGS() as ddgs:
            return list(ddgs.text(topic, max_results=max_results))

    try:
        raw_results = await asyncio.wait_for(asyncio.to_thread(run_search), timeout=25)
    except asyncio.TimeoutError as exc:
        raise ResearchProviderError("Web search timed out after 25 seconds.") from exc
    except Exception as exc:
        raise ResearchProviderError(
            f"Web search provider failed: {type(exc).__name__}"
        ) from exc

    usable = []
    seen_urls = set()
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("href") or item.get("url") or "").strip()
        if not url or url in seen_urls or not is_public_http_url(url):
            continue
        seen_urls.add(url)
        usable.append({
            "title": str(item.get("title") or url).strip()[:300],
            "url": url,
            "snippet": str(item.get("body") or item.get("snippet") or "").strip()[:1200],
        })

    if not usable:
        raise ResearchProviderError(
            f"Web search returned no usable public sources for '{topic}'."
        )

    sources: List[ResearchSource] = []
    for item in usable[:max_pages]:
        try:
            content = await fetch_public_page(item["url"])
        except ResearchProviderError as exc:
            content = f"[SOURCE_UNAVAILABLE: {type(exc).__name__}]"
        sources.append(ResearchSource(content=content, **item))

    if not sources:
        raise ResearchProviderError("Search results were found, but no source page could be loaded.")

    return {
        "status": "success",
        "query": topic,
        "sources": [source.as_dict() for source in sources],
    }


async def fetch_public_page(url: str, *, limit: int = 12_000) -> str:
    """Fetch text from a public HTTP(S) page while blocking local-network SSRF."""
    from bs4 import BeautifulSoup

    try:
        payload = await fetch_public_html(url, limit=2_000_000)
        html = payload["text"]
    except ResearchProviderError:
        raise
    except Exception as exc:
        return f"[SOURCE_UNAVAILABLE: {type(exc).__name__}]"

    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "head", "noscript", "svg"]):
        node.decompose()
    text = "\n".join(
        line.strip()
        for line in soup.get_text(separator="\n").splitlines()
        if line.strip()
    )
    return text[:limit] or "[SOURCE_EMPTY]"


async def fetch_public_html(url: str, *, limit: int = 2_000_000) -> Dict:
    """Fetch bounded public HTML and validate every redirect before following it."""
    if not is_public_http_url(url):
        raise ResearchProviderError("Only public HTTP(S) URLs are allowed.")

    import httpx

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 Chrome/124 Safari/537.36"
        )
    }
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=httpx.Timeout(15.0, connect=8.0),
    ) as client:
        current_url = url
        for _ in range(6):
            if not is_public_http_url(current_url):
                raise ResearchProviderError("A source redirected to a non-public address.")
            async with client.stream("GET", current_url, headers=headers) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location", "")
                    if not location:
                        raise ResearchProviderError("A source returned an invalid redirect.")
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                chunks = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > limit:
                        remaining = max(0, limit - (total - len(chunk)))
                        chunks.append(chunk[:remaining])
                        break
                    chunks.append(chunk)
                encoding = response.encoding or "utf-8"
                text = b"".join(chunks).decode(encoding, errors="replace")
                return {
                    "status": response.status_code,
                    "url": str(response.url),
                    "headers": dict(response.headers),
                    "text": text,
                }
    raise ResearchProviderError("A source exceeded the redirect limit.")


def format_research_context(payload: Dict) -> str:
    """Format collected sources as verifiable prompt context."""
    chunks = ["REAL WEB RESEARCH SOURCES:"]
    for index, source in enumerate(payload.get("sources", []), start=1):
        chunks.append(
            f"### Source {index}: {source.get('title', '')}\n"
            f"URL: {source.get('url', '')}\n"
            f"Search snippet: {source.get('snippet', '')}\n"
            f"Page text:\n{source.get('content', '')}"
        )
    chunks.append(
        "Use only supported claims. Cite the exact source URLs in the final response. "
        "Clearly label uncertainty or unavailable pages."
    )
    return "\n\n".join(chunks) + "\n\n"


def is_public_http_url(url: str) -> bool:
    try:
        if not isinstance(url, str) or any(ord(char) < 32 for char in url):
            return False
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return False
        hostname = parsed.hostname.lower().rstrip(".")
        if (
            hostname in {"localhost", "localhost.localdomain"}
            or hostname.endswith(".local")
        ):
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port not in {80, 443}:
            return False

        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        }
        if not addresses:
            return False
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                return False
        return True
    except (OSError, ValueError):
        return False
