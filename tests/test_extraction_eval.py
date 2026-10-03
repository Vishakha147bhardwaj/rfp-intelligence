"""The extraction scorer must catch wrong values, not just reward right ones."""

import importlib.util
from pathlib import Path

_path = Path(__file__).parents[1] / "eval" / "run_extraction_eval.py"
_spec = importlib.util.spec_from_file_location("extraction_eval", _path)
ee = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ee)


def test_wrong_date_is_detected():
    score, detail = ee.score_field(
        {"datetime": "July 9, 2024 2:00 PM"}, "June 27, 2024 2:00 PM"
    )
    assert score < 1 and "2024-07-09" in detail


def test_reformatted_date_still_counts():
    assert (
        ee.score_field({"datetime": "July 9, 2024 2:00 PM"}, "07/09/2024 at 14:00 CST")[
            0
        ]
        == 1.0
    )


def test_missing_list_item_is_partial():
    score, detail = ee.score_field({"list": ["210-BLYZ", "340-DMMK"]}, ["210-BLYZ"])
    assert score == 0.5 and "340-DMMK" in detail


def test_keyword_alternatives():
    assert (
        ee.score_field({"keywords": ["eMMA|eMaryland"]}, "via eMaryland Marketplace")[0]
        == 1.0
    )


def test_invented_value_scores_zero():
    assert ee.score_field({"keywords": ["10 days"]}, "Net 30")[0] == 0.0
