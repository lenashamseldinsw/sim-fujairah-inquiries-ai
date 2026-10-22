import numpy as np
import pytest

from noveintel_ingest.embed import EmbeddingError, HashEmbedder
from noveintel_ingest.ingest import default_document_id, ingest_workbook, search
from noveintel_ingest.store import StoreError

from .conftest import make_faq_workbook


class CountingEmbedder(HashEmbedder):
    def __init__(self, dimensions=128):
        super().__init__(dimensions)
        self.embedded: list[str] = []

    def embed_documents(self, texts):
        self.embedded.extend(texts)
        return super().embed_documents(texts)


class FailingEmbedder(HashEmbedder):
    def embed_documents(self, texts):
        raise EmbeddingError("no quota")


def test_ingests_every_sheet_with_provenance(store, faq_xlsx):
    report = ingest_workbook(faq_xlsx, collection="faq", store=store, embedder=CountingEmbedder())
    assert report.document_id == "الاسئلة الشائعة"
    assert [(s.name, s.hidden, s.rows) for s in report.sheets] == [("FAQs", False, 3), ("مسودة", True, 1)]
    assert (report.chunks, report.embedded, report.unchanged, report.deleted) == (4, 4, 0, 0)
    rows = store.rows("faq", "الاسئلة الشائعة")
    assert rows[0]["sheet"] == "FAQs" and rows[0]["row_number"] == 2
    assert list(rows[0]["fields"]) == ["CA Reviewed Arabic Question", "الصيغة المقترحة", "الإدارة المعنية", "الخدمة"]


def test_reingest_embeds_only_what_changed(store, tmp_path):
    path = make_faq_workbook(tmp_path / "faq.xlsx")
    ingest_workbook(path, collection="faq", store=store, embedder=CountingEmbedder())

    again = CountingEmbedder()
    report = ingest_workbook(path, collection="faq", store=store, embedder=again)
    assert (report.embedded, report.unchanged, report.deleted) == (0, 4, 0) and again.embedded == []

    # Reorder two rows, edit one answer, drop one row.
    make_faq_workbook(path, rows=[
        ("ما هو نظام الخصم المباشر؟", "نظام يهدف إلى تسهيل سداد الاشتراكات الشهرية.", "التحصيل والمتابعة", "تسجيل جهة عمل"),
        ("كيف يمكن للمؤمن عليه متابعة طلبه؟", "عبر منصة تم أو مراكز السعادة.", "معاشات المدنيين", "صرف المعاش التقاعدي"),
    ])
    edited = CountingEmbedder()
    report = ingest_workbook(path, collection="faq", store=store, embedder=edited)
    assert (report.embedded, report.unchanged, report.deleted) == (1, 2, 2)
    assert "مراكز السعادة" in edited.embedded[0]
    moved = {r["fields"]["CA Reviewed Arabic Question"]: r["row_number"] for r in store.rows("faq", "faq") if r["sheet"] == "FAQs"}
    assert moved == {"ما هو نظام الخصم المباشر؟": 2, "كيف يمكن للمؤمن عليه متابعة طلبه؟": 3}


def test_documents_in_one_collection_are_independent(store, tmp_path):
    a = make_faq_workbook(tmp_path / "a.xlsx")
    b = make_faq_workbook(tmp_path / "b.xlsx", rows=[("سؤال آخر", "جواب", "x", "y")])
    ingest_workbook(a, collection="faq", store=store, embedder=CountingEmbedder())
    ingest_workbook(b, collection="faq", store=store, embedder=CountingEmbedder())
    assert store.collections()[0]["documents"] == {"a": 4, "b": 2}
    assert store.delete_document("faq", "b") == 2
    assert store.collections()[0]["documents"] == {"a": 4}


def test_a_collection_never_mixes_models(store, faq_xlsx):
    ingest_workbook(faq_xlsx, collection="faq", store=store, embedder=CountingEmbedder(128))
    with pytest.raises(StoreError, match="local-hash vectors of 128"):
        ingest_workbook(faq_xlsx, collection="faq", store=store, embedder=CountingEmbedder(256))


def test_failed_embedding_leaves_no_collection_behind(store, faq_xlsx):
    with pytest.raises(EmbeddingError):
        ingest_workbook(faq_xlsx, collection="faq", store=store, embedder=FailingEmbedder(128))
    assert store.collection("faq") is None


def test_search_finds_the_row_and_can_skip_hidden_sheets(store, faq_xlsx):
    embedder = CountingEmbedder()
    ingest_workbook(faq_xlsx, collection="faq", store=store, embedder=embedder)
    [hit] = search("متابعة طلبه عبر منصة تم", collection="faq", k=1, store=store, embedder=embedder)
    assert hit.sheet == "FAQs" and hit.row_number == 2 and 0 < hit.score <= 1
    assert hit.fields["الخدمة"] == "صرف المعاش التقاعدي"
    hits = search("هل يمكنني إعادة التسجيل", collection="faq", k=10, store=store, embedder=embedder, include_hidden=False)
    assert all(h.sheet == "FAQs" for h in hits)
    assert search("x", collection="faq", sheet="مسودة", store=store, embedder=embedder)[0].sheet == "مسودة"


def test_search_refuses_another_models_vectors(store, faq_xlsx):
    ingest_workbook(faq_xlsx, collection="faq", store=store, embedder=CountingEmbedder(128))
    with pytest.raises(ValueError, match="embedded with local-hash at 128"):
        search("x", collection="faq", store=store, embedder=CountingEmbedder(256))


def test_collection_names_are_checked(store, faq_xlsx):
    with pytest.raises(StoreError, match="lowercase"):
        ingest_workbook(faq_xlsx, collection="faq; DROP TABLE x", store=store, embedder=CountingEmbedder())


def test_default_document_id_keeps_arabic_and_collapses_spaces():
    assert default_document_id("/x/الاسئلة الشائعة  .xlsx") == "الاسئلة الشائعة"


def test_vectors_round_trip_through_pgvector(store, faq_xlsx):
    embedder = CountingEmbedder()
    ingest_workbook(faq_xlsx, collection="faq", store=store, embedder=embedder)
    text = embedder.embedded[0]
    [hit] = store.search("faq", embedder.embed_documents([text])[0], k=1)
    assert hit.text == text and hit.score == pytest.approx(1.0, abs=1e-5)
    assert np.isfinite(hit.score)
