"""Penjaga desain: hook sebelum alat menulis, untuk aturan Referensi Desain di protokol D:\\CODE (sejak 2026-11-08).
Membuat berkas tampilan baru (.html, .css, .jsx, .tsx, .vue, .svelte, dan sejenisnya) atau menulis DESIGN.md di proyek di
bawah --projects-root ditolak, selama halaman Referensi Desain belum dibaca di sesi itu. Proyek dengan .no-vault dilewati.
Mengubah berkas tampilan yang sudah ada tetap boleh, supaya perbaikan kecil tidak tertahan. Tulisan ke DESIGN.md yang memuat
tautan [[...]] ke halaman vault juga ditolak, karena DESIGN.md hanya menyebut referensi publik (uji Hermes 2026-11-08).

Tiga format hook:
- claude: PreToolUse Claude Code (sejak 2026-11-10). Keluar 2 dengan alasan di stderr. Riwayat baca dari transcript_path.
- hermes: pre_tool_call Hermes. Keluar 2 dengan alasan di stderr berarti ditolak. Riwayat baca dari state.db.
- antigravity: PreToolUse Antigravity. Keputusan berupa JSON di stdout, selalu keluar 0, karena hook yang gagal ikut
  menggagalkan alatnya. Riwayat baca dari transkrip sesi (transcriptPath).
Ini pengingat, bukan pagar keamanan: gagal memeriksa berarti lolos (fail open), kebalikan dari vault_guard.py."""
import os
import re
import sys
import json
import sqlite3
import pathlib
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vault_guard as g  # path tujuan Hermes, folder sesi dari state.db, dan cek di dalam folder (Aturan 6)

HALAMAN = "Referensi Desain.md"
# Nama berkas utuh, didahului pemisah path atau kutip: membaca "Lampiran Referensi Desain.md" tidak dihitung (2026-11-08)
HALAMAN_UTUH = re.compile(r"(?:^|[\\/\"'])Referensi Desain\.md")
WIKILINK = re.compile(r"\[\[[^\]\n]+\]\]")  # tautan ke halaman vault, yang tidak boleh masuk DESIGN.md (repo bisa publik)
TAMPILAN = (".html", ".htm", ".css", ".scss", ".sass", ".less", ".jsx", ".tsx", ".vue", ".svelte", ".astro")
TULIS = {"hermes": ("write_file", "patch"),
         "antigravity": ("write_file", "edit_file", "write_to_file", "replace_file_content", "multi_replace_file_content"),
         "claude": ("Write", "Edit", "MultiEdit")}
BACA = {"hermes": ("read_file", "search_files", "terminal"),
        "antigravity": ("read_file", "view_file", "grep_search", "run_command"),
        "claude": ("Read", "Bash", "PowerShell")}


def tujuan(fmt, hook):
    """Path penuh yang akan ditulis panggilan ini, atau [] kalau bukan alat tulis."""
    if fmt in ("hermes", "claude"):
        if hook.get("tool_name") not in TULIS[fmt]:
            return []
        folder = g.session_cwd(hook) if fmt == "hermes" else None  # cwd di payload Hermes hanyalah folder gateway
        return g.targets({**hook, "cwd": folder} if folder else hook)
    call = hook.get("toolCall") or {}
    if call.get("name") not in TULIS[fmt]:
        return []
    args = call.get("args") or {}
    base = next(iter(hook.get("workspacePaths") or []), None) or os.getcwd()
    paths = [args.get(k) for k in ("Path", "TargetFile", "AbsolutePath", "FilePath")]
    return [os.path.join(base, os.path.expanduser(str(p).strip().strip('"'))) for p in paths if p and str(p).strip()]


def wajib_referensi(path, root):
    """(proyek, jenis) kalau tulisan ini keputusan desain di proyek yang memakai vault, atau None."""
    if not g.inside(path, root):
        return None
    bagian = os.path.relpath(os.path.abspath(path), os.path.abspath(root)).split(os.sep)
    if len(bagian) < 2 or os.path.exists(os.path.join(root, bagian[0], ".no-vault")):
        return None  # berkas langsung di root bukan milik proyek mana pun
    nama = os.path.basename(path)
    if nama == "DESIGN.md":
        return bagian[0], "DESIGN.md"
    if nama.lower().endswith(TAMPILAN) and not os.path.exists(path):
        return bagian[0], "berkas tampilan baru"
    return None


def menyebut_halaman(fmt, nama, args):
    teks = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
    return nama in BACA[fmt] and HALAMAN_UTUH.search(teks) is not None


def sudah_baca(fmt, hook):
    """Apakah alat baca sudah membuka halaman Referensi Desain di sesi ini. Riwayat yang tidak terlihat dianggap sudah."""
    if fmt == "hermes":
        home, sesi = os.environ.get("HERMES_HOME"), hook.get("session_id")
        if not home or not sesi:
            return True
        db = sqlite3.connect(pathlib.Path(home, "state.db").as_uri() + "?mode=ro", uri=True, timeout=5)
        try:
            rows = db.execute("SELECT tool_calls FROM messages WHERE session_id = ? AND role = 'assistant' AND tool_calls LIKE ?",
                              (sesi, f"%{HALAMAN}%")).fetchall()
        finally:
            db.close()
        for (calls,) in rows:
            for c in json.loads(calls or "[]"):
                f = c.get("function") or {}
                if menyebut_halaman(fmt, f.get("name"), f.get("arguments") or ""):
                    return True
        return False
    transkrip = hook.get("transcriptPath") or hook.get("transcript_path")
    if not transkrip or not os.path.exists(transkrip):
        return True
    with open(transkrip, encoding="utf-8", errors="replace") as f:
        for baris in f:
            if HALAMAN not in baris:
                continue
            try:
                langkah = json.loads(baris)
            except ValueError:
                continue
            if fmt == "claude":  # baris transkrip Claude: blok tool_use di message.content
                isi = (langkah.get("message") or {}).get("content")
                panggilan = [(b.get("name"), b.get("input") or {}) for b in (isi if isinstance(isi, list) else [])
                             if isinstance(b, dict) and b.get("type") == "tool_use"]
            else:
                panggilan = [(c.get("name"), c.get("args") or {}) for c in langkah.get("tool_calls") or []]
            if any(menyebut_halaman(fmt, n, a) for n, a in panggilan):
                return True
    return False


def teks_baru(fmt, hook):
    """Teks yang akan ditulis. Teks lama (Target, old_string) dan baris hapus di patch V4A tidak ikut."""
    if fmt == "claude":
        return g.new_text(hook.get("tool_input") or {})  # content, new_string, dan edits MultiEdit
    if fmt == "hermes":
        ti = hook.get("tool_input") or {}
        tambah = [l for l in str(ti.get("patch") or "").splitlines() if l.startswith("+")]
        return "\n".join(str(t) for t in [ti.get("content"), ti.get("new_string"), *tambah] if t)
    args = (hook.get("toolCall") or {}).get("args") or {}
    return "\n".join(t for k, v in args.items() if "Target" not in k and k not in ("Path", "AbsolutePath", "FilePath")
                     for t in g.leaves(v))


def alasan_tolak(fmt, hook, root, vault):
    for path in tujuan(fmt, hook):
        kena = wajib_referensi(path, root)
        if kena and kena[1] == "DESIGN.md" and WIKILINK.search(teks_baru(fmt, hook)):
            return (f"Ditolak penjaga desain: DESIGN.md di proyek {kena[0]} hanya boleh menyebut referensi publik, berupa nama "
                    "atau URL, karena repo bisa publik. Ganti tautan [[...]] ke halaman vault dengan nama atau URL referensinya, "
                    "lalu ulangi tulisan ini.")
        if kena and not sudah_baca(fmt, hook):
            proyek, jenis = kena
            apa = "ini tulisan ke DESIGN.md" if jenis == "DESIGN.md" else f"{os.path.basename(path)} adalah {jenis}"
            halaman = os.path.normpath(os.path.join(vault, "Wiki", "system", HALAMAN))
            return (f"Ditolak penjaga desain: {apa} di proyek {proyek}. Aturan desain di "
                    f"{os.path.normpath(os.path.join(root, 'AGENTS.md'))}: sebelum keputusan desain, buka dulu {halaman}, mulai dari referensi yang "
                    "ditetapkan untuk proyek ini, lalu catat referensi yang dipakai di bagian ## Referensi di DESIGN.md. "
                    "Sesudah membacanya, ulangi tulisan ini.")
    return None


def main():
    sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Hook sebelum alat menulis: tolak berkas tampilan baru dan DESIGN.md di proyek "
                                            "yang memakai vault, selama halaman Referensi Desain belum dibaca di sesi itu.")
    p.add_argument("--format", choices=("hermes", "antigravity", "claude"), required=True)
    p.add_argument("--projects-root", required=True, help="Folder induk proyek, mis. D:/CODE")
    p.add_argument("--vault", required=True, help="Folder vault memori, tempat Wiki/system/Referensi Desain.md")
    try:
        a = p.parse_args()
    except SystemExit:  # argumen salah tidak boleh menahan semua tulisan
        print('{"decision": "allow"}' if "antigravity" in sys.argv else "", end="")
        return 0
    alasan = None
    try:
        alasan = alasan_tolak(a.format, json.loads(sys.stdin.buffer.read().decode("utf-8")), a.projects_root, a.vault)
    except Exception as e:
        print(f"Penjaga desain gagal memeriksa ({type(e).__name__}: {e}), tulisan dibiarkan lewat.", file=sys.stderr)
    if a.format == "antigravity":
        print(json.dumps({"decision": "deny", "reason": alasan} if alasan else {"decision": "allow"}))
        return 0
    if alasan:
        print(alasan, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
