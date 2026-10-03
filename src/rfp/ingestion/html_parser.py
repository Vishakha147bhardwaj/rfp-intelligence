"""Parse a bid portal HTML page into one Page of 'label: value' lines grouped by section."""

import re
from pathlib import Path

import structlog
import yaml
from bs4 import BeautifulSoup

from rfp.schemas.documents import Page

log = structlog.get_logger()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RULES_PATH = PROJECT_ROOT / "config" / "html_rules.yaml"
NUMBERED_ITEM = re.compile(
    r"\s+(?=\d{1,2}\.\s+[A-Z])"
)  # split "... 1. Foo 2. Bar" into lines
TRUNCATION_NOTE = " [truncated on portal page]"


def load_rules(path: Path = DEFAULT_RULES_PATH) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def _text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


def _title(soup: BeautifulSoup, rules: dict) -> str:
    title = _text(soup.title)
    for pattern in rules.get("title_strip_patterns", []):
        title = re.sub(pattern, "", title, flags=re.IGNORECASE)
    return title.strip(" -|")


def _field_lines(soup: BeautifulSoup, rules: dict) -> tuple[list[str], list[str]]:
    """Return (lines, section titles). Unlabeled values are grouped under their section."""
    field_sel, section_sel = rules["field_selector"], rules["section_selector"]
    lines: list[str] = []
    sections: list[str] = []
    section = "Info"
    unlabeled: list[str] = []

    def flush() -> None:
        if unlabeled:
            lines.append(f"{section}: " + " | ".join(unlabeled))
            unlabeled.clear()

    for el in soup.select(f"{section_sel}, {field_sel}"):
        if el.css.match(section_sel):
            flush()
            section = _text(el)
            sections.append(section)
            lines += ["", f"## {section}"]
            continue
        if el.select_one(
            field_sel
        ):  # a container of other fields: skip, keep innermost
            continue
        label = _text(el.select_one(rules["label_selector"])).rstrip(":")
        value = _text(el.select_one(rules["value_selector"]))
        for marker in rules.get("truncation_markers", []):
            value = re.sub(marker, TRUNCATION_NOTE, value, flags=re.IGNORECASE)
        if not value:
            continue
        if label:
            flush()
            lines.append(f"{label}: " + NUMBERED_ITEM.sub("\n", value))
        else:
            unlabeled.append(value)
    flush()
    return lines, sections


def _table_lines(soup: BeautifulSoup) -> list[str]:
    lines = []
    for row in soup.select("table tr"):
        cells = [c for c in (_text(td) for td in row.find_all(["th", "td"])) if c]
        if len(cells) == 2:
            lines.append(f"{cells[0].rstrip(':')}: {cells[1]}")
        elif cells:
            lines.append(" | ".join(cells))
    return lines


def _dl_lines(soup: BeautifulSoup) -> list[str]:
    lines = []
    for dt in soup.select("dl dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            lines.append(f"{_text(dt).rstrip(':')}: {_text(dd)}")
    return lines


def _fallback_text(soup: BeautifulSoup, rules: dict) -> str:
    for selector in rules.get("noise_selectors", []):
        for el in soup.select(selector):
            el.decompose()
    body = soup.body or soup
    return body.get_text("\n", strip=True)


def parse_html(path: Path, rules: dict | None = None) -> tuple[list[Page], list[str]]:
    """Return (pages, errors). An HTML file becomes a single Page. Never raises."""
    rules = rules or load_rules()
    try:
        soup = BeautifulSoup(path.read_text(errors="ignore"), "lxml")
    except Exception as exc:
        log.error("html_read_failed", file=path.name, error=str(exc))
        return [], [f"Could not read HTML: {exc}"]

    title = _title(soup, rules)
    field_lines, sections = _field_lines(soup, rules)
    lines = field_lines + _table_lines(soup) + _dl_lines(soup)

    if sum(1 for l in lines if ":" in l) < rules.get("min_structured_lines", 3):
        log.warning("html_no_structured_fields", file=path.name)
        body_text = _fallback_text(soup, rules)
    else:
        body_text = "\n".join(lines).strip()

    text = f"# {title}\n\n{body_text}" if title else body_text
    page = Page(
        page_number=1,
        text=text,
        headings=[h for h in [title, *sections] if h],
        is_empty=not body_text.strip(),
    )
    return [page], []
