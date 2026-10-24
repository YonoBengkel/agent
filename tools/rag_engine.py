import sys
import os
import re
import json
import math
import hashlib
import fnmatch
import argparse
import subprocess
from collections import Counter, defaultdict

# Model embedding disimpan di D: (tools/models), bukan cache default di C: (Aturan 8).
# Harus di-set sebelum chromadb/sentence-transformers di-import.
os.environ.setdefault("HF_HOME", os.path.join(os.path.dirname(os.path.abspath(__file__)), "models"))

import chromadb

# Konfigurasi pemenang evaluasi 2026-10-13 (tools/rag_eval.py, Wiki/concepts/Evaluasi RAG.md):
# e5-small multibahasa + BM25, digabung RRF dengan bobot vektor 2 : BM25 1, tanpa log operasional;
# v4 menambah overlap chunk (perluasan lewat [[link]] diuji lalu dimatikan).
# v5 (2026-10-15) tidak mengubah cara mencari: index jadi inkremental lewat manifest hash per file, dan search
# menyegarkan dulu file yang berubah sehingga index tidak pernah basi.
# v6 (2026-10-20): tiap chunk membawa jalur judul bagiannya ("Halaman › Bagian › Subbagian") sebagai metadata
# "section", yang ditampilkan di hasil search. SECTION_CONTEXT menentukan apakah jalur itu ikut dicari: "none"
# (hanya metadata), "vector" (diawalkan ke teks yang di-embed), "bm25", atau "both". Tetap "none" sampai mode
# lain lulus uji tertutup, bukan hanya set dev (Pelajaran #14).
MODEL = "intfloat/multilingual-e5-small"
QUERY_PREFIX, PASSAGE_PREFIX = "query: ", "passage: "   # wajib untuk keluarga e5
COLLECTION = "vault"
EXCLUDE = ["log.md", "log_id.md"]
VECTOR_WEIGHT = 2.0
# Perluasan [[link]] (tetangga 5 hasil teratas sebagai daftar ketiga RRF) naik sedikit di set dev, tapi
# menurunkan MRR di uji tertutup 0,88 → 0,68 (2026-10-13), jadi dimatikan. 0,5 = bobot yang pernah diuji.
LINK_WEIGHT, LINK_SEEDS = 0.0, 5
CHUNK_OVERLAP = 100                # karakter bertumpang antar potongan section panjang (v4)
# Pengali skor RRF untuk halaman di folder Log/. 0,97 hanya memecah skor yang hampir seri agar halaman wiki menang.
# Set dev: Recall@5 0,74 → 0,78, MRR 0,69 → 0,78 (≤ 0,9 menurunkan recall). Uji tertutup: recall tetap 0,62, MRR 0,65 → 0,71 (2026-10-16).
LOG_WEIGHT = 0.97
SECTION_CONTEXT = "none"
# Disimpan di manifest; kalau berbeda dari index di disk (cara memotong atau isi chunk berubah), index dibangun ulang.
INDEX_FORMAT = f"v6 section={SECTION_CONTEXT} overlap={CHUNK_OVERLAP}"
WEAK_DISTANCE = 0.18   # jarak cosine di atas ini ditandai "lemah" (tidak dibuang)
TOKEN = re.compile(r"\w+", re.UNICODE)
EXTS = ['.md', '.txt', '.csv']
# Dokumen yang dikonversi dulu ke Markdown dengan MarkItDown (sudah terpasang di tools/markitdown-venv), untuk folder di
# luar vault seperti materi kuliah (2026-10-20). Vault sendiri tidak berisi jenis file ini.
CONVERT_EXTS = ['.pdf', '.docx', '.pptx']
MARKITDOWN = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'markitdown-venv', 'Scripts', 'markitdown.exe')
# Cakupan bawaan search: vault memori. Folder lain yang diindeks dicari lewat --root, supaya hasilnya tidak tercampur.
VAULT = r"D:\Obsidian\All Sources\AI Workspace"
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rag_db')
# Hash isi tiap file per folder yang diindeks: dasar index inkremental (2026-10-15). Juga dibaca vault_lint.py.
MANIFEST = os.path.join(DB_DIR, 'manifest.json')

def get_files(folder, exts=EXTS):
    """Mencari file berekstensi exts di dalam folder. Folder yang memuat .no-vault dilewati beserta isinya."""
    files = []
    for root, dirs, filenames in os.walk(folder):
        if ".no-vault" in filenames:
            dirs[:] = []
            continue
        for filename in filenames:
            if os.path.splitext(filename)[1].lower() in exts:
                files.append(os.path.join(root, filename))
    return files

def indexable(folder):
    """File yang diindeks dari folder: teks dan dokumen yang dikonversi, tanpa pola EXCLUDE."""
    return [f for f in get_files(folder, EXTS + CONVERT_EXTS) if not any(fnmatch.fnmatch(os.path.basename(f), p) for p in EXCLUDE)]

def read_text(path):
    """Isi file sebagai teks; dokumen di CONVERT_EXTS dikonversi ke Markdown dengan MarkItDown lebih dulu."""
    if os.path.splitext(path)[1].lower() not in CONVERT_EXTS:
        with open(path, 'r', encoding='utf-8') as file:
            return file.read()
    out = subprocess.run([MARKITDOWN, path], capture_output=True, timeout=600,
                         env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"))
    if out.returncode != 0:
        err = out.stderr.decode('utf-8', 'replace').strip().splitlines()
        raise OSError(f"markitdown gagal: {err[-1] if err else out.returncode}")
    return out.stdout.decode('utf-8', 'replace')

def resolve_root(manifest, arg):
    """Folder akar di manifest yang sama dengan arg (besar-kecil huruf dan garis miring diabaikan)."""
    p = os.path.normcase(os.path.abspath(arg))
    return next((r for r in manifest["roots"] if os.path.normcase(r) == p), os.path.abspath(arg))

HEADING = re.compile(r'(#{1,6}) +(.*)')

def chunk_sections(text, chunk_size=1000, overlap=0):
    """Memotong teks per heading Markdown; section yang terlalu panjang dipotong lagi per chunk_size,
    dengan potongan berurutan bertumpang sebanyak overlap karakter. Tiap potongan membawa jalur judulnya
    (heading induk sampai heading section itu), juga potongan lanjutan yang tidak lagi memuat heading-nya."""
    out, path = [], []
    for s in re.split(r'(?m)^(?=#{1,6} )', text):
        m = HEADING.match(s)
        if m:
            level = len(m[1])
            path = [p for p in path if p[0] < level] + [(level, m[2].strip())]
        trail = [t for _, t in path]
        out += [(trail, s[i:i+chunk_size]) for i in range(0, max(len(s) - overlap, 1), chunk_size - overlap)]
    return out

def section_label(path, trail):
    """'Halaman › Bagian › Subbagian'. Nama halaman = nama file; H1 yang sama dengan nama file tidak diulang."""
    title = os.path.splitext(os.path.basename(path))[0]
    if trail and trail[0].lower() == title.lower():
        trail = trail[1:]
    return " › ".join([title] + trail)

def contextual(section, chunk, backend, mode=SECTION_CONTEXT):
    """Teks chunk untuk backend ("vector" atau "bm25"): diawali jalur judulnya kalau mode menyalakannya."""
    return f"{section}\n{chunk}" if mode in (backend, "both") else chunk

class BM25:
    """Okapi BM25 dengan standard library; skor file = skor chunk terbaiknya. Menangkap istilah persis."""
    def __init__(self, chunks, k1=1.5, b=0.75):
        self.docs = [Counter(TOKEN.findall(t.lower())) for _, t in chunks]
        self.files = [f for f, _ in chunks]
        self.len = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.len) / max(len(self.len), 1)
        df = Counter(w for d in self.docs for w in d)
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.k1, self.b = k1, b

    def rank(self, query):
        terms = TOKEN.findall(query.lower())
        best = {}
        for d, ln, f in zip(self.docs, self.len, self.files):
            s = sum(self.idf.get(t, 0) * d[t] * (self.k1 + 1) / (d[t] + self.k1 * (1 - self.b + self.b * ln / self.avg)) for t in terms if t in d)
            if s > 0:
                best[f] = max(best.get(f, 0.0), s)
        return sorted(best.items(), key=lambda x: -x[1])

def rrf(rankings, weights=None, k=60):
    """Reciprocal Rank Fusion (berbobot) atas daftar peringkat file."""
    score = defaultdict(float)
    for r, w in zip(rankings, weights or [1] * len(rankings)):
        for i, (f, _) in enumerate(r):
            score[f] += w / (k + i + 1)
    return sorted(score.items(), key=lambda x: -x[1])

def weigh_logs(fused, weight, rel=lambda f: f):
    """Kalikan skor RRF halaman di folder Log/ dengan weight, lalu urutkan ulang. Log sesi panjang membahas banyak
    topik sekaligus, jadi sering mengalahkan halaman wiki yang lebih tepat."""
    if weight == 1:
        return fused
    return sorted(((f, s * weight if rel(f).replace("\\", "/").startswith("Log/") else s) for f, s in fused), key=lambda x: -x[1])

LINK = re.compile(r"\[\[([^\]|#]+)")

def link_graph(chunks):
    """Graph [[link]] tak berarah antar file terindeks, dicocokkan per nama file seperti Obsidian.
    Link ke halaman yang tidak terindeks diabaikan."""
    by_name = {os.path.splitext(os.path.basename(f))[0].lower(): f for f, _ in chunks}
    graph = defaultdict(set)
    for f, t in chunks:
        for name in LINK.findall(t):
            g = by_name.get(os.path.basename(name.strip()).lower())
            if g and g != f:
                graph[f].add(g)
                graph[g].add(f)
    return graph

def link_rank(fused, graph, seeds=5, norm=True):
    """Peringkat tetangga [[link]] dari `seeds` hasil teratas. Dengan norm, skor dibagi akar derajat
    kedua halaman supaya hub (index.md, hot.md) tidak otomatis menang."""
    score = defaultdict(float)
    for s, sc in fused[:seeds]:
        for p in graph.get(s, ()):
            score[p] += sc / math.sqrt(len(graph[s]) * len(graph[p])) if norm else sc
    return sorted(score.items(), key=lambda x: -x[1])

def load_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL)

def load_manifest():
    try:
        with open(MANIFEST, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"roots": {}}

def save_manifest(manifest):
    manifest.update(exts=EXTS + CONVERT_EXTS, exclude=EXCLUDE, format=INDEX_FORMAT)   # aturan pemilihan file ikut disimpan, supaya vault_lint.py tidak menyalinnya
    tmp = MANIFEST + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    os.replace(tmp, MANIFEST)

def changes(root, known):
    """Bandingkan isi folder dengan hash di manifest: (berubah atau baru, terhapus, hash terkini)."""
    current = {}
    for f in indexable(root):
        rel = os.path.relpath(f, root)
        try:
            with open(f, 'rb') as fh:
                current[rel] = hashlib.sha1(fh.read()).hexdigest()
        except OSError as e:
            print(f"[WARN] Gagal membaca {f}: {e}")
            if rel in known:
                current[rel] = known[rel]   # anggap tidak berubah; dicoba lagi lain kali
    return [r for r, h in current.items() if known.get(r) != h], [r for r in known if r not in current], current

def sync(collection, root, changed, removed, current, model, manifest):
    """Index inkremental: buang chunk file yang berubah atau terhapus, lalu embed ulang yang berubah atau baru."""
    for rel in changed + removed:
        collection.delete(where={"source": os.path.join(root, rel)})
    docs, ids, metadatas = [], [], []
    for rel in changed:
        f = os.path.join(root, rel)
        try:
            content = read_text(f)
        except (OSError, UnicodeDecodeError, subprocess.SubprocessError) as e:
            if os.path.splitext(f)[1].lower() in CONVERT_EXTS:
                print(f"[WARN] Konversi gagal, dilewati sampai file ini berubah: {f}: {e}")   # hash tetap dicatat
            else:
                print(f"[WARN] Gagal membaca {f}: {e}")
                current.pop(rel, None)   # belum terindeks; dicoba lagi lain kali
            continue
        for i, (trail, chunk) in enumerate(chunk_sections(content, overlap=CHUNK_OVERLAP)):
            if chunk.strip():
                docs.append(chunk)
                ids.append(f"{f}_{i}")
                metadatas.append({"source": f, "folder": os.path.basename(os.path.dirname(f)), "root": root,
                                  "section": section_label(f, trail)})
    if docs:
        print(f"[*] Membuat embedding {len(docs)} chunk dengan {MODEL}...")
        texts = [PASSAGE_PREFIX + contextual(m["section"], d, "vector") for m, d in zip(metadatas, docs)]
        vectors = model().encode(texts, normalize_embeddings=True, batch_size=32)
        for i in range(0, len(docs), 100):
            collection.upsert(documents=docs[i:i+100], metadatas=metadatas[i:i+100], ids=ids[i:i+100],
                              embeddings=vectors[i:i+100].tolist())
    manifest["roots"][root] = current
    save_manifest(manifest)
    return len(docs)

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="AI Agent Local RAG Engine v6 — hybrid (e5 + BM25), overlap chunk, index inkremental, judul bagian per chunk")
    parser.add_argument("action", choices=["index", "search", "status"],
                        help="index: index folder (hanya file yang berubah); search: cari (index disegarkan dulu kalau ada file berubah); status: hitung file yang berubah sejak index terakhir")
    parser.add_argument("target", nargs="?", help="Path folder (untuk index) atau kata kunci (untuk search)")
    parser.add_argument("--folder", type=str, default=None, help="Filter: hanya file di folder induk dengan nama ini")
    parser.add_argument("--k", type=int, default=5, help="Jumlah halaman yang ditampilkan")
    parser.add_argument("--full", action="store_true", help="index: bangun ulang semua chunk folder ini, abaikan manifest")
    parser.add_argument("--no-refresh", action="store_true", help="search: jangan segarkan index walau ada file yang berubah")
    parser.add_argument("--root", default=VAULT, help='search: folder akar yang dicari, mis. "D:/KULIAH/MATA KULIAH/SEM 5" '
                                                      '(bawaan: vault); "all" untuk semua folder yang diindeks')
    args = parser.parse_args()
    if args.action != "status" and not args.target:
        parser.error(f"'{args.action}' butuh target (folder atau kata kunci)")

    manifest = load_manifest()
    stale = manifest.get("format") != INDEX_FORMAT   # dihitung sekali: save_manifest menimpanya setelah folder pertama
    if args.action == "status":
        if not manifest["roots"]:
            print("Belum ada manifest. Jalankan 'index <folder>' dulu.")
        for root, known in manifest["roots"].items():
            changed, removed, current = changes(root, known)
            print(f"{root}: {len(current)} file; {len(changed)} berubah atau baru, {len(removed)} terhapus sejak index terakhir.")
        if manifest["roots"] and stale:
            print(f"Format index berubah ({manifest.get('format', 'v5')} → {INDEX_FORMAT}): index berikutnya dibangun ulang penuh.")
        return

    client = chromadb.PersistentClient(path=DB_DIR)
    collection = client.get_or_create_collection(name=COLLECTION, configuration={"hnsw": {"space": "cosine"}})
    loaded = []
    def model():
        """Model dimuat sekali, dan hanya kalau dibutuhkan."""
        if not loaded:
            loaded.append(load_model())
        return loaded[0]

    if args.action == "index":
        root = os.path.abspath(args.target)
        full = args.full or stale or root not in manifest["roots"]   # tanpa manifest, chunk lama tak bisa dicocokkan per file
        if full:
            collection.delete(where={"root": root})
        changed, removed, current = changes(root, {} if full else manifest["roots"][root])
        print(f"[*] {len(current)} file di {root} (dikecualikan: {', '.join(EXCLUDE)}); "
              f"{'bangun ulang penuh' if full else f'{len(changed)} berubah atau baru, {len(removed)} terhapus'}.")
        n = sync(collection, root, changed, removed, current, model, manifest)
        print(f"[SUCCESS] {n} chunk dari {len(changed)} file diperbarui. Total chunk di index: {collection.count()}.")

    elif args.action == "search":
        # Index disegarkan sebelum mencari, hanya untuk file yang berubah: tidak ada ambang yang perlu ditunggu,
        # karena memperbarui satu file cuma butuh beberapa detik dan model toh dimuat untuk query.
        # Hanya cakupan yang dicari yang disegarkan, supaya pencarian vault tidak ikut meng-hash folder dokumen yang besar.
        scope = list(manifest["roots"]) if args.root == "all" else [resolve_root(manifest, args.root)]
        for root in ([] if args.no_refresh else scope):
            known = manifest["roots"].get(root)
            if known is None:
                print(f"[WARN] Folder ini belum diindeks: {root}. Jalankan 'index' dulu.")
                continue
            if not os.path.isdir(root):
                print(f"[WARN] Folder index tidak ditemukan: {root}")
                continue
            if stale:
                collection.delete(where={"root": root})
            changed, removed, current = changes(root, {} if stale else known)
            if changed or removed:
                n = sync(collection, root, changed, removed, current, model, manifest)
                print(f"[*] Index disegarkan{' penuh (format index berubah)' if stale else ''}: "
                      f"{len(changed)} file berubah atau baru, {len(removed)} terhapus ({n} chunk).")
        conds = ([] if args.root == "all" else [{"root": scope[0]}]) + ([{"folder": args.folder}] if args.folder else [])
        where = None if not conds else conds[0] if len(conds) == 1 else {"$and": conds}
        stored = collection.get(where=where, include=["documents", "metadatas"])
        if not stored["documents"]:
            print("Index kosong untuk filter ini. Jalankan 'index' dulu.")
            return
        chunks = [(m["source"], contextual(m.get("section", ""), d, "bm25")) for m, d in zip(stored["metadatas"], stored["documents"])]
        root_of = {m["source"]: m["root"] for m in stored["metadatas"]}
        q = model().encode([QUERY_PREFIX + args.target], normalize_embeddings=True)[0].tolist()
        res = collection.query(query_embeddings=[q], n_results=min(40, len(chunks)), where=where)

        vec_rank, best_chunk, dist, section = [], {}, {}, {}
        for m, d, dd in zip(res["metadatas"][0], res["documents"][0], res["distances"][0]):
            if m["source"] not in dist:
                dist[m["source"]], best_chunk[m["source"]], section[m["source"]] = dd, d, m.get("section")
                vec_rank.append((m["source"], dd))
        bm_rank = BM25(chunks).rank(args.target)
        base = weigh_logs(rrf([vec_rank, bm_rank], [VECTOR_WEIGHT, 1]), LOG_WEIGHT, lambda f: os.path.relpath(f, root_of[f]))
        graph = link_graph(chunks) if LINK_WEIGHT else {}
        fused = (rrf([vec_rank, bm_rank, link_rank(base, graph, LINK_SEEDS)], [VECTOR_WEIGHT, 1, LINK_WEIGHT]) if LINK_WEIGHT else base)[:args.k]
        seeds, direct = [s for s, _ in base[:LINK_SEEDS]], {s for s, _ in base[:args.k]}
        rel = lambda f: os.path.relpath(f, root_of[f])

        print(f"[*] Pencarian: '{args.target}' (cakupan: {'semua folder' if args.root == 'all' else scope[0]})"
              + (f" (folder: {args.folder})" if args.folder else ""))
        print("[*] Ini daftar halaman untuk dibuka, bukan jawaban. Jarak cosine: kecil = mirip.\n")
        for n, (f, _) in enumerate(fused, 1):
            if f not in dist:   # masuk lewat BM25 atau [[link]]: ambil jarak chunk terbaiknya
                r = collection.query(query_embeddings=[q], n_results=1, where={"source": f})
                dist[f], best_chunk[f], section[f] = r["distances"][0][0], r["documents"][0][0], r["metadatas"][0][0].get("section")
            flag = "" if dist[f] <= WEAK_DISTANCE else "  ⚠ lemah"
            via = [os.path.splitext(os.path.basename(s))[0] for s in seeds if f in graph.get(s, ())]
            vtxt = f"\n   terangkat lewat [[link]] dari: {', '.join(via)}" if f not in direct and via else ""
            stxt = f"\n   bagian: {section[f]}" if section.get(f) else ""
            snippet = " ".join(best_chunk[f].split())[:280]
            print(f"{n}. {rel(f)}{stxt}\n   jarak {dist[f]:.3f}{flag}{vtxt}\n   {snippet}…\n")

if __name__ == "__main__":
    main()
