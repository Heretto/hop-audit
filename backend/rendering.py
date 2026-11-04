"""HTML from the Jinja templates in `templates/`, and the brand assets they
embed (data URIs, so a rendered page needs nothing but its fonts)."""

import base64
import mimetypes
from functools import cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]))


@cache
def asset(name: str) -> str:
    """An asset in `assets/` as a data URI."""
    path = ASSETS / name
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def render(template: str, **context) -> str:
    return env.get_template(template).render(**context)
