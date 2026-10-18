import sys
import os
import re
import json
import argparse

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

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Ekspor transkrip Claude Code (JSONL) ke Markdown")
    parser.add_argument("transcript", nargs="?", help="Path file .jsonl. Jika kosong, dibaca dari JSON hook di stdin (transcript_path)")
    parser.add_argument("--out", required=True, help="Folder tujuan file Markdown")
    parser.add_argument("--secrets-from", action="append", help="File konfigurasi yang nilai secret-nya ikut disensor di mana pun muncul (boleh diulang)")
    parser.add_argument("--max-result", type=int, default=3000, help="Batas karakter per hasil tool (0 = penuh)")
    parser.add_argument("--projects-root", help="Mode semua proyek, mis. D:/CODE: hanya sesi di dalam folder proyek di bawahnya "
                                                "yang diekspor, ke <out>/<proyek>/; folder kerja dibaca dari JSON hook")
    parser.add_argument("--skip", action="append", default=[], help="Nama folder proyek yang dilewati, mis. 'AI Agent' (boleh diulang)")
    args = parser.parse_args()

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
