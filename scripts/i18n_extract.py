#!/usr/bin/env python3
"""Collect English UI strings for the runtime translation layer (static/js/i18n.js).

Sources: static HTML pages, UI-looking string literals in static JS (including
text between tags inside HTML template strings) and HTTPException details in
the backend. Template placeholders (${...} in JS, {...} in f-strings) become
{0}, {1}, ... so i18n.js can match them as patterns.

Writes static/i18n/strings.json (sorted list). Re-run after upstream syncs, then
translate the new keys into static/i18n/<lang>.json.
"""
from __future__ import annotations

import glob
import json
import os
import re
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "static", "i18n", "strings.json")

UI_ATTRS = {"title", "placeholder", "aria-label", "alt", "data-tooltip"}
WORD = re.compile(r"[A-Za-z]{2,}")
CODEY = re.compile(
    r"^[\w.-]+$(?<=[a-z0-9_-])|[{};=<>`\\]|https?://|^#|^\.|^/|\b(px|rem|var\(|rgba?\(|calc\()|"
    r"^[a-z]+[A-Z]\w*$|^[A-Z0-9_]{3,}$|\.(js|css|py|json|png|svg|html)\b"
)


def _ui_text(s: str) -> bool:
    s = s.strip()
    if not (2 <= len(s) <= 160) or not WORD.search(s):
        return False
    if re.fullmatch(r"[A-Z][a-z]{1,20}[.!?…:]?", s):
        return True
    if CODEY.search(s):
        return False
    # Space-separated CSS class lists ("hwfit-loading cookbook-cached").
    if "-" in s and re.fullmatch(r"[a-z0-9 _-]+", s):
        return False
    # Needs a space, or a capitalised single word ("Save", "Settings").
    if " " not in s and not re.match(r"^[A-Z][a-z]+[.!?…:]?$", s):
        return False
    letters = sum(c.isalpha() for c in s)
    return letters >= len(s) * 0.5


class _HTMLText(HTMLParser):
    SKIP = {"script", "style", "code", "pre", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: set[str] = set()
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        for k, v in attrs:
            if k in UI_ATTRS and v and _ui_text(v):
                self.out.add(_norm(v))

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and _ui_text(data):
            self.out.add(_norm(data))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _placeholders(s: str, pattern: str) -> str:
    n = iter(range(100))
    return re.sub(pattern, lambda _m: "{%d}" % next(n), s)


def _from_markup(fragment: str, out: set[str]) -> None:
    p = _HTMLText()
    try:
        p.feed(fragment)
    except Exception:
        return
    out.update(p.out)


JS_STR = re.compile(r"""'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`""", re.S)


def _js_strings(path: str, out: set[str]) -> None:
    src = open(path, encoding="utf-8", errors="replace").read()
    for m in JS_STR.finditer(src):
        s = m.group(1) or m.group(2) or m.group(3) or ""
        if m.group(3) is not None:
            s = _placeholders(s, r"\$\{[^}]*\}")
        s = s.replace("\\'", "'").replace('\\"', '"').replace("\\n", " ")
        if "<" in s and ">" in s:
            _from_markup(re.sub(r"\{\d+\}", "{0}", s), out)
            continue
        if _ui_text(s):
            out.add(_norm(s))


PY_DETAIL = re.compile(r"""HTTPException\(\s*(?:status_code\s*=\s*)?\d+\s*,\s*(?:detail\s*=\s*)?(f?)(["'])(.+?)\2\s*[,)]""")
PY_EXTRA = [
    "Allow this task to continue?",
    "The approved bash action could not run",
    "The approved bash action could not run: {0}",
    "Approval fingerprint",
    "Approval fingerprint: {0}",
    "Effects: {0}",
    "Answered {0}",
    "Processing request",
    "Processing request - {0}",
    "View thinking process",
    "{0} recalled",
    "{0} pinned, {1} recalled",
    "Effects",
    "Answered",
    "Allow for this chat session",
    "Allow for this task",
    "Allow once",
    "Deny",
]


def _py_strings(out: set[str]) -> None:
    for path in glob.glob(os.path.join(ROOT, "routes", "**", "*.py"), recursive=True) + \
            glob.glob(os.path.join(ROOT, "src", "**", "*.py"), recursive=True):
        src = open(path, encoding="utf-8", errors="replace").read()
        for m in PY_DETAIL.finditer(src):
            s = m.group(3)
            if m.group(1):
                s = _placeholders(s, r"\{[^}]*\}")
            if _ui_text(s) and len(s) <= 160:
                out.add(_norm(s))
    out.update(PY_EXTRA)


def main() -> None:
    out: set[str] = set()
    for html in glob.glob(os.path.join(ROOT, "static", "*.html")):
        if "variants" in html:
            continue
        _from_markup(open(html, encoding="utf-8").read(), out)
    js_files = [os.path.join(ROOT, "static", "app.js")] + glob.glob(os.path.join(ROOT, "static", "js", "**", "*.js"), recursive=True)
    for js in js_files:
        if os.sep + "lib" + os.sep in js:
            continue
        _js_strings(js, out)
    _py_strings(out)
    out = {s for s in out if not s.startswith("{0}") or len(s) > 4}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(sorted(out), f, ensure_ascii=False, indent=0)
    print(f"{len(out)} strings -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
