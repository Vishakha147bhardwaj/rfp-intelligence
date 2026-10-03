from rfp.ingestion.pdf_parser import _is_layout_table, _join_cell_lines, _normalise_rows


def test_wrapped_email_is_not_split():
    assert (
        _join_cell_lines("thawkins@treasurer.state.md\n.us")
        == "thawkins@treasurer.state.md.us"
    )


def test_wrapped_url_is_not_split():
    cell = "https://doit.maryland.gov/hardware_co\nntract/hwmercury_affidavit.pdf"
    assert (
        _join_cell_lines(cell)
        == "https://doit.maryland.gov/hardware_contract/hwmercury_affidavit.pdf"
    )


def test_normal_wrap_gets_a_space():
    assert (
        _join_cell_lines("Delivery within\n45 days of Award")
        == "Delivery within 45 days of Award"
    )


def test_empty_columns_are_dropped():
    rows = [
        [None, "PORFP Number:", None, "#E20P4600040"],
        [None, "PORFP Type:", "", "Fixed Price"],
    ]
    assert _normalise_rows(rows) == [
        ["PORFP Number:", "#E20P4600040"],
        ["PORFP Type:", "Fixed Price"],
    ]


def test_single_column_box_is_layout():
    assert _is_layout_table(
        [["LENGTH OF CONTRACT"], ["The term of this proposal shall be..."]]
    )


def test_short_key_value_table_is_data():
    assert not _is_layout_table(
        [["PORFP Number:", "#E20P4600040"], ["PORFP Type:", "Fixed Price"]]
    )


def test_list_item_after_url_gets_a_space():
    cell = "https://doit.maryland.gov/hwmercury_affidavit.pdf\n9. Delivery within 45 days of Award."
    assert _join_cell_lines(cell).endswith(
        "affidavit.pdf 9. Delivery within 45 days of Award."
    )


def test_sparse_form_table_is_layout():
    rows = [
        ["Agency POC Name:", "", "", "Tamaira Hawkins", "", "410-260-7533"],
        ["", "", "", "", "Phone Number:", ""],
    ]
    assert _is_layout_table(rows)
