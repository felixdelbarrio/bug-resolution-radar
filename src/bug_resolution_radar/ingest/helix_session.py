# src/ingest/helix_session.py
from __future__ import annotations

from typing import Any, Callable, Optional


def _cookie_applies_to_host(cookie_domain: str, host: str) -> bool:
    cd = (cookie_domain or "").lstrip(".").lower()
    h = (host or "").lower()
    if not cd or not h:
        return False
    return h == cd or h.endswith("." + cd)


def _cookie_applies_to_any_host(cookie_domain: str, hosts: list[str]) -> bool:
    return any(_cookie_applies_to_host(cookie_domain, h) for h in hosts)


def _related_hosts(host: str) -> list[str]:
    h = (host or "").strip().lower()
    if not h:
        return []
    out = [h]
    if "-smartit." in h:
        out.append(h.replace("-smartit.", "-rsso.", 1))
    seen: set[str] = set()
    dedup: list[str] = []
    for x in out:
        if x and x not in seen:
            dedup.append(x)
            seen.add(x)
    return dedup


def _candidate_domains_from_host(host: str) -> list[str]:
    h = (host or "").strip().lower()
    if not h:
        return []

    parts = [p for p in h.split(".") if p]
    candidates: list[str] = [h]
    if len(parts) >= 3:
        candidates.append(".".join(parts[1:]))  # e.g. helixbbva-smartit.onbmc.com
    if len(parts) >= 2:
        candidates.append(".".join(parts[-2:]))  # e.g. onbmc.com

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


def get_helix_session_cookie(browser: str, host: str) -> Optional[str]:
    """
    Extrae cookies de Chrome/Edge (Chromium) usando browser-cookie3.
    No persiste cookies. Devuelve un string listo para header Cookie.
    """
    if not host:
        return None

    import browser_cookie3  # type: ignore

    getter = browser_cookie3.edge if browser == "edge" else browser_cookie3.chrome

    hosts = _related_hosts(host)

    domains: list[str] = []
    seen_domains: set[str] = set()
    for h in hosts:
        for d in _candidate_domains_from_host(h):
            if d and d not in seen_domains:
                domains.append(d)
                seen_domains.add(d)

    cookie_jars = []
    for d in domains:
        jar = _load_cookie_jar(getter, domain_name=d)
        if jar is not None:
            cookie_jars.append(jar)
    # Fallback amplio: en algunos perfiles Chromium el filtro por domain_name
    # no devuelve todas las cookies válidas de sesión.
    jar = _load_cookie_jar(getter)
    if jar is not None:
        cookie_jars.append(jar)

    if not cookie_jars:
        return None

    parts: dict[str, str] = {}
    for cj in cookie_jars:
        for c in cj:
            if not c.domain or not _cookie_applies_to_any_host(c.domain, hosts):
                continue
            if not c.name:
                continue
            parts.setdefault(c.name, c.value)

    return "; ".join([f"{k}={v}" for k, v in parts.items()]) if parts else None
