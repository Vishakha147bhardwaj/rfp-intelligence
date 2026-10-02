from rfp.agents.registry import extractable_fields, field_names, fields_by_group, load_registry


def test_twenty_unique_fields():
    names = field_names()
    assert len(names) == 20
    assert len(set(names)) == 20


def test_required_assignment_fields_present():
    required = {"Bid Number", "Title", "Due Date", "Bid Submission Type", "Term of Bid",
                "Pre Bid Meeting", "Installation", "Bid Bond Requirement", "Delivery Date",
                "Payment Terms", "Any Additional Documentation Required", "MFG for Registration",
                "Contract or Cooperative to use", "Model_no", "Part_no", "Product", "contact_info",
                "company_name", "Bid Summary", "Product Specification"}
    assert set(field_names()) == required


def test_every_extracted_field_has_queries():
    assert all(spec.queries for spec in extractable_fields())


def test_three_groups_cover_all_extracted_fields():
    groups, _ = load_registry()
    by_group = fields_by_group()
    assert set(by_group) == set(groups)
    assert sum(len(v) for v in by_group.values()) == 19     # 20 minus generated Bid Summary