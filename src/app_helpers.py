# src/app_helpers.py
import base64
import logging
import os

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from starlette.requests import Request

from src.path_confinement import is_inside

logger = logging.getLogger(__name__)

def read_if_exists(path: str) -> str:
    """Read file if it exists, return empty string otherwise."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

def file_to_data_url(path: str, mime: str) -> str:
    """Convert file to data URL."""
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"

def abs_join(base_dir: str, rel: str) -> str:
    """Join paths and return absolute path."""
    return os.path.abspath(os.path.join(base_dir, rel))

def serve_html_with_nonce(request: Request, file_path: str) -> HTMLResponse:
    """Read an app-bundled HTML page and inject the CSP nonce into inline <script> tags.

    Callers pass fixed, server-owned template paths (index/login/backgrounds),
    never a client-supplied path. So any read failure here — a missing file
    (broken deployment) or a permission/IO error — is a server fault, not a
    client "not found": map all of them to a logged 500 so a missing core
    template surfaces in 5xx alerting instead of hiding behind a 404. If a
    future caller serves a client-influenced path where 404 is correct, branch
    that at the call site rather than defaulting this shared helper to 404.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            html = f.read()
    except OSError:
        logger.exception("Failed to read page %s", file_path)
        raise HTTPException(500, "Internal server error")
    nonce = getattr(request.state, "csp_nonce", "")
    html = html.replace("{{CSP_NONCE}}", nonce)
    return HTMLResponse(apply_brand(html))


def apply_brand(html: str) -> str:
    """Swap the display name in a served page and expose it to the client."""
    from html import escape
    from src.constants import BRAND_NAME, DEFAULT_BRAND_NAME

    if BRAND_NAME != DEFAULT_BRAND_NAME:
        if BRAND_NAME.lower().endswith("chat"):
            html = html.replace(f"{DEFAULT_BRAND_NAME} Chat", BRAND_NAME)
        html = html.replace(DEFAULT_BRAND_NAME, BRAND_NAME)
    meta = f'<meta name="app-brand" content="{escape(BRAND_NAME, quote=True)}">'
    return html.replace("<head>", "<head>\n  " + meta, 1)


def inside_base_dir(base_dir: str, path: str) -> bool:
    """Check if path is inside base directory."""
    return is_inside(base_dir, path)
