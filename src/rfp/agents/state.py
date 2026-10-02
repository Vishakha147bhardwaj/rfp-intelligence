"""Shared state for the extraction graph. Reducers define how parallel updates merge."""

import operator
from typing import Annotated, Any, TypedDict

from rfp.schemas.agents import AddendumChange, BidRecord, FieldResult, FieldValidation


def merge(left: dict, right: dict) -> dict:
    """Combine dict updates from parallel branches instead of overwriting."""
    return {**(left or {}), **(right or {})}


class BidState(TypedDict, total=False):
    run_id: str
    bid_id: str
    groups: list[str]                                          # the plan
    results: Annotated[dict[str, FieldResult], merge]          # field -> current value
    validations: Annotated[dict[str, FieldValidation], merge]  # field -> latest validation
    retry_counts: Annotated[dict[str, int], merge]             # field -> retries used
    to_validate: list[str] | None                              # None = all fields
    addendum_changes: Annotated[dict[str, AddendumChange], merge]
    record: BidRecord | None                                   # final output
    trace: Annotated[list[dict[str, Any]], operator.add]       # one event per agent step
    errors: Annotated[list[str], operator.add]


class GroupTask(TypedDict):
    """Input for one parallel extraction branch."""

    run_id: str
    bid_id: str
    group: str