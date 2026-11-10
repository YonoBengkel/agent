import sys
import os
import re
import json
import sqlite3
import pathlib
import argparse
import datetime
import urllib.parse

def as_text(content):
    """Ambil teks dari content yang bisa berupa string atau list blok."""
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if b.get("type") == "text":
            parts.append(b.get("text", ""))
        elif b.get("type") == "image":
            parts.append("[gambar]")
    return "\n".join(parts)

def clip(text, limit):
    if limit and len(text) > limit:
        return text[:limit] + f"\n\n[... dipotong, {len(text) - limit} karakter lagi — pakai --max-result 0 untuk versi penuh]"
    return text

# Nilai dari assignment seperti JWT_SECRET=..., DB_PASSWORD: ..., API_KEY=... (Aturan 9).
SECRET_ASSIGNMENT = re.compile(r"(?i)\b([A-Z0-9_]*(?:SECRET|PASSWORD|PASSWD|TOKEN|API_KEY)[A-Z0-9_]*\s*[=:]\s*)([^\s\"'\\,]+)")

def known_secrets(paths):
    """Nilai secret dari file konfigurasi (mis. docker-compose.yml, .env), agar kemunculannya di teks bebas ikut disensor."""
    values = set()
    for p in paths or []:
        try:
            with open(p, encoding="utf-8") as f:
                values.update(m.group(2) for m in SECRET_ASSIGNMENT.finditer(f.read()))
        except OSError:
            pass
    return sorted((v for v in values if len(v) >= 6), key=len, reverse=True)

def project_of(cwd, root, skip):
    """Folder proyek (tingkat pertama di bawah root) tempat sesi berjalan. None kalau sesi di luar root,
    proyeknya dilewati, atau proyeknya memakai .no-vault (D:\\CODE\\AGENTS.md)."""
    try:
        rel = os.path.relpath(os.path.abspath(cwd), os.path.abspath(root))
    except ValueError:   # beda drive di Windows
        return None
    if rel == "." or rel.startswith(".."):
        return None
    project = rel.split(os.sep)[0]
    folder = os.path.join(os.path.abspath(root), project)
    if project in skip or os.path.exists(os.path.join(folder, ".no-vault")):
        return None
    return folder

def env_files(folder):
    """File .env* di folder proyek dan satu tingkat di bawahnya; nilai secret-nya ikut disensor (Aturan 9)."""
    bases = [folder]
    try:
        bases += [os.path.join(folder, d) for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d))
                  and d not in ("node_modules", ".git") and "venv" not in d.lower()]
    except OSError:
        pass
    found = []
    for b in bases:
        try:
            found += [os.path.join(b, f) for f in os.listdir(b) if f.startswith(".env") and os.path.isfile(os.path.join(b, f))]
        except OSError:
            pass
    return found

def redact(text, literals=()):
    """Sensor nilai secret sebelum transkrip ditulis ke disk."""
    for v in literals:
        text = text.replace(v, "[DISENSOR]")
    return SECRET_ASSIGNMENT.sub(lambda m: m.group(1) + "[DISENSOR]", text)

def fence(text):
    """Code fence yang lebih panjang dari backtick mana pun di dalam teks."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)

def convert(transcript_path, max_result, literals=()):
    title, session_id, started = None, None, None
    out = []
    for line in open(transcript_path, encoding="utf-8"):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = d.get("type")
        if t == "custom-title":
            title = d.get("customTitle") or title
        session_id = session_id or d.get("sessionId")
        if t not in ("user", "assistant") or d.get("isMeta") or d.get("isSidechain"):
            continue
        started = started or d.get("timestamp")
        content = (d.get("message") or {}).get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content or [])
        for b in blocks:
            bt = b.get("type")
            if bt == "text" and b.get("text", "").strip():
                out.append(f"### [{'USER' if t == 'user' else 'ASSISTANT'}]\n\n{b['text'].strip()}\n")
            elif bt == "tool_use":
                body = json.dumps(b.get("input", {}), ensure_ascii=False, indent=2)
                f = fence(body)
                out.append(f"### [TOOL CALL] `{b.get('name')}`\n\n{f}json\n{body}\n{f}\n")
            elif bt == "tool_result":
                body = clip(as_text(b.get("content")), max_result)
                f = fence(body)
                label = "TOOL RESULT (error)" if b.get("is_error") else "TOOL RESULT"
                out.append(f"### [{label}]\n\n{f}\n{body}\n{f}\n")
            # Blok thinking dilewati: di transkrip Claude Code isinya kosong (hanya signature).
    header = [
        f"# {title or 'Sesi Claude Code'}",
        "",
        f"> Transkrip sesi [[Claude Code]], diekspor otomatis oleh `tools/export_transcript.py`.",
        f"> Session: `{session_id}` · Mulai: {started}",
        "> Penalaran internal (thinking) tidak ikut karena tidak tersimpan di transkrip.",
        "",
        "---",
        "",
    ]
    return title, session_id, started, redact("\n".join(header) + "\n".join(out), literals)

def tool_call(name, body):
    f = fence(body)
    return f"### [TOOL CALL] `{name}`\n\n{f}json\n{body}\n{f}\n"

def tool_result(body, max_result):
    body = clip(body, max_result)
    f = fence(body)
    return f"### [TOOL RESULT]\n\n{f}\n{body}\n{f}\n"

def header(title, agent, ident, started):
    return "\n".join([f"# {title}", "", f"> Transkrip [[{agent}]], diekspor oleh `tools/export_transcript.py`.",
                      f"> Percakapan: `{ident}` · Mulai: {started}",
                      "> Penalaran internal (thinking) dan pesan sistem tidak ikut.", "", "---", ""])

def antigravity_md(path, max_result):
    """Transkrip Antigravity (transcript_full.jsonl): masukan pengguna, jawaban, panggilan alat, dan hasilnya (2026-11-10)."""
    out, started = [], None
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        started = started or d.get("created_at")
        t, isi = d.get("type"), (d.get("content") or "")
        if t == "USER_INPUT":
            teks = re.sub(r"(?s)<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>|</?USER_REQUEST>", "", isi).strip()
            if teks:
                out.append(f"### [USER]\n\n{teks}\n")
        elif t == "PLANNER_RESPONSE":
            if isi.strip():
                out.append(f"### [ASSISTANT]\n\n{isi.strip()}\n")
            out += [tool_call(c.get("name"), json.dumps(c.get("args") or {}, ensure_ascii=False, indent=2)) for c in d.get("tool_calls") or []]
        elif t == "GENERIC" and isi.strip():
            out.append(tool_result(isi, max_result))
    return started, out

def hermes_md(db, sid, max_result):
    """Satu sesi Hermes dari state.db: pesan pengguna, jawaban, panggilan alat, dan hasilnya (2026-11-10)."""
    out = []
    for role, isi, calls in db.execute("SELECT role, content, tool_calls FROM messages WHERE session_id = ? ORDER BY id", (sid,)):
        isi = isi or ""
        if role == "user" and isi.strip():
            out.append(f"### [USER]\n\n{isi.strip()}\n")
        elif role == "assistant":
            if isi.strip():
                out.append(f"### [ASSISTANT]\n\n{isi.strip()}\n")
            try:
                daftar = json.loads(calls or "[]")
            except ValueError:
                daftar = []
            out += [tool_call((c.get("function") or {}).get("name"), (c.get("function") or {}).get("arguments") or "{}") for c in daftar]
        elif role == "tool" and isi.strip():
            out.append(tool_result(isi, max_result))
    return out

def uri_path(uri):
    """file:///d%3A/CODE/X menjadi d:/CODE/X."""
    s = urllib.parse.unquote(str(uri))
    return re.sub(r"^file:/+", "", s) if s.startswith("file:") else s

def tulis_jika_berubah(dest, md):
    """Tulis hanya kalau isinya berbeda, supaya ekspor ulang tidak menyentuh berkas yang sama. newline="" di kedua arah:
    keluaran alat sering memuat \\r, dan terjemahan baris baru membuat isi yang sama selalu tampak berbeda."""
    if os.path.exists(dest) and open(dest, encoding="utf-8", newline="").read() == md:
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="") as f:
        f.write(md)
    return True

def nama_berkas(date, agent, title, ident):
    bersih = re.sub(r'[<>:"/\\|?*\n]', "", title).strip()[:70]
    return f"{date} {agent} {bersih} ({str(ident)[:8]}).md"

def buka_db(path):
    """Buka SQLite hanya-baca, supaya basis data agent lain tidak pernah tertulis."""
    return sqlite3.connect(pathlib.Path(path).as_uri() + "?mode=ro", uri=True)

def ekspor_lain(args, secrets):
    """Mode --format antigravity atau hermes: ekspor semua percakapan yang folder kerjanya proyek di bawah --projects-root.
    Proyek .no-vault, proyek yang sudah tidak ada, dan folder di luar root (misalnya D:\\KULIAH) dilewati tanpa dibaca."""
    tulis = lewat = 0
    def proyek(path):
        folder = project_of(path, args.projects_root, set(args.skip)) if path else None
        return folder if folder and os.path.isdir(folder) else None
    if args.format == "antigravity":
        # App dan CLI berbagi ID percakapan, jadi satu percakapan bisa tercatat di dua folder data: ambil transkrip terbesar.
        # Percakapan lama tanpa transcript_full.jsonl hanya tersimpan sebagai protobuf di conversations/<id>.db dan tidak diekspor.
        semua, pilihan = set(), {}
        for app in args.app_dir:
            dbp = os.path.join(app, "conversation_summaries.db")
            if not os.path.exists(dbp):
                continue
            db = buka_db(dbp)
            rows = list(db.execute("SELECT conversation_id, title, workspace_uris, nesting_depth FROM conversation_summaries"))
            db.close()
            for cid, title, ws, depth in rows:
                semua.add(cid)
                try:
                    paths = [uri_path(u) for u in json.loads(ws or "[]")]
                except ValueError:
                    paths = []
                folder = next((f for f in map(proyek, paths) if f), None)
                path = os.path.join(app, "brain", cid, ".system_generated", "logs", "transcript_full.jsonl")
                if folder and not depth and os.path.exists(path) and os.path.getsize(path) > pilihan.get(cid, (-1,))[0]:
                    pilihan[cid] = (os.path.getsize(path), path, title, folder)
        for cid, (_, path, title, folder) in pilihan.items():
            started, out = antigravity_md(path, args.max_result)
            md = redact(header(title or "Percakapan Antigravity", "Antigravity IDE", cid, started) + "\n".join(out),
                        known_secrets(secrets + env_files(folder)))
            dest = os.path.join(args.out, os.path.basename(folder),
                                nama_berkas((started or "")[:10] or "tanpa-tanggal", "Antigravity", title or "percakapan", cid))
            tulis += tulis_jika_berubah(dest, md)
        lewat = len(semua) - len(pilihan)
    else:
        for sdb in args.state_db:   # state.db utama dan milik profil, mis. profiles/pekerja/state.db
            db = buka_db(sdb)
            for sid, title, cwd, started in db.execute("SELECT id, title, cwd, started_at FROM sessions WHERE parent_session_id IS NULL"):
                folder = proyek(cwd)
                if not folder:
                    lewat += 1
                    continue
                tanggal = datetime.datetime.fromtimestamp(started).strftime("%Y-%m-%d") if isinstance(started, (int, float)) else str(started or "")[:10]
                md = redact(header(title or "Sesi Hermes", "Hermes Agent", sid, tanggal) + "\n".join(hermes_md(db, sid, args.max_result)),
                            known_secrets(secrets + env_files(folder)))
                dest = os.path.join(args.out, os.path.basename(folder),   # ID Hermes berawalan local-, ambil hash-nya
                                    nama_berkas(tanggal or "tanpa-tanggal", "Hermes", title or "sesi", str(sid).removeprefix("local-")))
                tulis += tulis_jika_berubah(dest, md)
            db.close()
    print(f"[SUCCESS] {args.format}: {tulis} berkas ditulis atau diperbarui, {lewat} percakapan dilewati")

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Ekspor transkrip Claude Code (JSONL) ke Markdown, atau semua percakapan Antigravity "
                                                 "dan Hermes di proyek bawah --projects-root")
    parser.add_argument("transcript", nargs="?", help="Path file .jsonl. Jika kosong, dibaca dari JSON hook di stdin (transcript_path)")
    parser.add_argument("--out", required=True, help="Folder tujuan file Markdown")
    parser.add_argument("--secrets-from", action="append", help="File konfigurasi yang nilai secret-nya ikut disensor di mana pun muncul (boleh diulang)")
    parser.add_argument("--max-result", type=int, default=3000, help="Batas karakter per hasil tool (0 = penuh)")
    parser.add_argument("--projects-root", help="Mode semua proyek, mis. D:/CODE: hanya sesi di dalam folder proyek di bawahnya "
                                                "yang diekspor, ke <out>/<proyek>/; folder kerja dibaca dari JSON hook")
    parser.add_argument("--skip", action="append", default=[], help="Nama folder proyek yang dilewati, mis. 'AI Agent' (boleh diulang)")
    parser.add_argument("--format", choices=("claude", "antigravity", "hermes"), default="claude",
                        help="claude: satu transkrip JSONL atau dari hook. antigravity dan hermes: semua percakapan, butuh --projects-root")
    parser.add_argument("--app-dir", action="append", default=[], help="Folder data Antigravity, mis. ~/.gemini/antigravity (boleh diulang)")
    parser.add_argument("--state-db", action="append", default=[], help="Path state.db Hermes (boleh diulang untuk profil lain)")
    args = parser.parse_args()

    if args.format != "claude":
        if not args.projects_root or (args.format == "antigravity" and not args.app_dir) or (args.format == "hermes" and not args.state_db):
            parser.error("--format antigravity butuh --projects-root dan --app-dir, --format hermes butuh --projects-root dan --state-db")
        return ekspor_lain(args, list(args.secrets_from or []))

    hook, path, out, secrets = {}, args.transcript, args.out, list(args.secrets_from or [])
    if not path:
        hook = json.load(sys.stdin)
        path = hook.get("transcript_path")
    if args.projects_root:
        folder = project_of(hook.get("cwd") or os.getcwd(), args.projects_root, set(args.skip))
        if not folder:
            return   # di luar proyek, dilewati, atau .no-vault: tidak diarsipkan
        out = os.path.join(out, os.path.basename(folder))
        secrets += env_files(folder)
    if not path or not os.path.exists(path):
        print(f"[ERROR] Transkrip tidak ditemukan: {path}", file=sys.stderr)
        sys.exit(1)

    title, session_id, started, md = convert(path, args.max_result, known_secrets(secrets))
    date = (started or "")[:10] or "tanpa-tanggal"
    name = re.sub(r'[<>:"/\\|?*]', "", title or session_id or "sesi").strip()[:80]
    os.makedirs(out, exist_ok=True)
    dest = os.path.join(out, f"{date} {name} ({(session_id or 'x')[:8]}).md")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[SUCCESS] {dest}")

if __name__ == "__main__":
    main()
