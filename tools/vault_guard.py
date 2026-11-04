"""Hook sebelum tool menulis: tolak tulisan ke vault kalau teks barunya memuat nomor dokumen identitas,
kata terlarang, atau secret (protokol D:\\CODE bagian Always, Aturan 9). Dipakai PreToolUse Claude Code
(Write/Edit/MultiEdit) dan pre_tool_call Hermes (write_file/patch, sejak 2026-11-03). Input JSON hook di stdin;
keluar 2 dengan alasan di stderr berarti diblokir, 0 berarti lanjut. Gagal memeriksa juga keluar 2 (fail closed).
Daftar kata terlarang dan nilai secret dibaca dari file lokal yang diberikan lewat argumen, jadi nilainya tidak
pernah tertulis di skrip ini. Batasnya: hanya tool tulis berkas; tulisan lewat skrip shell atau Python tidak terlihat."""
import os
import re
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from export_transcript import SECRET_ASSIGNMENT, known_secrets  # satu definisi secret untuk semua tool (Aturan 6)

NOMOR = re.compile(r"(?<!\d)\d{16}(?!\d)")       # NIK dan nomor KK: 16 digit (NRP boleh sejak 2026-10-21)
PLACEHOLDER = ("<", "[", "$", "{", "*", ".", "%")  # API_KEY=<kunci>, TOKEN: [DISENSOR], ${VAR} bukan secret
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "write_file", "patch")  # Claude Code, lalu Hermes
V4A_FILE = re.compile(r"(?m)^\*\*\* (?:Add File|Update File|Move to): *(.+?) *$")  # berkas di patch V4A Hermes

def banned_words(path):
    """Satu entri per baris; baris kosong dan baris yang diawali # dilewati."""
    if not path:
        return []
    with open(path, encoding="utf-8") as f:
        return [l.strip().lower() for l in f if l.strip() and not l.lstrip().startswith("#")]

def new_text(tool_input):
    """Hanya teks yang akan ditulis; isi lama file tidak ikut diperiksa supaya edit kecil tidak tertahan."""
    edits = [e.get("new_string") for e in tool_input.get("edits") or [] if isinstance(e, dict)]
    return "\n".join(str(t) for t in [tool_input.get("content"), tool_input.get("new_string"),
                                      tool_input.get("patch"), *edits] if t)

def targets(hook):
    """Path tujuan: file_path (Claude), path (Hermes, bisa relatif ke cwd sesi), dan berkas di patch V4A Hermes.
    Path gaya Git Bash (/d/...) diubah ke D:/... supaya tetap dikenali."""
    ti = hook.get("tool_input") or {}
    base = str(hook.get("cwd") or os.getcwd())
    paths = [ti.get("file_path"), ti.get("path"), *V4A_FILE.findall(str(ti.get("patch") or ""))]
    return [os.path.join(base, re.sub(r"^/([a-zA-Z])/", r"\1:/", str(p).strip())) for p in paths if p and str(p).strip()]

def inside(path, folder):
    path, folder = (os.path.normcase(os.path.abspath(p)) for p in (path, folder))
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:  # beda drive
        return False

def reasons(text, banned, secrets):
    low = text.lower()
    found = []
    if any(w in low for w in banned):
        found.append("kata dari daftar terlarang (data pribadi)")
    if NOMOR.search(text):
        found.append("angka 16 digit yang mirip NIK atau nomor KK")
    if any(v in text for v in secrets):
        found.append("nilai secret yang dikenal")
    if any(len(m.group(2)) >= 8 and not m.group(2).startswith(PLACEHOLDER) for m in SECRET_ASSIGNMENT.finditer(text)):
        found.append("assignment yang mirip secret")
    return found

def main():
    sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Hook sebelum tool menulis: tolak tulisan ke vault yang memuat data pribadi atau secret.")
    p.add_argument("--vault", required=True, help="Folder vault yang dijaga")
    p.add_argument("--words", help="File daftar kata terlarang (lokal, tidak di-commit)")
    p.add_argument("--secrets-from", action="append", default=[], help="File konfigurasi yang nilai secret-nya ikut dicari (boleh diulang)")
    a = p.parse_args()  # argumen salah: argparse keluar dengan kode 2, jadi tetap diblokir
    try:
        hook = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        ti = hook.get("tool_input") or {}
        hit = [t for t in targets(hook) if inside(t, a.vault)] if hook.get("tool_name") in WRITE_TOOLS else []
        if not hit:
            return 0
        found = reasons(new_text(ti), banned_words(a.words), known_secrets(a.secrets_from))
        if found:
            print(f"Ditolak penjaga vault: tulisan ke {hit[0]} memuat {', '.join(found)}. "
                  "Ganti bagian itu dengan penanda seperti <nik> atau <nama> (protokol D:\\CODE, bagian Always).", file=sys.stderr)
            return 2
        return 0
    except Exception as e:  # gagal berarti tolak (fail closed), bukan diam-diam lolos
        print(f"Penjaga vault gagal memeriksa ({type(e).__name__}: {e}); tulisan ditolak supaya aman.", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
