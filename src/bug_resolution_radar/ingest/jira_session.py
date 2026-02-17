"""Jira HTTP session factory and browser cookie integration."""

from __future__ import annotations

from typing import Any, Callable, Optional


def _cookie_applies_to_host(cookie_domain: str, host: str) -> bool:
    cd = (cookie_domain or "").lstrip(".").lower()
    h = (host or "").lower()
    if not cd or not h:
        return False
    return h == cd or h.endswith("." + cd)


def _candidate_domains_from_host(host: str) -> list[str]:
    h = (host or "").strip().lower()
    if not h:
        return []

    parts = [p for p in h.split(".") if p]
    candidates: list[str] = [h]
    if len(parts) >= 3:
        candidates.append(".".join(parts[1:]))  # e.g. globaldevtools.bbva.com
    if len(parts) >= 2:
        candidates.append(".".join(parts[-2:]))  # e.g. bbva.com

    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c and c not in seen:
            out.append(c)
            seen.add(c)
    return out


def _load_cookie_jar(
    getter: Callable[..., Any],
    *,
    domain_name: Optional[str] = None,
) -> Optional[Any]:
    try:
        if domain_name:
            return getter(domain_name=domain_name)
        return getter()
    except Exception:
        return None


def get_jira_session_cookie(browser: str, host: str) -> Optional[str]:
    """
    Extrae cookies de Chrome/Edge (Chromium) usando browser-cookie3.
    No persiste cookies. Devuelve un string listo para header Cookie.

    No requiere configurar dominio: se autodetecta desde el host de JIRA_BASE_URL.
    """
    if not host:
        return None

    import browser_cookie3  # type: ignore

    getter = browser_cookie3.edge if browser == "edge" else browser_cookie3.chrome

    # Prefer small cookie-jar queries by scoping with domain_name.
    # Some environments still fail; we fall back to unscoped retrieval.
    cookie_jars = []
    for d in _candidate_domains_from_host(host):
        jar = _load_cookie_jar(getter, domain_name=d)
        if jar is not None:
            cookie_jars.append(jar)
    if not cookie_jars:
        jar = _load_cookie_jar(getter)
        if jar is None:
            return None
        cookie_jars.append(jar)

    parts: dict[str, str] = {}
    for cj in cookie_jars:
        for c in cj:
            if not c.domain or not _cookie_applies_to_host(c.domain, host):
                continue
            if not c.name:
                continue
            # Keep first seen value for stability.
            parts.setdefault(c.name, c.value)

    return "; ".join([f"{k}={v}" for k, v in parts.items()]) if parts else None
