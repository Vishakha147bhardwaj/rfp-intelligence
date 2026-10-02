"""Decide what role each file plays in a bid (doc_type), using rules from config."""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from rfp.schemas.documents import DocType

# detector.py -> ingestion -> rfp -> src -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RULES_PATH = PROJECT_ROOT / "config" / "doc_types.yaml"


@dataclass
class Detection:
    doc_type: DocType
    addendum_number: int | None
    matched_by: str  # why this type was chosen: "file_type", "filename", "title_text", "default"


def load_rules(path: Path = DEFAULT_RULES_PATH) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def detect_file_type(path: Path) -> str | None:
    """Return 'pdf' or 'html' from the extension, or None if unsupported."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in (".html", ".htm"):
        return "html"
    return None


def find_addendum_number(text: str, patterns: list[str]) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _any_match(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _build(doc_type: DocType, name: str, head: str, rules: dict, matched_by: str) -> Detection:
    number = None
    if doc_type == DocType.ADDENDUM:
        patterns = rules.get("addendum_number_patterns", [])
        number = find_addendum_number(name, patterns) or find_addendum_number(head, patterns)
    return Detection(doc_type, number, matched_by)


def detect_doc_type(
    file_name: str,
    file_type: str,
    first_page_text: str = "",
    rules: dict | None = None,
) -> Detection:
    rules = rules or load_rules()
    name = file_name.lower()
    head = first_page_text[: rules.get("title_window_chars", 400)].lower()

    # Pass 1: file type and file name
    for rule in rules["rules"]:
        doc_type = DocType(rule["doc_type"])
        if file_type in rule.get("file_types", []):
            return _build(doc_type, name, head, rules, "file_type")
        if _any_match(rule.get("filename_patterns", []), name):
            return _build(doc_type, name, head, rules, "filename")

    # Pass 2: the title area of the first page
    for rule in rules["rules"]:
        doc_type = DocType(rule["doc_type"])
        if _any_match(rule.get("title_patterns", []), head):
            return _build(doc_type, name, head, rules, "title_text")

    return Detection(DocType(rules.get("default", "other")), None, "default")