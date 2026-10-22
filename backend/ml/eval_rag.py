"""Retrieval benchmark for Sphura's document engine (RAG), mirroring the production retriever.

Corpus     ml/eval_corpus/*.md — 18 documents written for this benchmark (ML papers, finance reports, history,
           science, product docs, an HR policy). Several pairs deliberately share vocabulary (two quarterly
           reports of the same company, API v2 docs vs the v3 migration guide, three attention/retrieval papers)
           so that retrieval is not trivial.
Questions  ml/eval_corpus/questions.jsonl — 122 questions, each with a gold answer and a gold supporting passage
           (an exact substring of one document). Types: "paraphrase" (few words shared with the passage — where
           dense retrieval should win), "keyword" (IDs, codes, names, numbers — where BM25 should win), "factual".
Chunking   the production chunker (app.rag.parsers' Markdown parser → app.rag.chunker.chunk_blocks); a chunk is
           relevant when it contains the whole gold passage (overlapping chunks may both contain it, and the
           passage counts once — see `collapse`).
Configs    BM25 · Dense (bge-small) · Hybrid (RRF) · Hybrid + cross-encoder rerank — same tokenizer, top-k sizes,
           RRF k, reranker model, rerank pool and score blend as app/rag/retriever.py, over an in-memory index
           (numpy cosine for dense vectors, rank_bm25 for BM25).
Metrics    Recall@1/3/5/10, MRR, nDCG@10 (binary relevance) and per-query latency p50/p95 (CPU, warm models,
           query embedding and reranking included).

Run from backend/:  .venv/Scripts/python -m ml.eval_rag
Outputs: ml/artifacts/rag_eval.json (RagEvalReport + extras) and ml/artifacts/rag_eval.png
"""
from __future__ import annotations

import json
import math
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):  # allow `python ml/eval_rag.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

ML_DIR = Path(__file__).resolve().parent
CORPUS_DIR = ML_DIR / "eval_corpus"
QUESTIONS_PATH = CORPUS_DIR / "questions.jsonl"
ARTIFACT_DIR = ML_DIR / "artifacts"
REPORT_PATH = ARTIFACT_DIR / "rag_eval.json"
CHART_PATH = ARTIFACT_DIR / "rag_eval.png"
DATASET_NAME = "Sphura RAG-Bench v1"
K = 10
CONFIG_NAMES = ["BM25", "Dense (bge-small)", "Hybrid (RRF)", "Hybrid + cross-encoder rerank"]
GOLD = "\x00gold"


# ── metrics (pure functions; binary relevance) ───────────────────────────────
def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Share of the relevant items that appear in the top k."""
    if not relevant:
        return 0.0
    return len(relevant.intersection(ranked[:k])) / len(relevant)


def reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float:
    """1 / rank of the first relevant item (0 when none is retrieved)."""
    for i, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Normalised discounted cumulative gain with binary gains: DCG / ideal DCG over the top k."""
    if not relevant:
        return 0.0
    dcg = sum(1.0 / math.log2(i + 2) for i, item in enumerate(ranked[:k]) if item in relevant)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal


def collapse(ranked: Sequence[str], relevant: set[str]) -> tuple[list[str], set[str]]:
    """Passage-level view: every chunk containing the gold passage becomes one GOLD item (first hit kept).

    With overlapping chunks a passage can live in two chunks; finding either one answers the question,
    so after collapsing, Recall@k is the hit rate and nDCG@10 = 1/log2(rank+1) of the first hit.
    """
    out, seen = [], False
    for item in ranked:
        if item in relevant:
            if seen:
                continue
            seen, item = True, GOLD
        out.append(item)
    return out, {GOLD}


def percentile(values: Sequence[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), q)) if len(values) else 0.0


# ── corpus ───────────────────────────────────────────────────────────────────
@dataclass
class EvalChunk:
    id: str
    doc: str
    text: str
    embed_text: str
    section: str | None


def _norm(text: str) -> str:
    return " ".join(text.split())


def load_corpus() -> tuple[list[str], list[EvalChunk]]:
    """(document names, chunks) produced exactly like an uploaded .md file is chunked in production."""
    from app.rag.chunker import chunk_blocks
    from app.rag.text import parse_markdown_text

    docs = sorted(p.name for p in CORPUS_DIR.glob("*.md"))
    chunks: list[EvalChunk] = []
    for name in docs:
        drafts = chunk_blocks(parse_markdown_text((CORPUS_DIR / name).read_text(encoding="utf-8")))
        chunks.extend(EvalChunk(f"{name}#{i}", name, d.text, d.embed_text, d.section) for i, d in enumerate(drafts))
    return docs, chunks


def load_questions() -> list[dict]:
    with QUESTIONS_PATH.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def relevant_ids(question: dict, chunks: list[EvalChunk]) -> set[str]:
    passage = _norm(question["passage"])
    return {c.id for c in chunks if c.doc == question["doc"] and passage in _norm(c.text)}


# ── the four retrieval configurations ────────────────────────────────────────
class Bench:
    """In-memory replica of app/rag/retriever.py over the benchmark chunks."""

    def __init__(self, chunks: list[EvalChunk]) -> None:
        from rank_bm25 import BM25Okapi

        from app.rag import embeddings
        from app.rag.retriever import tokenize

        self.chunks = chunks
        self.ids = [c.id for c in chunks]
        self.by_id = {c.id: c for c in chunks}
        corpus = [tokenize(f"{c.section or ''} {c.text}") for c in chunks]
        self.bm25 = BM25Okapi([doc or ["∅"] for doc in corpus])
        matrix = np.asarray(embeddings.embed_passages([c.embed_text for c in chunks]), dtype=np.float32)
        self.matrix = matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)

    # building blocks
    def _bm25(self, query: str) -> dict[str, float]:
        from app.rag.retriever import tokenize

        tokens = tokenize(query)
        scores = self.bm25.get_scores(tokens) if tokens else np.zeros(len(self.ids))
        order = np.argsort(-scores, kind="stable")
        return {self.ids[i]: float(scores[i]) for i in order}

    def _dense(self, query: str) -> dict[str, float]:
        from app.rag import embeddings

        vector = np.asarray(embeddings.embed_query(query), dtype=np.float32)
        sims = self.matrix @ (vector / max(float(np.linalg.norm(vector)), 1e-12))
        order = np.argsort(-sims, kind="stable")
        return {self.ids[i]: float(sims[i]) for i in order}

    def _hybrid(self, query: str) -> tuple[list[str], dict[str, float], dict[str, float], dict[str, float]]:
        from app.rag.retriever import DENSE_K, LEXICAL_K, rrf

        dense_all = self._dense(query)
        dense = dict(list(dense_all.items())[:DENSE_K])
        lexical = {cid: s for cid, s in list(self._bm25(query).items())[:LEXICAL_K] if s > 0}
        fused = rrf([list(dense), list(lexical)])
        ranking = sorted(fused, key=fused.get, reverse=True)  # type: ignore[arg-type]
        ranking += [cid for cid in dense_all if cid not in fused]
        return ranking, dense, lexical, fused

    # configs: query → full ranking of chunk ids
    def bm25_ranking(self, query: str) -> list[str]:
        return list(self._bm25(query))

    def dense_ranking(self, query: str) -> list[str]:
        return list(self._dense(query))

    def hybrid_ranking(self, query: str) -> list[str]:
        return self._hybrid(query)[0]

    def rerank_ranking(self, query: str) -> list[str]:
        from app.rag import embeddings
        from app.rag.retriever import RERANK_POOL, RERANK_WEIGHT, RRF_K, _evidence, focus_tables, tokenize

        ranking, dense, lexical, fused = self._hybrid(query)
        pool = ranking[:RERANK_POOL]
        terms = set(tokenize(query))
        texts = []
        for cid in pool:
            chunk = self.by_id[cid]
            text = focus_tables(chunk.text, terms)
            texts.append(f"{chunk.section}\n{text}" if chunk.section else text)
        relevance = embeddings.rerank(query, texts)
        if relevance is None:  # reranker unavailable → production falls back to normalised RRF
            relevance = [fused[c] / (2.0 / (RRF_K + 1)) for c in pool]
        evidence = _evidence(pool, dense, lexical)
        scores = [RERANK_WEIGHT * r + (1 - RERANK_WEIGHT) * e for r, e in zip(relevance, evidence)]
        reranked = [cid for cid, _ in sorted(zip(pool, scores), key=lambda x: x[1], reverse=True)]
        return reranked + ranking[RERANK_POOL:]

    def configs(self) -> dict[str, Callable[[str], list[str]]]:
        return dict(zip(CONFIG_NAMES, [self.bm25_ranking, self.dense_ranking, self.hybrid_ranking,
                                       self.rerank_ranking]))


# ── evaluation ───────────────────────────────────────────────────────────────
def _summary(rows: list[dict]) -> dict[str, float]:
    def mean(key: str) -> float:
        return round(float(np.mean([r[key] for r in rows])), 4) if rows else 0.0

    return {"recallAt1": mean("r1"), "recallAt3": mean("r3"), "recallAt5": mean("r5"), "recallAt10": mean("r10"),
            "mrr": mean("mrr"), "ndcg10": mean("ndcg")}


def _chart(configs: list[dict], by_type: dict[str, dict[str, dict]], counts: dict[str, int], path: Path) -> None:
    # Figure without pyplot: no global backend switch or shared state when the API runs this in a worker thread
    from matplotlib.figure import Figure

    colors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # categorical slots 1-4 (validated order)
    ink, muted, grid = "#0b0b0b", "#52514e", "#e4e3df"
    metrics = [("recallAt1", "Recall@1"), ("recallAt3", "Recall@3"), ("recallAt5", "Recall@5"),
               ("recallAt10", "Recall@10"), ("mrr", "MRR"), ("ndcg10", "nDCG@10")]
    types = [t for t in ("keyword", "paraphrase", "factual") if t in counts]

    fig = Figure(figsize=(14, 5.4), dpi=150)
    ax1, ax2 = fig.subplots(1, 2, gridspec_kw={"width_ratios": [2.1, 1]})
    width = 0.2
    for i, cfg in enumerate(configs):
        xs = np.arange(len(metrics)) + (i - 1.5) * width
        values = [cfg[m] for m, _ in metrics]
        ax1.bar(xs, values, width, color=colors[i], label=cfg["name"], edgecolor="white", linewidth=1.2, zorder=3)
        if i == len(configs) - 1:  # direct labels on the production configuration only
            for x, v in zip(xs, values):
                ax1.text(x, v + 0.012, f"{v:.2f}", ha="center", va="bottom", fontsize=7.5, color=ink)
    ax1.set_xticks(np.arange(len(metrics)), [label for _, label in metrics], fontsize=10, color=ink)
    ax1.set_ylim(0, 1.2)
    ax1.set_ylabel("Score (higher is better)", color=muted)
    ax1.set_title("Retrieval quality by configuration (all questions)", fontsize=12, color=ink, loc="left")
    ax1.legend(loc="upper left", ncol=4, fontsize=9, frameon=False, borderaxespad=0.2)

    for i, cfg in enumerate(configs):
        xs = np.arange(len(types)) + (i - 1.5) * width
        values = [by_type[t][cfg["name"]]["recallAt1"] for t in types]
        ax2.bar(xs, values, width, color=colors[i], edgecolor="white", linewidth=1.2, zorder=3)
    ax2.set_xticks(np.arange(len(types)), [f"{t}\n(n={counts[t]})" for t in types], fontsize=10, color=ink)
    ax2.set_ylim(0, 1.2)
    ax2.set_title("Recall@1 by question type", fontsize=12, color=ink, loc="left")

    for ax in (ax1, ax2):
        ax.set_yticks(np.linspace(0, 1, 6))
        ax.grid(axis="y", color=grid, linewidth=0.8, zorder=0)
        ax.tick_params(colors=muted, length=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(grid)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)


def run(write: bool = True, log: Callable[[str], None] = print) -> dict:
    """Run the benchmark; returns the RagEvalReport dict (and saves json + png when `write`)."""
    from app.core.config import settings
    from app.rag import embeddings
    from app.rag.retriever import DENSE_K, LEXICAL_K, RERANK_POOL, RERANK_WEIGHT, RRF_K

    started = time.perf_counter()
    docs, chunks = load_corpus()
    questions = load_questions()
    gold = {q["id"]: relevant_ids(q, chunks) for q in questions}
    missing = [q["id"] for q in questions if not gold[q["id"]]]
    if missing:
        raise RuntimeError(f"gold passages not contained in any chunk: {missing}")
    log(f"corpus: {len(docs)} documents -> {len(chunks)} chunks; {len(questions)} questions")

    bench = Bench(chunks)
    embeddings.embed_query("warm up")
    reranker_ok = embeddings.rerank("warm up", ["warm up"]) is not None

    per_config: dict[str, list[dict]] = {name: [] for name in CONFIG_NAMES}
    latencies: dict[str, list[float]] = {name: [] for name in CONFIG_NAMES}
    for q in questions:
        for name, fn in bench.configs().items():
            t0 = time.perf_counter()
            ranking = fn(q["question"])
            latencies[name].append((time.perf_counter() - t0) * 1000)
            ranked, rel = collapse(ranking, gold[q["id"]])
            rank = next((i for i, c in enumerate(ranked, start=1) if c in rel), None)
            per_config[name].append({"id": q["id"], "type": q.get("type", "factual"), "rank": rank,
                                     "r1": recall_at_k(ranked, rel, 1), "r3": recall_at_k(ranked, rel, 3),
                                     "r5": recall_at_k(ranked, rel, 5), "r10": recall_at_k(ranked, rel, 10),
                                     "mrr": reciprocal_rank(ranked, rel), "ndcg": ndcg_at_k(ranked, rel, K)})

    configs = []
    for name in CONFIG_NAMES:
        configs.append({"name": name, **_summary(per_config[name]),
                        "latencyMsP50": round(percentile(latencies[name], 50), 1),
                        "latencyMsP95": round(percentile(latencies[name], 95), 1)})
        c = configs[-1]
        log(f"  {name:<32} R@1 {c['recallAt1']:.3f}  R@3 {c['recallAt3']:.3f}  R@5 {c['recallAt5']:.3f}  "
            f"R@10 {c['recallAt10']:.3f}  MRR {c['mrr']:.3f}  nDCG@10 {c['ndcg10']:.3f}  "
            f"p50 {c['latencyMsP50']} ms  p95 {c['latencyMsP95']} ms")

    counts: dict[str, int] = {}
    for q in questions:
        counts[q.get("type", "factual")] = counts.get(q.get("type", "factual"), 0) + 1
    by_type = {t: {name: _summary([r for r in per_config[name] if r["type"] == t]) for name in CONFIG_NAMES}
               for t in counts}

    best = max(configs, key=lambda c: (c["mrr"], c["ndcg10"]))
    final = CONFIG_NAMES[-1]
    hardest = sorted((r for r in per_config[final] if r["rank"] is None or r["rank"] > 3),
                     key=lambda r: (r["rank"] is None, r["rank"] or 0), reverse=True)[:15]
    q_by_id = {q["id"]: q for q in questions}
    bm, de = "BM25", "Dense (bge-small)"
    notes = [
        f"{len(questions)} questions over {len(docs)} documents ({len(chunks)} chunks from the production chunker); "
        "a chunk is relevant when it contains the question's gold passage.",
        f"Best overall: {best['name']} (MRR {best['mrr']:.3f}, Recall@1 {best['recallAt1']:.3f}, "
        f"Recall@5 {best['recallAt5']:.3f}).",
    ]
    if "keyword" in by_type:
        notes.append(f"Keyword/ID questions (n={counts['keyword']}): BM25 Recall@1 "
                     f"{by_type['keyword'][bm]['recallAt1']:.3f} vs dense {by_type['keyword'][de]['recallAt1']:.3f}.")
    if "paraphrase" in by_type:
        notes.append(f"Paraphrased questions (n={counts['paraphrase']}): dense Recall@1 "
                     f"{by_type['paraphrase'][de]['recallAt1']:.3f} vs BM25 {by_type['paraphrase'][bm]['recallAt1']:.3f}.")
    notes.append(f"Configs mirror app/rag/retriever.py: RRF k={RRF_K} over the top-{DENSE_K} dense and "
                 f"top-{LEXICAL_K} BM25 lists; the cross-encoder re-scores the top {RERANK_POOL} fused chunks and "
                 f"the final score is {RERANK_WEIGHT}·rerank + {round(1 - RERANK_WEIGHT, 2)}·retrieval evidence.")
    notes.append("Latency: single query on CPU with warm models, including query embedding (and reranking).")
    if not reranker_ok:
        notes.append("The cross-encoder could not be loaded, so the rerank config fell back to fusion scores.")

    report = {
        "available": True,
        "runAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dataset": {"name": DATASET_NAME, "documents": len(docs), "chunks": len(chunks), "questions": len(questions)},
        "k": K,
        "configs": configs,
        "notes": notes,
        # extras (not in the TS contract; used by the README)
        "byType": by_type,
        "questionTypes": counts,
        "settings": {"embeddingModel": settings.embedding_model, "rerankerModel": settings.reranker_model,
                     "rerankerLoaded": reranker_ok, "rrfK": RRF_K, "denseK": DENSE_K, "lexicalK": LEXICAL_K,
                     "rerankPool": RERANK_POOL, "rerankWeight": RERANK_WEIGHT},
        "hardest": [{"id": r["id"], "type": r["type"], "rank": r["rank"], "question": q_by_id[r["id"]]["question"],
                     "doc": q_by_id[r["id"]]["doc"]} for r in hardest],
        "seconds": round(time.perf_counter() - started, 1),
    }
    if write:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            _chart(configs, by_type, counts, CHART_PATH)
        except ImportError:  # matplotlib is optional (not in requirements.txt): the chart is for the README only
            log("matplotlib is not installed; skipped the chart")
        log(f"saved {REPORT_PATH.name} and {CHART_PATH.name} in {ARTIFACT_DIR}")
    return report


if __name__ == "__main__":
    run()
