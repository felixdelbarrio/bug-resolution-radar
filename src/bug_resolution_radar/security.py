from __future__ import annotations

import re
import streamlit as st

SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(authorization:)(\s*)(.+)"),
    re.compile(r"(?i)(cookie:)(\s*)(.+)"),
    re.compile(r"(?i)(token)(\s*[:=]\s*)([^\s]+)"),
]

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

def consent_banner() -> None:
    st.caption(
        "🔒 Privacidad: La app corre localmente. "
        "Si activas Jira por cookies: “Se leerán cookies locales del navegador solo para autenticar tu sesión personal hacia Jira. "
        "No se envían a terceros.”"
    )
