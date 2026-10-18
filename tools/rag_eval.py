import os
import re
import sys
import json
import time
import fnmatch
import argparse
import statistics
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_engine  # men-set HF_HOME ke tools/models (D:) sebelum model dimuat

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = re.compile(r"\w+", re.UNICODE)

def load_set(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def load_chunks(vault, chunk_size, exclude, overlap=0):
    """Chunk vault memakai fungsi rag_engine yang sama dengan produksi."""
    chunks = []
    for f in rag_engine.get_files(vault):
        rel = os.path.relpath(f, vault).replace("\\", "/")
        if any(fnmatch.fnmatch(os.path.basename(rel), pat) for pat in exclude):
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as e:
            print(f"[WARN] Gagal membaca {f}: {e}")
            continue
        chunks += [(rel, c) for c in rag_engine.chunk_text(text, chunk_size, overlap) if c.strip()]
    return chunks

class Vector:
    """Pencarian cosine eksak (pada ±1.000 chunk hasilnya setara HNSW di produksi)."""
    def __init__(self, chunks, model_name, passage_prefix, query_prefix):
        from sentence_transformers import SentenceTransformer
        self.model, self.qp = SentenceTransformer(model_name), query_prefix
        self.emb = self.model.encode([passage_prefix + t for _, t in chunks], normalize_embeddings=True, batch_size=32)
        self.files = [f for f, _ in chunks]
    def rank(self, query):
        q = self.model.encode([self.qp + query], normalize_embeddings=True)[0]
        best = {}
        for f, s in zip(self.files, self.emb @ q):
            best[f] = max(best.get(f, -1.0), float(s))
        return sorted(((f, 1 - s) for f, s in best.items()), key=lambda x: x[1])  # (file, jarak cosine)

BM25 = rag_engine.BM25   # satu implementasi untuk produksi dan evaluasi (Aturan 6)
rrf = rag_engine.rrf
link_graph, link_rank = rag_engine.link_graph, rag_engine.link_rank

def evaluate(rank_fn, rows, k):
    per = []
    for r in rows:
        ranked = rank_fn(r["query"])
        top = [f for f, _ in ranked[:k]]
        rec = {"id": r["id"], "type": r["type"], "top": top[:3], "top1": ranked[0][1] if ranked else None}
        if r["type"] == "answerable":
            rel = set(r["relevant"])
            rank = next((i + 1 for i, (f, _) in enumerate(ranked) if f in rel), None)
            rec.update(recall=len(rel & set(top)) / len(rel), precision=len(rel & set(top)) / k,
                       rr=1 / rank if rank else 0.0, first_rel_rank=rank)
        per.append(rec)
    return per

def report(label, per, k, distance):
    ans = [p for p in per if p["type"] == "answerable"]
    m = {"recall": statistics.mean(p["recall"] for p in ans), "precision": statistics.mean(p["precision"] for p in ans), "mrr": statistics.mean(p["rr"] for p in ans)}
    print(f"\n### {label} — Recall@{k} {m['recall']:.2f} · Precision@{k} {m['precision']:.2f} · MRR {m['mrr']:.2f}")
    print(f"| ID | Recall@{k} | Peringkat relevan pertama | Top-1 ({'jarak' if distance else 'skor'}) | 3 file teratas |\n|---|---|---|---|---|")
    for p in per:
        rc = f"{p['recall']:.2f}" if p["type"] == "answerable" else "tanpa jawaban"
        fr = p.get("first_rel_rank") or "—"
        t1 = f"{p['top1']:.3f}" if p["top1"] is not None else "—"
        print(f"| {p['id']} | {rc} | {fr} | {t1} | {', '.join(os.path.basename(t) for t in p['top'])} |")
    if distance:
        a = [p["top1"] for p in per if p["type"] == "answerable"]
        n = [p["top1"] for p in per if p["type"] == "no_answer"]
        if a and n:
            print(f"\nJarak top-1 — berjawaban: median {statistics.median(a):.3f} (min {min(a):.3f}, maks {max(a):.3f}) · "
                  f"tanpa jawaban: median {statistics.median(n):.3f} (min {min(n):.3f}, maks {max(n):.3f})")
    return m

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Evaluasi retrieval RAG (Recall@K, Precision@K, MRR) di tingkat dokumen: chunk diagregasi per file.")
    p.add_argument("vault")
    p.add_argument("--set", action="append", required=True, help="File JSONL test set (boleh diulang)")
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--model", default="all-MiniLM-L6-v2")
    p.add_argument("--query-prefix", default="", help='mis. "query: " untuk keluarga e5')
    p.add_argument("--passage-prefix", default="", help='mis. "passage: " untuk keluarga e5')
    p.add_argument("--chunk-size", type=int, default=1000)
    p.add_argument("--overlap", type=int, default=0, help="Karakter yang bertumpang antar potongan berurutan dalam satu section")
    p.add_argument("--exclude", action="append", default=[], help="Pola nama file yang tidak diindeks, mis. log.md (boleh diulang)")
    p.add_argument("--backend", choices=["vector", "bm25", "hybrid", "all"], default="all")
    p.add_argument("--vector-weight", type=float, default=2.0, help="Bobot vektor terhadap BM25 (=1) di RRF; 2 terbaik di set dev 2026-10-13")
    p.add_argument("--link-weight", type=float, action="append", default=[], help="Tambah backend hybrid+link dengan bobot daftar tetangga [[link]] ini di RRF (boleh diulang)")
    p.add_argument("--link-seeds", type=int, default=5, help="Jumlah hasil teratas yang tetangganya diambil")
    p.add_argument("--no-link-norm", action="store_true", help="Jangan bagi skor tetangga dengan derajat halaman")
    p.add_argument("--log-weight", type=float, action="append", default=[], help="Tambah backend hybrid+log dengan pengali skor halaman Log/ ini (boleh diulang)")
    p.add_argument("--out", default=os.path.join(HERE, "eval", "results"))
    a = p.parse_args()
    if not 0 <= a.overlap < a.chunk_size:
        p.error("--overlap harus >= 0 dan lebih kecil dari --chunk-size")

    t0 = time.time()
    chunks = load_chunks(a.vault, a.chunk_size, a.exclude, a.overlap)
    backends = {}
    if a.backend in ("bm25", "hybrid", "all"):
        bm = BM25(chunks); backends["bm25"] = (bm.rank, False)
    if a.backend in ("vector", "hybrid", "all"):
        vec = Vector(chunks, a.model, a.passage_prefix, a.query_prefix); backends["vector"] = (vec.rank, True)
    if a.backend in ("hybrid", "all"):
        backends["hybrid"] = (lambda q: rrf([vec.rank(q), bm.rank(q)], [a.vector_weight, 1]), False)
        graph = link_graph(chunks)
        def hybrid_link(q, w):
            v, b = vec.rank(q), bm.rank(q)
            nb = link_rank(rrf([v, b], [a.vector_weight, 1]), graph, a.link_seeds, not a.no_link_norm)
            return rrf([v, b, nb], [a.vector_weight, 1, w])
        for w in a.link_weight:
            backends[f"hybrid+link{w:g}"] = (lambda q, w=w: hybrid_link(q, w), False)
        for w in a.log_weight:
            backends[f"hybrid+log{w:g}"] = (lambda q, w=w: rag_engine.weigh_logs(rrf([vec.rank(q), bm.rank(q)], [a.vector_weight, 1]), w), False)
    if a.backend != "all":
        backends = {n: b for n, b in backends.items() if n == a.backend or n.startswith(a.backend + "+")}

    excl = f", tanpa {', '.join(a.exclude)}" if a.exclude else ""
    link = f", link seeds {a.link_seeds}{' tanpa normalisasi' if a.no_link_norm else ''}" if a.link_weight else ""
    print(f"# Evaluasi RAG — model `{a.model}`, chunk {a.chunk_size}, overlap {a.overlap}{excl}{link}\n\n"
          f"{len({f for f, _ in chunks})} file, {len(chunks)} chunk, siap dalam {time.time() - t0:.1f} detik. "
          f"Tingkat dokumen; Recall = file relevan di Top-{a.k} ÷ total file relevan; Precision = ÷ {a.k}; RR = 1 ÷ peringkat file relevan pertama.")
    results = {}
    for s in a.set:
        rows = load_set(s)
        print(f"\n## Set `{os.path.basename(s)}` — {sum(r['type'] == 'answerable' for r in rows)} berjawaban, {sum(r['type'] == 'no_answer' for r in rows)} tanpa jawaban")
        for name, (fn, is_dist) in backends.items():
            per = evaluate(fn, rows, a.k)
            results[f"{os.path.basename(s)}::{name}"] = {"metrics": report(name, per, a.k, is_dist), "per": per}
    os.makedirs(a.out, exist_ok=True)
    tag = re.sub(r"[^A-Za-z0-9]+", "-", f"{a.model}-c{a.chunk_size}-o{a.overlap}-{'-'.join(a.exclude) or 'all'}")
    out = os.path.join(a.out, f"{time.strftime('%Y%m%d-%H%M%S')}-{tag}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"config": vars(a), "chunks": len(chunks), "results": results}, f, ensure_ascii=False, indent=1)
    print(f"\nHasil lengkap: `{out}`")

if __name__ == "__main__":
    main()
