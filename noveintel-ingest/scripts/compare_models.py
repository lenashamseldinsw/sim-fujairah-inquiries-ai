"""
Compare the approved embedding models on a FAQ workbook.

    uv run python scripts/compare_models.py "الاسئلة الشائعة.xlsx" scripts/adpf_faq_queries.json

Two tasks, on the visible FAQ sheet only (hidden drafts would make the gold rows
ambiguous):

* **A · question → answer.** Each FAQ's own question is the query; the corpus is
  every row serialised *without* the question column, so a hit means the model
  matched a question to its answer, not to its own text.
* **B · customer phrasing → stored row.** Hand-written colloquial queries against
  the rows exactly as ingested. Its unanswerable queries measure whether the top
  score separates "an FAQ answers this" from "none does" (AUC, and the best single
  threshold), which is what any case → FAQ matching would rest on.

Each model is scored at its native size and at the stored size (truncated and
re-normalised), and Qwen3 with and without its query instruction. Vectors are
cached beside the query file's name in --cache, so re-scoring costs nothing.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from noveintel_ingest.embed import DEFAULT_QUERY_TASK, Core42Embedder, EmbeddingError
from noveintel_ingest.excel import read_workbook
from noveintel_ingest.faq import find_faq_columns
from noveintel_ingest.ingest import default_document_id
from noveintel_ingest.serialize import normalize_text, row_chunks
from noveintel_ingest.settings import ALLOWED_EMBEDDING_MODELS, NATIVE_DIMENSIONS


def _fit(v: np.ndarray, d: int) -> np.ndarray:
    v = v[:, :d]
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def _ranks(sim: np.ndarray, gold: list[set[int]]) -> np.ndarray:
    """1-based rank of the best-placed gold column for each query row."""
    order = np.argsort(-sim, axis=1)
    out = []
    for i, g in enumerate(gold):
        out.append(next(r for r, j in enumerate(order[i], 1) if j in g))
    return np.array(out)


def _metrics(ranks: np.ndarray) -> dict[str, float]:
    return {
        "hit@1": float(np.mean(ranks <= 1)),
        "hit@3": float(np.mean(ranks <= 3)),
        "hit@5": float(np.mean(ranks <= 5)),
        "mrr": float(np.mean(1 / ranks)),
    }


def _auc(pos: np.ndarray, neg: np.ndarray) -> float:
    return float(np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg]))


def _best_threshold(pos: np.ndarray, neg: np.ndarray) -> tuple[float, float]:
    best = (0.0, 0.0)
    for t in np.unique(np.concatenate([pos, neg])):
        acc = (np.sum(pos >= t) + np.sum(neg < t)) / (len(pos) + len(neg))
        if acc > best[1]:
            best = (float(t), float(acc))
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("workbook")
    ap.add_argument("queries")
    ap.add_argument("--dimensions", type=int, default=1024, help="The stored size to score besides native")
    ap.add_argument("--cache", default=".compare_cache")
    ap.add_argument("--out", help="Write the scores as JSON here")
    ap.add_argument("--models", nargs="+", default=list(ALLOWED_EMBEDDING_MODELS),
                    help="Embed only these; models already cached are scored regardless")
    args = ap.parse_args()

    spec = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    sheet = read_workbook(args.workbook).sheet(spec.get("sheet", "FAQs"))
    question_col = find_faq_columns(sheet)["question_ar"]
    doc = default_document_id(args.workbook)
    rows = [r for r in sheet.rows if r.values.get(question_col)]
    row_index = {r.number: i for i, r in enumerate(rows)}

    corpus_full = [row_chunks(doc, sheet, r)[0].text for r in rows]
    corpus_noq = [row_chunks(doc, sheet, r, exclude_columns=[question_col])[0].text for r in rows]
    questions = [normalize_text(r.values[question_col]) for r in rows]
    answerable = [normalize_text(a["q"]) for a in spec["answerable"]]
    gold_b = [{row_index[n] for n in a["gold"]} for a in spec["answerable"]]
    unanswerable = [normalize_text(q) for q in spec["unanswerable"]]

    cache = Path(args.cache)
    cache.mkdir(exist_ok=True)
    results: dict[str, dict] = {}
    for model in ALLOWED_EMBEDDING_MODELS:
        path = cache / f"{model}.npz"
        native = NATIVE_DIMENSIONS[model]
        if path.exists():
            v = dict(np.load(path))
            elapsed = float(v.pop("elapsed"))
        elif model not in args.models:
            continue
        else:
            try:
                e = Core42Embedder(model, native)
                t = time.time()
                v = {
                    "corpus_full": e.embed_documents(corpus_full),
                    "corpus_noq": e.embed_documents(corpus_noq),
                    "questions_plain": e.embed_documents(questions),
                    "answerable_plain": e.embed_documents(answerable),
                    "unanswerable_plain": e.embed_documents(unanswerable),
                }
                if model.startswith("qwen3"):
                    # Batched, with the exact prefix embed_query sends.
                    instr = lambda qs, e=e: e.embed_documents([f"Instruct: {DEFAULT_QUERY_TASK}\nQuery:{q}" for q in qs])
                    v["questions_instr"] = instr(questions)
                    v["answerable_instr"] = instr(answerable)
                    v["unanswerable_instr"] = instr(unanswerable)
                elapsed = time.time() - t
                np.savez(path, elapsed=elapsed, **v)
            except EmbeddingError as exc:
                print(f"{model}: skipped — {exc}")
                continue
        modes = ["instr", "plain"] if model.startswith("qwen3") else ["plain"]
        for mode in modes:
            for dims in (native, args.dimensions):
                f = lambda k, v=v, dims=dims: _fit(v[k], dims)
                a = _ranks(f(f"questions_{mode}") @ f("corpus_noq").T, [{i} for i in range(len(rows))])
                pos_sim = f(f"answerable_{mode}") @ f("corpus_full").T
                b = _ranks(pos_sim, gold_b)
                pos = pos_sim.max(axis=1)
                neg = (f(f"unanswerable_{mode}") @ f("corpus_full").T).max(axis=1)
                threshold, accuracy = _best_threshold(pos, neg)
                key = f"{model} · {dims}d" + (
                    " · no instruction" if mode == "plain" and model.startswith("qwen3") else ""
                )
                results[key] = {
                    "A_question_to_answer": _metrics(a),
                    "B_customer_phrasing": _metrics(b),
                    "B_misses": [spec["answerable"][i]["q"] for i in np.where(b > 3)[0]],
                    "B_answerable_vs_not": {
                        "auc": _auc(pos, neg),
                        "best_threshold": round(threshold, 3),
                        "accuracy_at_threshold": accuracy,
                        "mean_top_score_answerable": float(pos.mean()),
                        "mean_top_score_unanswerable": float(neg.mean()),
                    },
                    "embed_seconds_all_texts": round(elapsed, 1),
                }

    print(
        f"{len(rows)} FAQ rows · task A {len(rows)} queries · task B {len(answerable)} + {len(unanswerable)} unanswerable\n"
    )
    header = f"{'variant':<48} {'A@1':>5} {'A@5':>5} {'A mrr':>6} │ {'B@1':>5} {'B@3':>5} {'B@5':>5} {'B mrr':>6} │ {'AUC':>5} {'thr':>5} {'acc':>5}"
    print(header)
    print("─" * len(header))
    for key, r in results.items():
        a, b, s = r["A_question_to_answer"], r["B_customer_phrasing"], r["B_answerable_vs_not"]
        print(
            f"{key:<48} {a['hit@1']:>5.2f} {a['hit@5']:>5.2f} {a['mrr']:>6.3f} │ {b['hit@1']:>5.2f} {b['hit@3']:>5.2f} "
            f"{b['hit@5']:>5.2f} {b['mrr']:>6.3f} │ {s['auc']:>5.2f} {s['best_threshold']:>5.2f} {s['accuracy_at_threshold']:>5.2f}"
        )
    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
