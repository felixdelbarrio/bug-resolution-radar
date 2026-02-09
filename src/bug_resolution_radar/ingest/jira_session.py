from __future__ import annotations

from typing import Optional

def get_jira_session_cookie(browser: str, domain: str) -> Optional[str]:
    """
    Extrae cookies de Chrome/Edge (Chromium) usando browser-cookie3.
    No persiste cookies. Devuelve un string listo para header Cookie.
    """
    if not domain:
        return None

    import browser_cookie3  # type: ignore

    if browser == "edge":
        cj = browser_cookie3.edge(domain_name=domain)
    else:
        cj = browser_cookie3.chrome(domain_name=domain)

    parts = []
    for c in cj:
        if c.domain and domain in c.domain:
            parts.append(f"{c.name}={c.value}")
    return "; ".join(parts) if parts else None
