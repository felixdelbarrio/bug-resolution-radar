from __future__ import annotations

import ipaddress
import re
from typing import Optional
from urllib.parse import urlparse, urlunparse

import streamlit as st

SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(authorization:)(\s*)(.+)"),
    re.compile(r"(?i)(cookie:)(\s*)(.+)"),
    re.compile(r"(?i)(token)(\s*[:=]\s*)([^\s]+)"),
]

_LOCAL_HOSTNAMES = {"localhost", "localhost.localdomain"}


def mask_secret(value: str) -> str:
    if not value:
        return value
    if len(value) <= 8:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 6) + value[-3:]


def safe_log_text(text: str) -> str:
    out = text
    for pat in SENSITIVE_PATTERNS:
        out = pat.sub(lambda m: f"{m.group(1)}{m.group(2)}***", out)
    return out


def _is_local_or_private_host(host: str) -> bool:
    h = (host or "").strip().lower().rstrip(".")
    if not h:
        return True
    if h in _LOCAL_HOSTNAMES or h.endswith(".local"):
        return True

    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False

    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_service_base_url(raw_url: str, *, service_name: str) -> str:
    """
    Normalize and validate service base URL used by outbound HTTP clients.

    Security hardening:
    - Enforce https scheme.
    - Reject credentials in URL.
    - Reject local/private hosts to reduce SSRF risk from misconfiguration.
    """
    value = (raw_url or "").strip()
    if not value:
        raise ValueError(f"Configura {service_name} base URL.")

    parsed = urlparse(value)
    if parsed.scheme.lower() != "https":
        raise ValueError(f"{service_name}: solo se permite HTTPS por seguridad.")
    if not parsed.netloc:
        raise ValueError(f"{service_name}: URL inválida.")
    if parsed.username or parsed.password:
        raise ValueError(f"{service_name}: no incluyas credenciales en la URL base.")
    if _is_local_or_private_host(parsed.hostname or ""):
        raise ValueError(f"{service_name}: no se permiten hosts locales/privados.")

    cleaned = parsed._replace(query="", fragment="", params="")
    return urlunparse(cleaned).rstrip("/")


def sanitize_cookie_header(raw_cookie: Optional[str]) -> Optional[str]:
    """
    Best-effort sanitizer for manual/browser cookie headers.

    - Rejects CR/LF to prevent header injection.
    - Keeps only well-formed `name=value` cookie pairs.
    """
    if raw_cookie is None:
        return None

    data = raw_cookie.strip()
    if not data:
        return None
    if "\r" in data or "\n" in data:
        return None

    clean_parts: list[str] = []
    for raw_part in data.split(";"):
        part = raw_part.strip()
        if not part or "=" not in part:
            continue

        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()

        # Cookie name token validation (RFC 6265-ish).
        if not name or not re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", name):
            continue
        if any(ord(ch) < 32 for ch in value):
            continue

        clean_parts.append(f"{name}={value}")

    if not clean_parts:
        return None
    return "; ".join(clean_parts)


def consent_banner() -> None:
    st.caption(
        "🔒 Privacidad: La app corre localmente. "
        "Si activas Jira por cookies: “Se leerán cookies locales del navegador solo para autenticar tu sesión personal hacia Jira. "
        "No se envían a terceros.”"
    )
