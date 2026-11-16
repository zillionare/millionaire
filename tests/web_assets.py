"""Inspect page-owned script assets after they move out of inline Python strings."""

from html.parser import HTMLParser
from pathlib import Path


def script_sources(html):
    root = Path(__file__).resolve().parents[1] / "quantide/web/static"
    scripts = []

    class Parser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            source = dict(attrs).get("src", "")
            if tag == "script" and source.startswith("/static/"):
                path = root / source.removeprefix("/static/")
                assert path.is_relative_to(root)
                assert path.is_file(), f"Page references a missing script: {source}"
                scripts.append(path.read_text(encoding="utf-8"))

    Parser().feed(html)
    return "\n".join(scripts)
