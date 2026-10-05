"""
English translation of the report: the defect that emptied every English table.

A table's column names are both values (the ``columns`` list) and keys (every row).
The translation prompt translates values and forbids renaming keys, so the model
returned English columns over rows still keyed in Arabic, and the English builder —
looking each cell up by column name — printed a table of blanks. On a real run 181 of
214 English table cells came out empty. These pin the deterministic repair.
"""
from __future__ import annotations

from noveintel_inquiries.stages.translate_report_en import _rekey_translated_tables

AR = {
    "title": "القسم",
    "tables": [{"columns": ["المصدر", "الحجم"], "rows": [{"المصدر": "تحليل", "الحجم": "11"}]}],
    "subsections": [
        {"tables": [{"columns": ["النوع", "العدد"], "rows": [{"النوع": "شكوى", "العدد": "9"}]}]}
    ],
}


def translated():
    """What the model actually returns: English columns, Arabic row keys."""
    return {
        "title": "Section",
        "tables": [{"columns": ["Source", "Volume"], "rows": [{"المصدر": "Analysis", "الحجم": "11"}]}],
        "subsections": [
            {"tables": [{"columns": ["Type", "Count"], "rows": [{"النوع": "Complaint", "العدد": "9"}]}]}
        ],
    }


def test_rows_are_rekeyed_to_the_english_columns():
    en = translated()
    assert _rekey_translated_tables(AR, en) == 2
    assert en["tables"][0]["rows"] == [{"Source": "Analysis", "Volume": "11"}]


def test_nested_tables_are_reached():
    en = translated()
    _rekey_translated_tables(AR, en)
    assert en["subsections"][0]["tables"][0]["rows"] == [{"Type": "Complaint", "Count": "9"}]


def test_every_column_can_be_looked_up_afterwards():
    """The property the English builder relies on."""
    en = translated()
    _rekey_translated_tables(AR, en)
    for table in en["tables"] + en["subsections"][0]["tables"]:
        for row in table["rows"]:
            assert all(column in row for column in table["columns"])


def test_rows_already_keyed_in_english_are_left_alone():
    en = translated()
    en["tables"][0]["rows"] = [{"Source": "Analysis", "Volume": "11"}]
    _rekey_translated_tables(AR, en)
    assert en["tables"][0]["rows"] == [{"Source": "Analysis", "Volume": "11"}]


def test_a_changed_structure_is_left_untouched():
    """If the model dropped or added a table, pairing by position would put values
    under the wrong headings. An empty cell is the lesser harm."""
    en = translated()
    del en["subsections"]
    before = repr(en)
    assert _rekey_translated_tables(AR, en) == 0
    assert repr(en) == before


def test_a_column_count_mismatch_skips_only_that_table():
    en = translated()
    en["tables"][0]["columns"] = ["Source"]
    assert _rekey_translated_tables(AR, en) == 1
    assert en["subsections"][0]["tables"][0]["rows"] == [{"Type": "Complaint", "Count": "9"}]
