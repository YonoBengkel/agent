import os
import re
import sys
import json
import math
import hashlib
import time
import fnmatch
import argparse
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vault_guard  # pola yang sama dengan hook penjaga, supaya cek ini jalan juga untuk agent tanpa hook

LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)   # Obsidian tidak menganggap [[...]] di dalam kode sebagai link
CONTROL = {"hot", "index", "log", "log_id", "KONTEKS_PROYEK"}
FRONTMATTER = re.compile(r"\A﻿?---\r?\n(.*?)\r?\n---", re.S)
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rag_db", "manifest.json")   # ditulis rag_engine.py

def page_name(target):
    """Nama halaman tujuan link tanpa folder dan tanpa `.md`, karena Obsidian juga me-resolve [[Folder/Nama.md]]."""
    name = os.path.basename(target.strip())
    return name[:-3] if name.lower().endswith(".md") else name

def aliases(text):
    """Nilai `aliases` di frontmatter, bentuk [a, b] atau daftar '- a'. Alias dihitung sebagai nama halaman untuk link masuk,
    tapi link `[[alias]]` biasa juga dilaporkan terpisah: saat alias dipilih, Obsidian menulis `[[Halaman|alias]]`
    "rather than just using the alias as the link destination" (dokumentasi Aliases, dibaca 2026-10-20)."""
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
            target = canonical.get(page_name(target))
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

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build", ".claude", ".cache"}
LOG_FOLDER = re.compile(r"Folder log[^`\n]*`(Log/[^`]+)`")
day = lambda t: time.strftime("%Y-%m-%d", time.localtime(t))

def latest_mtime(folder, ext=None):
    """Waktu ubah file terbaru di folder (folder build dan venv dilewati); None kalau tidak ada file."""
    best = None
    for dp, dn, fn in os.walk(folder):
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.endswith("-venv")]
        for f in fn:
            if ext and not f.endswith(ext):
                continue
            try:
                m = os.path.getmtime(os.path.join(dp, f))
            except OSError:
                continue
            best = m if best is None or m > best else best
    return best

def project_activity(vault, projects_root, pages, active_days=14, skip=("AI Agent",)):
    """Protokol D:\\CODE: perubahan di proyek dicatat di log dan halaman proyek. Kembalikan (proyek yang berubah
    di hari yang lebih baru daripada log atau halamannya, folder aktif tanpa halaman proyek)."""
    stale, unpaged = [], []
    for name in sorted(os.listdir(projects_root)):
        folder = os.path.join(projects_root, name)
        if name in skip or not os.path.isdir(folder) or os.path.exists(os.path.join(folder, ".no-vault")):
            continue
        changed = latest_mtime(folder)
        if changed is None:
            continue
        if name not in pages:   # folder mata kuliah dicatat di Log/Kuliah/<nama> (D:\KULIAH\AGENTS.md), itu dihitung tercatat
            logged = any(os.path.isdir(os.path.join(vault, l)) for l in (f"Log/{name}", f"Log/Kuliah/{name}"))
            if not logged and time.time() - changed < active_days * 86400:
                unpaged.append((name, day(changed)))
            continue
        path, page_text = pages[name]
        m = LOG_FOLDER.search(page_text)
        logs = [m.group(1)] if m else [f"Log/{name}", f"Log/Kuliah/{name}"]
        noted = max([t for t in (latest_mtime(os.path.join(vault, l), ".md") for l in logs) if t] + [os.path.getmtime(path)])
        if day(changed) > day(noted):
            stale.append((name, day(changed), day(noted)))
    return stale, unpaged

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
    parser.add_argument("--words", help="Daftar kata terlarang yang sama dengan hook penjaga (Konfigurasi/penjaga_vault_terlarang.txt)")
    parser.add_argument("--projects-root", help="Folder proyek, mis. D:/CODE: cek proyek yang berubah tanpa log (lambat, ±30 detik)")
    parser.add_argument("--active-days", type=int, default=14, help="Folder yang berubah dalam sekian hari dianggap aktif")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    files = list(md_files(args.vault))
    names = {os.path.splitext(os.path.basename(p))[0]: p for p in files}
    text, empty, bom, control = {}, [], [], []
    for p in files:
        raw = open(p, "rb").read()
        if not raw.strip():
            empty.append(p)
        if raw.startswith(b"\xef\xbb\xbf"):
            bom.append(p)
        text[p] = raw.decode("utf-8", errors="replace")
        if any(ord(c) < 32 and c not in "\r\n\t" for c in text[p]):   # sisa escape yang rusak, mis. \b atau \f (Pelajaran #11)
            control.append(p)

    canonical = {n: n for n in names}   # nama atau alias → nama file halamannya
    for p, t in text.items():
        for a in aliases(t):
            canonical.setdefault(a, os.path.splitext(os.path.basename(p))[0])

    occurrences, referencing = Counter(), defaultdict(set)
    inbound = defaultdict(set)
    for p, t in text.items():
        for target in LINK.findall(CODE.sub("", t)):
            target = page_name(target)
            occurrences[target] += 1
            referencing[target].add(p)
            name = canonical.get(target)
            if name and names[name] != p:
                inbound[name].add(p)
    broken = {t: n for t, n in occurrences.items() if t not in canonical}
    via_alias = {t: n for t, n in occurrences.items() if t in canonical and t not in names}

    wiki = os.path.join(args.vault, "Wiki")
    wiki_pages = [p for p in files if p.startswith(wiki) and os.path.splitext(os.path.basename(p))[0] not in CONTROL]
    orphans = [p for p in wiki_pages if not inbound[os.path.splitext(os.path.basename(p))[0]]]
    # Konsep tanpa link langsung (arah mana pun) ke system/ atau projects/: riset yang dampaknya ke sistem kita belum ditulis (kasus D11)
    folder = {os.path.splitext(os.path.basename(p))[0]: os.path.relpath(p, wiki).split(os.sep)[0] for p in wiki_pages}
    neighbors = defaultdict(set)
    for p in wiki_pages:
        me = os.path.splitext(os.path.basename(p))[0]
        for target in LINK.findall(CODE.sub("", text[p])):
            target = canonical.get(page_name(target), page_name(target))
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
    banned = vault_guard.banned_words(args.words)
    forbidden = [(p, found) for p in sorted(text) if (found := vault_guard.reasons(text[p], banned, []))]

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
    section("File dengan karakter kontrol (escape backslash yang rusak)", [rel(p) for p in control])
    section("Halaman wiki yatim (tidak ada link masuk dari file lain)", [rel(p) for p in orphans])
    section("Halaman wiki yang tidak tercantum di index.md", [rel(p) for p in not_indexed])
    section("Rujukan path yang tidak ada lagi (halaman wiki dan hot.md)", [f"{rel(p)}: `{s}`" for p, s in dead_paths])
    print("\nMetrik: halaman di `Wiki/concepts/` yang tidak punya link langsung (masuk atau keluar) dengan halaman `Wiki/system/` atau `Wiki/projects/`. Kaitan ke sistem kita yang tidak ditulis tidak bisa ditemukan RAG (Aturan 11, Wiki-to-System).")
    print("Saran per konsep: halaman system/projects dengan skor Adamic-Adar tertinggi atas tetangga bersama (log ikut sebagai penghubung, hub kontrol tidak). Hanya saran: tulis kaitannya kalau memang nyata, atau tulis bahwa tidak ada.")
    section("Konsep tanpa kaitan ke sistem atau proyek", [f"[[{n}]]" + (" — saran: " + "; ".join(f"[[{t}]] (lewat {', '.join(c)})" for _, t, c in suggestions[n]) if suggestions[n] else "") for n in unlinked])
    # Aturan 3 meminta nama tool dan entitas tetap di-link; yang jarang dirujuk sengaja dibiarkan sebagai node graph (2026-10-20)
    wanted = {t: n for t, n in broken.items() if len(referencing[t]) >= 3}
    print(f"\n## Link ke halaman yang tidak ada — {len(broken)} target, {len(wanted)} dirujuk dari ≥3 file")
    print("Metrik: *kemunculan* = total `[[...]]` di seluruh vault; *file* = jumlah file yang merujuk. Yang didaftar hanya target "
          "yang dirujuk dari 3 file atau lebih, sebagai kandidat halaman baru (Aturan 11); yang lebih jarang dibiarkan sebagai node graph (Aturan 3).")
    for t, n in sorted(wanted.items(), key=lambda x: (-len(referencing[x[0]]), -x[1], x[0]))[:args.top]:
        print(f"- [[{t}]] — {n} kemunculan, {len(referencing[t])} file")
    print(f"\n## Link lewat alias — {len(via_alias)} target")
    print("Metrik: `[[alias]]` biasa yang hanya cocok dengan alias, bukan nama file. Kemungkinan tampil sebagai node abu-abu di Graph View; tulis sebagai `[[Halaman|alias]]`.")
    for t, n in sorted(via_alias.items(), key=lambda x: (-x[1], x[0])):
        print(f"- [[{t}]] → [[{canonical[t]}]] — {n} kemunculan: {', '.join(sorted(rel(p) for p in referencing[t]))}")
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
    print("\nMetrik: pola `tools/vault_guard.py` (angka 16 digit, kata terlarang, assignment mirip secret) atas seluruh isi file. "
          "Menangkap juga tulisan yang lolos dari hook, misalnya lewat skrip atau agent tanpa hook.")
    section("File vault yang memuat teks terlarang (protokol D:\\CODE, Always)", [f"{rel(p)}: {', '.join(f)}" for p, f in forbidden])
    if args.projects_root:
        pages = {os.path.splitext(os.path.basename(p))[0]: (p, text[p]) for p in wiki_pages if os.sep + "projects" + os.sep in p}
        stale, unpaged = project_activity(args.vault, args.projects_root, pages, args.active_days)
        print("\nMetrik: tanggal file terbaru di folder proyek (tanpa .git, node_modules, venv, build) dibanding tanggal log "
              "terbaru di folder log yang disebut halaman proyek (atau `Log/<nama>`, `Log/Kuliah/<nama>`) dan tanggal halamannya.")
        section("Proyek yang berubah sesudah log atau halaman terakhirnya", [f"{n}: file {c}, catatan {l}" for n, c, l in stale])
        section(f"Folder aktif ({args.active_days} hari) tanpa halaman proyek maupun folder log", [f"{n}: file {c}" for n, c in unpaged])
    print("\n## Tidak dicek skrip ini\n- Kontradiksi dan klaim basi antar-catatan: perlu dibaca agent.")

if __name__ == "__main__":
    main()
