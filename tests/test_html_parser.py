from rfp.ingestion.html_parser import parse_html

BIDNET_LIKE = """
<html><head><title>Laptops RFP - Bid Information - {3} | BidNet Direct</title></head><body>
<div class="mets-field"><span class="mets-field-label">Solicitation Number</span>
  <div class="mets-field-body">JA-207652</div></div>
<h3 class="content-block-sub-title">Dates</h3>
<div class="mets-field"><span class="mets-field-label">Closing Date</span>
  <div class="mets-field-body">07/09/2024 03:00 PM EDT</div></div>
<h3 class="content-block-sub-title">Contact Information</h3>
<div class="mets-field"><div class="mets-field-body">Tamaira Hawkins</div></div>
<div class="mets-field"><div class="mets-field-body">410-260-7533</div></div>
<div class="mets-field"><span class="mets-field-label">Description</span>
  <div class="mets-field-body">1. Dell Latitude 5550 qty 30 2. Dell Thunderbolt Dock</div></div>
</body></html>
"""


def _parse(tmp_path, html):
    f = tmp_path / "page.html"
    f.write_text(html)
    pages, errors = parse_html(f)
    assert errors == [] and len(pages) == 1
    return pages[0]


def test_title_is_cleaned(tmp_path):
    page = _parse(tmp_path, BIDNET_LIKE)
    assert page.text.startswith("# Laptops RFP\n")
    assert page.headings[0] == "Laptops RFP"


def test_label_value_and_sections(tmp_path):
    text = _parse(tmp_path, BIDNET_LIKE).text
    assert "Solicitation Number: JA-207652" in text
    assert "## Dates\nClosing Date: 07/09/2024 03:00 PM EDT" in text


def test_unlabeled_values_grouped_under_section(tmp_path):
    text = _parse(tmp_path, BIDNET_LIKE).text
    assert "Contact Information: Tamaira Hawkins | 410-260-7533" in text


def test_numbered_description_split_into_lines(tmp_path):
    text = _parse(tmp_path, BIDNET_LIKE).text
    assert "Description: 1. Dell Latitude 5550 qty 30\n2. Dell Thunderbolt Dock" in text


def test_table_fallback(tmp_path):
    html = """<html><body><table>
      <tr><th>Bid Number</th><td>ABC-1</td></tr>
      <tr><th>Due Date</th><td>01/01/2025</td></tr>
      <tr><th>Bond</th><td>5%</td></tr></table></body></html>"""
    text = _parse(tmp_path, html).text
    assert "Bid Number: ABC-1" in text and "Bond: 5%" in text


def test_plain_page_uses_full_text(tmp_path):
    html = "<html><body><script>x=1</script><p>Bids due Friday at noon.</p></body></html>"
    text = _parse(tmp_path, html).text
    assert "Bids due Friday at noon." in text and "x=1" not in text

def test_see_more_marked_as_truncated(tmp_path):
    html = """<html><head><title>X</title></head><body>
    <div class="mets-field"><span class="mets-field-label">Description</span>
      <div class="mets-field-body">Each submission must include a d See more</div></div>
    <div class="mets-field"><span class="mets-field-label">Bid</span><div class="mets-field-body">1</div></div>
    <div class="mets-field"><span class="mets-field-label">Due</span><div class="mets-field-body">2</div></div>
    </body></html>"""
    text = _parse(tmp_path, html).text
    assert "Description: Each submission must include a d [truncated on portal page]" in text
    assert "See more" not in text