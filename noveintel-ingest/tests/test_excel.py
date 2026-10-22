import pytest

from noveintel_ingest.excel import read_workbook


def test_header_found_below_a_merged_title(messy_xlsx):
    orders = read_workbook(messy_xlsx).sheet("Orders")
    assert orders.header_row == 3
    assert orders.header == ["Order ID", "Date", "Region", "Column D", "Region (2)"]


def test_values_cleaned_and_empty_and_repeated_header_rows_dropped(messy_xlsx):
    rows = read_workbook(messy_xlsx).sheet("Orders").rows
    assert [r.number for r in rows] == [4, 5, 8, 9]
    first, second, third, _ = rows
    assert first.values == {"Order ID": 42, "Date": "2024-03-01", "Region": "North", "Column D": 18500, "Region (2)": "N1"}
    assert second.values["Date"] == "2024-03-02T14:30:00"
    assert second.values["Column D"] == 99.5
    assert third.values["Region"] == "East"


def test_merged_value_applies_to_every_row_it_covers(messy_xlsx):
    rows = read_workbook(messy_xlsx).sheet("Orders").rows
    assert rows[-1].values["Region"] == "East"


def test_hidden_sheets_kept_and_flagged_unless_excluded(messy_xlsx):
    wb = read_workbook(messy_xlsx)
    assert [(s.name, s.hidden) for s in wb.sheets] == [("Orders", False), ("Hidden notes", True)]
    assert [s.name for s in read_workbook(messy_xlsx, include_hidden=False).sheets] == ["Orders"]


def test_header_whitespace_collapsed(faq_xlsx):
    assert "الصيغة المقترحة" in read_workbook(faq_xlsx).sheet("FAQs").header


def test_unsupported_file_type_refused(tmp_path):
    path = tmp_path / "legacy.xls"
    path.write_bytes(b"")
    with pytest.raises(ValueError, match="unsupported file type"):
        read_workbook(path)


def test_unknown_sheet_names_the_ones_there(faq_xlsx):
    with pytest.raises(KeyError, match="FAQs"):
        read_workbook(faq_xlsx).sheet("nope")
