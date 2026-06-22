from __future__ import annotations

import json
import re
import ssl
import xml.etree.ElementTree as ET
from dataclasses import asdict
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPSHandler, Request, build_opener

from collector.official_sources.models import DiscoveredItem
from collector.official_sources.relevance import is_cybersecurity_relevant

NAVIGATION_TITLES = {
    "",
    "back",
    "back to top",
    "content",
    "deutsch",
    "english",
    "home",
    "jump to main contents",
    "jump to navigation",
    "japanese",
    "main menu",
    "menu",
    "search",
    "skip to content",
    "skip to main content",
    "skip to navigation",
    "top",
}


class _AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = None
        for key, value in attrs:
            if key.lower() == "href":
                href = value
                break
        self._current_href = href
        self._text_parts = []

    def handle_data(self, data):
        if self._current_href is not None:
            self._text_parts.append(data.strip())

    def handle_endtag(self, tag):
        if tag.lower() != "a" or self._current_href is None:
            return
        title = " ".join(part for part in self._text_parts if part).strip()
        self.links.append({"href": self._current_href, "title": title})
        self._current_href = None
        self._text_parts = []


class OfficialSourceFetcher:
    def __init__(self):
        self._ssl_context = ssl._create_unverified_context()
        self._opener = build_opener(HTTPSHandler(context=self._ssl_context))

    def fetch(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        source_type = (source.get("source_type") or "").lower()
        if source_type == "rss":
            return self._fetch_rss(source)
        if source_type == "pdf_index":
            return self._fetch_html_like(source, pdf_only=True)
        if source_type == "official_api":
            return self._fetch_api(source)
        return self._fetch_html_like(source, pdf_only=False)

    def _open(self, url: str) -> bytes:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with self._opener.open(request, timeout=20) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ValueError(f"抓取官方源失败: {exc}") from exc

    def _fetch_rss(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        body = self._open(source["list_url"])
        root = ET.fromstring(body)
        items: list[dict[str, Any]] = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip() or None
            if title and link:
                items.append(asdict(DiscoveredItem(title=title, detail_url=link, published_date=pub_date)))
        return items

    def _fetch_api(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        body = self._open(source["list_url"])
        payload = json.loads(body.decode("utf-8"))
        items_path = (source.get("parser_config") or {}).get("items_path") or []
        items = payload
        for key in items_path:
            items = items[key]
        result: list[dict[str, Any]] = []
        for item in items:
            title = (item.get("title") or "").strip()
            link = (item.get("url") or item.get("link") or "").strip()
            if title and link:
                result.append(asdict(DiscoveredItem(title=title, detail_url=link, published_date=item.get("published_date"))))
        return result

    def _fetch_html_like(self, source: dict[str, Any], pdf_only: bool) -> list[dict[str, Any]]:
        body = self._open(source["list_url"])
        config = source.get("parser_config") or {}
        if pdf_only and (source["list_url"].lower().endswith(".pdf") or body.startswith(b"%PDF")):
            return [
                asdict(
                    DiscoveredItem(
                        title=source["name"],
                        detail_url=source["list_url"],
                        artifact_url=source["list_url"],
                    )
                )
            ]
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        if config.get("include_self"):
            title = config.get("self_title") or source["name"]
            result.append(
                asdict(
                    DiscoveredItem(
                        title=title,
                        detail_url=source["list_url"],
                        artifact_url=source["list_url"] if source["list_url"].lower().endswith(".pdf") else None,
                    )
                )
            )
            seen.add(source["list_url"])
        parser = _AnchorParser()
        parser.feed(body.decode("utf-8", errors="ignore"))
        patterns = [re.compile(pattern, re.I) for pattern in config.get("url_patterns", [])]
        exclude_url_patterns = [re.compile(pattern, re.I) for pattern in config.get("exclude_url_patterns", [])]
        exclude_title_patterns = [re.compile(pattern, re.I) for pattern in config.get("exclude_title_patterns", [])]
        allowed_domains = {self._normalize_domain(domain) for domain in (source.get("allowed_domains") or [])}
        for link in parser.links:
            href = (link.get("href") or "").strip()
            if not href:
                continue
            full_url = urljoin(source["base_url"], href)
            parsed = urlparse(full_url)
            if parsed.scheme not in {"http", "https"}:
                continue
            if allowed_domains and self._normalize_domain(parsed.netloc) not in allowed_domains:
                continue
            if pdf_only and not full_url.lower().endswith(".pdf"):
                continue
            title = (link.get("title") or "").strip()
            if self._is_navigation_anchor(source["list_url"], full_url, title):
                continue
            if exclude_url_patterns and any(pattern.search(full_url) for pattern in exclude_url_patterns):
                continue
            if exclude_title_patterns and any(pattern.search(title) for pattern in exclude_title_patterns):
                continue
            haystack = f"{full_url} {link.get('title','')}"
            if patterns and not any(pattern.search(haystack) for pattern in patterns):
                continue
            if not self._is_cybersecurity_relevant(haystack):
                continue
            if full_url in seen:
                continue
            seen.add(full_url)
            title = (title or parsed.path.rsplit("/", 1)[-1] or source["name"]).strip()
            result.append(
                asdict(
                    DiscoveredItem(
                        title=title,
                        detail_url=full_url,
                        artifact_url=full_url if full_url.lower().endswith(".pdf") else None,
                    )
                )
            )
        return result

    def _normalize_domain(self, domain: str) -> str:
        return (domain or "").strip().lower().removeprefix("www.")

    def _is_navigation_anchor(self, list_url: str, full_url: str, title: str) -> bool:
        normalized_title = re.sub(r"\s+", " ", (title or "").strip().lower())
        normalized_title = normalized_title.strip("[](){}")
        if normalized_title in NAVIGATION_TITLES:
            return True
        parsed_full = urlparse(full_url)
        if parsed_full.fragment:
            return True
        return False

    def _is_cybersecurity_relevant(self, text: str) -> bool:
        return is_cybersecurity_relevant(text)
