"""Shared helpers for browser-cookie extraction and header assembly."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional


def cookie_applies_to_host(cookie_domain: str, host: str) -> bool:
    cd = (cookie_domain or "").lstrip(".").lower()
    h = (host or "").lower()
    if not cd or not h:
        return False
    return h == cd or h.endswith("." + cd)


def candidate_domains_from_host(host: str) -> list[str]:
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
    for domain in candidates:
        if domain and domain not in seen:
            out.append(domain)
            seen.add(domain)
    return out


def load_cookie_jar(
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


def build_cookie_header_for_hosts(
    cookie_jars: Iterable[Any],
    *,
    hosts: list[str],
) -> Optional[str]:
    valid_hosts = [str(h or "").strip().lower() for h in hosts if str(h or "").strip()]
    if not valid_hosts:
        return None

    parts: dict[str, str] = {}
    for cookie_jar in cookie_jars:
        for cookie in cookie_jar:
            cookie_domain = str(getattr(cookie, "domain", "") or "")
            if not cookie_domain:
                continue
            if not any(cookie_applies_to_host(cookie_domain, host) for host in valid_hosts):
                continue

            cookie_name = str(getattr(cookie, "name", "") or "")
            if not cookie_name:
                continue
            cookie_value = str(getattr(cookie, "value", "") or "")
            # Keep first seen value for stability across duplicated jars.
            parts.setdefault(cookie_name, cookie_value)

    return "; ".join([f"{name}={value}" for name, value in parts.items()]) if parts else None
