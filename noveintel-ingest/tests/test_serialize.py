from noveintel_ingest.excel import Row, Sheet, read_workbook
from noveintel_ingest.serialize import chunk_workbook, row_chunks


def _sheet(rows, hidden=False):
    header = list(rows[0].values) if rows else []
    return Sheet(name="Orders", hidden=hidden, header=header, header_row=1, rows=rows)


def test_each_value_carries_its_column_name(messy_xlsx):
    chunks, _ = chunk_workbook(read_workbook(messy_xlsx), "sales")
    assert chunks[0].text == (
        "Document: sales | Sheet: Orders | Order ID: 42 | Date: 2024-03-01 | Region: North | "
        "Column D: 18500 | Region (2): N1"
    )


def test_empty_cells_skipped_whitespace_collapsed_fields_kept_raw():
    row = Row(number=7, values={"Question": "كيف\nأتابع  طلبي؟", "Notes": None, "Answer": "عبر تم"})
    row.values = {k: v for k, v in row.values.items() if v is not None}
    [chunk] = row_chunks("faq", _sheet([row]), row)
    assert chunk.text == "Document: faq | Sheet: Orders | Question: كيف أتابع طلبي؟ | Answer: عبر تم"
    assert chunk.fields["Question"] == "كيف\nأتابع  طلبي؟"
    assert chunk.metadata["columns"] == ["Question", "Answer"]
    assert chunk.row_number == 7


def test_excluded_columns_are_stored_but_not_embedded():
    row = Row(number=2, values={"#": 54, "Question": "سؤال", "Notes": "تم التعديل"})
    [chunk] = row_chunks("faq", _sheet([row]), row, exclude_columns=["#", "Notes"])
    assert chunk.text == "Document: faq | Sheet: Orders | Question: سؤال"
    assert chunk.fields == {"#": 54, "Question": "سؤال", "Notes": "تم التعديل"}


def test_long_row_split_on_its_longest_field_with_context_in_every_part():
    long_answer = " ".join(f"كلمة{i}" for i in range(600))
    row = Row(number=3, values={"Question": "سؤال طويل", "Answer": long_answer, "Service": "التسجيل"})
    chunks = row_chunks("faq", _sheet([row]), row, max_chars=1000)
    assert len(chunks) > 1
    for i, chunk in enumerate(chunks, 1):
        assert len(chunk.text) <= 1000
        assert "Question: سؤال طويل" in chunk.text and "Service: التسجيل" in chunk.text
        assert f"Answer (part {i}/{len(chunks)}): " in chunk.text
        assert (chunk.part, chunk.parts) == (i, len(chunks))
    rebuilt = " ".join(c.text.split(f"(part {c.part}/{c.parts}): ")[1].split(" | ")[0] for c in chunks)
    assert rebuilt == long_answer


def test_duplicate_rows_folded_and_ids_independent_of_position():
    a = Row(number=2, values={"Q": "x", "A": "y"})
    b = Row(number=3, values={"Q": "x", "A": "y"})
    c = Row(number=4, values={"Q": "z", "A": "w"})
    from noveintel_ingest.excel import Workbook

    chunks, duplicates = chunk_workbook(Workbook(path=None, sheets=[_sheet([a, b, c])]), "doc")
    assert duplicates == 1 and [ch.row_number for ch in chunks] == [2, 4]
    moved = Row(number=40, values={"Q": "z", "A": "w"})
    assert row_chunks("doc", _sheet([moved]), moved)[0].id == chunks[1].id


def test_tatweel_removed_from_the_embedded_text_only():
    row = Row(number=2, values={"Question": "مؤمـن عليـه لديـه مـدة خدمـة"})
    [chunk] = row_chunks("faq", _sheet([row]), row)
    assert chunk.text.endswith("Question: مؤمن عليه لديه مدة خدمة")
    assert chunk.fields["Question"] == "مؤمـن عليـه لديـه مـدة خدمـة"
