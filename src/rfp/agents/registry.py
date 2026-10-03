"""Load field definitions from config/fields.yaml."""

from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import yaml

from rfp.schemas.agents import FieldSpec
from rfp.settings import PROJECT_ROOT

FIELDS_PATH = PROJECT_ROOT / "config" / "fields.yaml"


@lru_cache
def load_registry(
    path: Path = FIELDS_PATH,
) -> tuple[dict[str, str], tuple[FieldSpec, ...]]:
    """Return (group name -> description, all field specs in file order)."""
    data = yaml.safe_load(path.read_text())
    groups = data["groups"]
    specs = tuple(FieldSpec(**item) for item in data["fields"])
    unknown = {s.group for s in specs} - set(groups)
    if unknown:
        raise ValueError(f"fields.yaml: unknown group(s) {unknown}")
    return groups, specs


def extractable_fields() -> list[FieldSpec]:
    return [s for s in load_registry()[1] if not s.generated]


def fields_by_group() -> dict[str, list[FieldSpec]]:
    grouped: dict[str, list[FieldSpec]] = defaultdict(list)
    for spec in extractable_fields():
        grouped[spec.group].append(spec)
    return dict(grouped)


def field_names() -> list[str]:
    return [s.name for s in load_registry()[1]]
