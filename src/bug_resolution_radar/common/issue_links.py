"""Issue reference normalization and link helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
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
