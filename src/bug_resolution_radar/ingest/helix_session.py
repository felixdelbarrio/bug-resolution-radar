"""Helix HTTP session bootstrap and cookie/header authentication handling."""

from __future__ import annotations

import os
from typing import Optional

from ..common.security import sanitize_cookie_header
from .cookie_utils import (
    build_cookie_header_for_hosts,
    candidate_domains_from_host,
    load_cookie_jar,
)


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


def _cookie_source() -> str:
    raw = str(os.getenv("HELIX_COOKIE_SOURCE", "browser") or "").strip().lower()
    if raw in {"manual", "auto"}:
        return raw
    return "browser"


def _manual_cookie() -> Optional[str]:
    cookie = sanitize_cookie_header(str(os.getenv("HELIX_COOKIE_HEADER", "") or "").strip())
    return cookie or None


def get_helix_session_cookie(browser: str, host: str) -> Optional[str]:
    """
    Extrae cookies de Chrome/Edge (Chromium) usando browser-cookie3.
    No persiste cookies. Devuelve un string listo para header Cookie.
    """
    source = _cookie_source()
    manual_cookie = _manual_cookie()
    if source == "manual":
        if manual_cookie:
            return manual_cookie
        raise ValueError("HELIX_COOKIE_SOURCE=manual requiere HELIX_COOKIE_HEADER no vacío.")
    if source == "auto" and manual_cookie:
        return manual_cookie
    if not host:
        return None

    import browser_cookie3  # type: ignore

    getter = browser_cookie3.edge if browser == "edge" else browser_cookie3.chrome

    hosts = _related_hosts(host)

    domains: list[str] = []
    seen_domains: set[str] = set()
    for h in hosts:
        for domain_name in candidate_domains_from_host(h):
            if domain_name and domain_name not in seen_domains:
                domains.append(domain_name)
                seen_domains.add(domain_name)

    cookie_jars = []
    for domain_name in domains:
        jar = load_cookie_jar(getter, domain_name=domain_name)
        if jar is not None:
            cookie_jars.append(jar)
    # Fallback amplio: en algunos perfiles Chromium el filtro por domain_name
    # no devuelve todas las cookies válidas de sesión.
    jar = load_cookie_jar(getter)
    if jar is not None:
        cookie_jars.append(jar)

    if not cookie_jars:
        return None
    return build_cookie_header_for_hosts(cookie_jars, hosts=hosts)
