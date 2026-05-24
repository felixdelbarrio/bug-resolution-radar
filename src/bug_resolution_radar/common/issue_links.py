"""Issue reference normalization and link helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping
from urllib.parse import quote, urlparse

JIRA_KEY_PATTERN = r"\b[A-Z][A-Z0-9]+-\d+(?:[A-Z0-9-]*)?\b"
HELIX_ID_PATTERN = r"\bINC\d{8,}\b"

JIRA_KEY_RE = re.compile(JIRA_KEY_PATTERN, flags=re.IGNORECASE)
HELIX_ID_RE = re.compile(HELIX_ID_PATTERN, flags=re.IGNORECASE)
_ISSUE_REF_RE = re.compile(f"({HELIX_ID_PATTERN})|({JIRA_KEY_PATTERN})", flags=re.IGNORECASE)


@dataclass(frozen=True)
class IssueReferenceSegment:
    text: str
    url: str = ""
    kind: str = ""


def normalize_jira_key(value: object) -> str:
    txt = str(value or "").strip().upper()
    match = JIRA_KEY_RE.fullmatch(txt)
    return str(match.group(0)).upper() if match else ""


def normalize_helix_id(value: object) -> str:
    txt = str(value or "").strip().upper()
    match = HELIX_ID_RE.fullmatch(txt)
    return str(match.group(0)).upper() if match else ""


def _http_url(value: object) -> str:
    txt = str(value or "").strip()
    if not txt:
        return ""
    parsed = urlparse(txt)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return txt


def _jira_root(base_url: str) -> str:
    base = _http_url(base_url)
    if not base:
        return ""
    marker = "/browse/"
    lowered = base.lower()
    if marker in lowered:
        return base[: lowered.index(marker)].rstrip("/")
    return base.rstrip("/")


def build_jira_issue_url(
    jira_key: object,
    *,
    base_url: str = "",
    existing_url: str = "",
) -> str:
    key = normalize_jira_key(jira_key)
    if not key:
        return ""
    existing = _http_url(existing_url)
    if existing:
        return existing
    root = _jira_root(base_url)
    if not root:
        return ""
    return f"{root}/browse/{quote(key)}"


def build_helix_issue_url(
    helix_id: object,
    *,
    base_url: str = "",
    existing_url: str = "",
) -> str:
    incident_id = normalize_helix_id(helix_id)
    if not incident_id:
        return ""
    existing = _http_url(existing_url)
    if existing:
        return existing
    base = _http_url(base_url)
    if not base:
        return ""
    if "{helix_id}" in base:
        return base.replace("{helix_id}", quote(incident_id))
    if "{id}" in base:
        return base.replace("{id}", quote(incident_id))
    return base


def _build_helix_map_url(
    helix_id: object,
    *,
    base_url: str = "",
    existing_url: str = "",
) -> str:
    existing = _http_url(existing_url)
    if existing:
        return existing
    base = _http_url(base_url)
    if "{helix_id}" not in base and "{id}" not in base:
        return ""
    return build_helix_issue_url(helix_id, base_url=base, existing_url="")


def build_issue_url_maps(
    rows: Iterable[Mapping[str, object]],
    *,
    jira_base_url: str = "",
    helix_base_url: str = "",
) -> tuple[dict[str, str], dict[str, str]]:
    """Build normalized Jira and Helix URL maps from heterogeneous issue rows."""
    jira_urls: dict[str, str] = {}
    helix_urls: dict[str, str] = {}
    for row in rows:
        source_type = str(row.get("source_type") or "").strip().lower()

        jira_key = normalize_jira_key(row.get("jira_key") or row.get("key") or "")
        jira_existing_url = str(row.get("jira_url") or "").strip()
        if source_type != "helix" and not jira_existing_url:
            jira_existing_url = str(row.get("url") or "").strip()
        jira_url = build_jira_issue_url(
            jira_key,
            base_url=jira_base_url,
            existing_url=jira_existing_url,
        )
        if jira_key and jira_url:
            jira_urls.setdefault(jira_key, jira_url)

        helix_id = normalize_helix_id(row.get("helix_id") or row.get("id") or row.get("key") or "")
        helix_existing_url = str(row.get("helix_url") or "").strip()
        if source_type == "helix" and not helix_existing_url:
            helix_existing_url = str(row.get("url") or "").strip()
        helix_url = _build_helix_map_url(
            helix_id,
            base_url=helix_base_url,
            existing_url=helix_existing_url,
        )
        if helix_id and helix_url:
            helix_urls.setdefault(helix_id, helix_url)
    return jira_urls, helix_urls


def linkify_issue_references(
    text: object,
    *,
    jira_base_url: str = "",
    helix_base_url: str = "",
    jira_urls: dict[str, str] | None = None,
    helix_urls: dict[str, str] | None = None,
) -> tuple[IssueReferenceSegment, ...]:
    raw = str(text or "")
    if not raw:
        return ()

    jira_lookup = {normalize_jira_key(key): value for key, value in dict(jira_urls or {}).items()}
    helix_lookup = {normalize_helix_id(key): value for key, value in dict(helix_urls or {}).items()}
    segments: list[IssueReferenceSegment] = []
    cursor = 0
    for match in _ISSUE_REF_RE.finditer(raw):
        start, end = match.span()
        if start > cursor:
            segments.append(IssueReferenceSegment(raw[cursor:start]))
        token = str(match.group(0) or "")
        helix_id = normalize_helix_id(token)
        jira_key = "" if helix_id else normalize_jira_key(token)
        if helix_id:
            url = build_helix_issue_url(
                helix_id,
                base_url=helix_base_url,
                existing_url=helix_lookup.get(helix_id, ""),
            )
            segments.append(IssueReferenceSegment(helix_id, url=url, kind="helix"))
        elif jira_key:
            url = build_jira_issue_url(
                jira_key,
                base_url=jira_base_url,
                existing_url=jira_lookup.get(jira_key, ""),
            )
            segments.append(IssueReferenceSegment(jira_key, url=url, kind="jira"))
        else:
            segments.append(IssueReferenceSegment(token))
        cursor = end
    if cursor < len(raw):
        segments.append(IssueReferenceSegment(raw[cursor:]))
    return tuple(segment for segment in segments if segment.text)
