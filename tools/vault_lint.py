import os
import re
import sys
import json
import math
import hashlib
import fnmatch
import argparse
from collections import Counter, defaultdict

LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)   # Obsidian tidak menganggap [[...]] di dalam kode sebagai link
CONTROL = {"hot", "index", "log", "log_id", "KONTEKS_PROYEK"}
FRONTMATTER = re.compile(r"\A﻿?---\r?\n(.*?)\r?\n---", re.S)
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rag_db", "manifest.json")   # ditulis rag_engine.py

def aliases(text):
    """Nilai `aliases` di frontmatter, bentuk [a, b] atau daftar '- a'. Obsidian menyambungkan [[alias]] ke halamannya."""
    m = FRONTMATTER.match(text)
    if not m:
        return []
    inline = re.search(r"(?m)^aliases:\s*\[(.*)\]\s*$", m.group(1))
    block = None if inline else re.search(r"(?m)^aliases:\s*\n((?:[ \t]*-.*\n?)+)", m.group(1))
    items = inline.group(1).split(",") if inline else re.findall(r"-\s*(.+)", block.group(1)) if block else []
    return [i.strip().strip("'\"") for i in items if i.strip()]

def rag_staleness(vault):
    """File yang berubah atau baru, dan yang terhapus, sejak index RAG terakhir; None kalau vault belum punya manifest.
    Aturan pemilihan file dibaca dari manifest, jadi sama persis dengan rag_engine.py."""
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        return None
    root = next((r for r in m.get("roots", {}) if os.path.normcase(os.path.abspath(r)) == os.path.normcase(os.path.abspath(vault))), None)
    if root is None:
        return None
    known, current = m["roots"][root], {}
    for dp, _, fn in os.walk(root):
        for f in fn:
            if os.path.splitext(f)[1].lower() in m["exts"] and not any(fnmatch.fnmatch(f, x) for x in m["exclude"]):
                p = os.path.join(dp, f)
                with open(p, "rb") as fh:
                    current[os.path.relpath(p, root)] = hashlib.sha1(fh.read()).hexdigest()
    return [r for r, h in current.items() if known.get(r) != h], [r for r in known if r not in current]

TICK = re.compile(r"`([^`\n]+)`")
PATH_ROOTS = ("log/", "wiki/", "ai workspace/", "tools/", "konfigurasi/", "riwayat perckapan/", ".claude/", ".agents/", "9router/", "d:/")
RETIRED = ("Recycle Bin", "dipensiunkan", "pensiun", "SUPERSEDED", "~~")

def stale_paths(pages, text, bases):
    """Verifikasi rujukan saat dipakai (ide sistem memori GitHub Copilot, 2026-10-16): path di dalam backtick pada
    halaman yang bicara masa kini, yang tidak ada lagi di disk. Path relatif dicoba terhadap setiap folder di `bases`.
    Baris yang menandai sesuatu sudah pensiun dilewati; log tidak dicek karena mencatat keadaan saat itu."""
    found = []
    for p in pages:
        for line in text[p].splitlines():
            if any(r in line for r in RETIRED):
                continue
            for raw in TICK.findall(line):
                s = re.sub(r":\d+$", "", raw.strip().replace("\\", "/")).rstrip("/")
                if not s.lower().startswith(PATH_ROOTS) or any(c in s for c in "<>*{}$|…"):
                    continue
                if s.lower().startswith("ai workspace/"):
                    s = s[len("ai workspace/"):]
                tries = [s, s.split(" ")[0]]   # perintah lengkap: cukup argumen pertamanya yang harus ada
                if not any(os.path.exists(t if re.match(r"(?i)d:/", t) else os.path.join(b, t)) for t in tries for b in bases):
                    found.append((p, raw))
    return found

def link_graph(text, canonical):
    """Graph link tak berarah antar semua file vault (log ikut sebagai penghubung), tanpa hub kontrol (index, hot, log)."""
    graph = defaultdict(set)
    for p, t in text.items():
        me = os.path.splitext(os.path.basename(p))[0]
        if me in CONTROL:
            continue
        for target in LINK.findall(CODE.sub("", t)):
            target = canonical.get(target.strip())
            if target and target != me and target not in CONTROL:
                graph[me].add(target)
                graph[target].add(me)
    return graph

def link_candidates(graph, folder, page, top=3):
    """Saran kaitan untuk satu halaman (Adamic-Adar): halaman system/ atau projects/ yang belum bertaut dengannya tetapi
    berbagi tetangga; tetangga berderajat kecil bernilai lebih. Per halaman, bukan daftar global: daftar global dikuasai
    halaman hub (uji 2026-10-16: 0/10 kaitan nyata di 10 besar global, 7/10 di peringkat 1 per halaman).
    Hanya saran untuk Kompilasi, tidak pernah dipasang otomatis."""
    scores = []
    for t, f in folder.items():
        if f in ("system", "projects") and t != page and t not in graph[page]:
            common = graph[page] & graph[t]
            s = sum(1 / math.log(len(graph[z])) for z in common if len(graph[z]) > 1)
            if s:
                scores.append((s, t, sorted(common, key=lambda z: len(graph[z]))[:2]))
    return sorted(scores, reverse=True)[:top]

def md_files(vault):
    for dp, dn, fn in os.walk(vault):
        dn[:] = [d for d in dn if not d.startswith(".")]
        for f in fn:
            if f.endswith(".md"):
                yield os.path.join(dp, f)

def main():
    parser = argparse.ArgumentParser(description="Lint vault Obsidian (Aturan 11). Hanya melapor, tidak mengubah apa pun.")
    parser.add_argument("vault", help="Path vault, mis. D:/Obsidian/All Sources/AI Workspace")
    parser.add_argument("--config", action="append", default=[], help="File JSON yang dicek validitasnya (boleh diulang)")
    parser.add_argument("--secrets-from", action="append", default=[], help="File konfigurasi; nilai secret-nya dicari di vault (Aturan 9)")
    parser.add_argument("--top", type=int, default=15, help="Jumlah link putus teratas yang ditampilkan")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    files = list(md_files(args.vault))
    names = {os.path.splitext(os.path.basename(p))[0]: p for p in files}
    text, empty, bom = {}, [], []
    for p in files:
        raw = open(p, "rb").read()
        if not raw.strip():
            empty.append(p)
        if raw.startswith(b"\xef\xbb\xbf"):
            bom.append(p)
        text[p] = raw.decode("utf-8", errors="replace")

    canonical = {n: n for n in names}   # nama atau alias → nama file halamannya
    for p, t in text.items():
        for a in aliases(t):
            canonical.setdefault(a, os.path.splitext(os.path.basename(p))[0])

    occurrences, referencing = Counter(), defaultdict(set)
    inbound = defaultdict(set)
    for p, t in text.items():
        for target in LINK.findall(CODE.sub("", t)):
            target = target.strip()
            occurrences[target] += 1
            referencing[target].add(p)
            name = canonical.get(target)
            if name and names[name] != p:
                inbound[name].add(p)
    broken = {t: n for t, n in occurrences.items() if t not in canonical}

    wiki = os.path.join(args.vault, "Wiki")
    wiki_pages = [p for p in files if p.startswith(wiki) and os.path.splitext(os.path.basename(p))[0] not in CONTROL]
    orphans = [p for p in wiki_pages if not inbound[os.path.splitext(os.path.basename(p))[0]]]
    # Konsep tanpa link langsung (arah mana pun) ke system/ atau projects/: riset yang dampaknya ke sistem kita belum ditulis (kasus D11)
    folder = {os.path.splitext(os.path.basename(p))[0]: os.path.relpath(p, wiki).split(os.sep)[0] for p in wiki_pages}
    neighbors = defaultdict(set)
    for p in wiki_pages:
        me = os.path.splitext(os.path.basename(p))[0]
        for target in LINK.findall(CODE.sub("", text[p])):
            target = canonical.get(target.strip(), target.strip())
            if target in folder and target != me:
                neighbors[me].add(target)
                neighbors[target].add(me)
    unlinked = sorted(n for n, f in folder.items() if f == "concepts" and not any(folder[m] in ("system", "projects") for m in neighbors[n]))
    workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    present = wiki_pages + [os.path.join(args.vault, "hot.md")]
    dead_paths = stale_paths([p for p in present if p in text], text, [args.vault, workspace, os.path.dirname(workspace)])
    graph = link_graph(text, canonical)
    suggestions = {n: link_candidates(graph, folder, n) for n in unlinked}
    index_text = text.get(os.path.join(args.vault, "index.md"), "")
    not_indexed = [p for p in wiki_pages if f"[[{os.path.splitext(os.path.basename(p))[0]}]]" not in index_text]

    hot = os.path.join(args.vault, "hot.md")
    hot_words = len(text.get(hot, "").split())

    bad_json = []
    for c in args.config:
        try:
            json.load(open(c, encoding="utf-8"))
        except (OSError, ValueError) as e:
            bad_json.append(f"{c}: {e}")

    secret_values = set()
    for s in args.secrets_from:
        try:
            secret_values.update(v for v in re.findall(r"(?i)[A-Z0-9_]*(?:SECRET|PASSWORD|TOKEN|API_KEY)[A-Z0-9_]*\s*[=:]\s*([^\s\"']+)", open(s, encoding="utf-8").read()) if len(v) >= 6)
        except OSError:
            pass
    leaked = sorted(p for p, t in text.items() if any(v in t for v in secret_values))

    rel = lambda p: os.path.relpath(p, args.vault)
    def section(title, items):
        print(f"\n## {title} — {len(items)}")
        for i in items:
            print(f"- {i}")

    print(f"# Lint Vault\n\nVault: `{args.vault}` · {len(files)} file .md (folder bertitik seperti `.obsidian` dilewati).")
    # Riset 2026-10-16: pola wiki dilaporkan patah di atas ±200 file; siapkan index per folder sebelum batas itu
    print(f"Wiki: {len(wiki_pages)} halaman" + (" ⚠️ mendekati batas ±200: siapkan index per folder." if len(wiki_pages) >= 180 else " (batas pantau ±200)."))
    section("File kosong (0 byte / hanya spasi)", [rel(p) for p in empty])
    section("File dengan BOM UTF-8", [rel(p) for p in bom])
    section("Halaman wiki yatim (tidak ada link masuk dari file lain)", [rel(p) for p in orphans])
    section("Halaman wiki yang tidak tercantum di index.md", [rel(p) for p in not_indexed])
    section("Rujukan path yang tidak ada lagi (halaman wiki dan hot.md)", [f"{rel(p)}: `{s}`" for p, s in dead_paths])
    print("\nMetrik: halaman di `Wiki/concepts/` yang tidak punya link langsung (masuk atau keluar) dengan halaman `Wiki/system/` atau `Wiki/projects/`. Kaitan ke sistem kita yang tidak ditulis tidak bisa ditemukan RAG (Aturan 11, Wiki-to-System).")
    print("Saran per konsep: halaman system/projects dengan skor Adamic-Adar tertinggi atas tetangga bersama (log ikut sebagai penghubung, hub kontrol tidak). Hanya saran: tulis kaitannya kalau memang nyata, atau tulis bahwa tidak ada.")
    section("Konsep tanpa kaitan ke sistem atau proyek", [f"[[{n}]]" + (" — saran: " + "; ".join(f"[[{t}]] (lewat {', '.join(c)})" for _, t, c in suggestions[n]) if suggestions[n] else "") for n in unlinked])
    print(f"\n## Link ke halaman yang tidak ada — {len(broken)} target")
    print("Metrik: *kemunculan* = total `[[...]]` di seluruh vault; *file* = jumlah file yang merujuk.")
    for t, n in sorted(broken.items(), key=lambda x: (-x[1], x[0]))[:args.top]:
        print(f"- [[{t}]] — {n} kemunculan, {len(referencing[t])} file")
    print(f"\n## hot.md — {hot_words} kata " + ("⚠️ di atas batas ~500" if hot_words > 500 else "(di bawah batas ~500)"))
    stale = rag_staleness(args.vault)
    if stale is None:
        print("\n## Index RAG — vault ini belum punya manifest; jalankan `rag_engine.py index <vault>`")
    else:
        print(f"\n## Index RAG — {len(stale[0])} file berubah atau baru, {len(stale[1])} terhapus sejak index terakhir")
        print("Metrik: hash isi file dibanding `tools/rag_db/manifest.json`. Disegarkan otomatis saat `rag_engine.py search` berikutnya.")
        for r in sorted(stale[0] + stale[1])[:args.top]:
            print(f"- {r}")
    section("Config JSON tidak valid", bad_json)
    section("File vault yang memuat nilai secret (Aturan 9)", [rel(p) for p in leaked])
    print("\n## Tidak dicek skrip ini\n- Kontradiksi dan klaim basi antar-catatan: perlu dibaca agent.")

if __name__ == "__main__":
    main()
