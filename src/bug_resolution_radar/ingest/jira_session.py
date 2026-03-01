"""Jira HTTP session factory and browser cookie integration."""

from __future__ import annotations

from typing import Optional

from .cookie_utils import (
    build_cookie_header_for_hosts,
    candidate_domains_from_host,
    load_cookie_jar,
)


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
    for domain_name in candidate_domains_from_host(host):
        jar = load_cookie_jar(getter, domain_name=domain_name)
        if jar is not None:
            cookie_jars.append(jar)
    if not cookie_jars:
        jar = load_cookie_jar(getter)
        if jar is None:
            return None
        cookie_jars.append(jar)
    return build_cookie_header_for_hosts(cookie_jars, hosts=[host])
