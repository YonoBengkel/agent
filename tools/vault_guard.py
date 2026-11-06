"""Hook sebelum tool menulis atau membuka folder terjaga (protokol D:\\CODE bagian Always, Aturan 9). Tiga tugas:
1. Tool tulis berkas, PreToolUse Claude Code (Write/Edit/MultiEdit) dan pre_tool_call Hermes (write_file/patch): tolak
   tulisan ke vault kalau teks barunya memuat nomor dokumen identitas, kata terlarang, atau secret. Daftar kata dan nilai
   secret dibaca dari file lokal lewat argumen, jadi tidak tertulis di sini.
2. Pagar shell Hermes (terminal/execute_code, sejak 2026-11-06): tolak perintah yang menulis, menghapus, atau pindah
   folder ke vault, apa pun isinya. Kode execute_code ditolak kalau menyebut path vault.
3. Folder --protect (vault pribadi, sejak 2026-11-06): tolak setiap tool yang masuk ke hook kalau membaca, menulis, atau
   mencakup folder itu, termasuk lewat folder induknya. Claude Code tidak memakai opsi ini, karena aturan deny-nya sudah menutup.
Input JSON hook di stdin; keluar 2 dengan alasan di stderr berarti diblokir, 0 berarti lanjut. Gagal memeriksa juga keluar 2
(fail closed). Batas: hanya pola yang dikenali. Skrip, path yang dirakit saat jalan, dan cd bertahap lintas panggilan tidak
terlihat, jadi vault_lint.py tetap cek terakhir untuk tulisan. Membaca vault memori tidak dihalangi."""
import os
import re
import sys
import json
import argparse
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from export_transcript import SECRET_ASSIGNMENT, known_secrets  # satu definisi secret untuk semua tool (Aturan 6)

NOMOR = re.compile(r"(?<!\d)\d{16}(?!\d)")       # NIK dan nomor KK: 16 digit (NRP boleh sejak 2026-10-21)
PLACEHOLDER = ("<", "[", "$", "{", "*", ".", "%")  # API_KEY=<kunci>, TOKEN: [DISENSOR], ${VAR} bukan secret
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "write_file", "patch")  # Claude Code, lalu Hermes
SHELL_TOOLS = ("terminal", "execute_code")  # Hermes
V4A_FILE = re.compile(r"(?m)^\*\*\* (?:Add File|Update File|Move to): *(.+?) *$")  # berkas di patch V4A Hermes
GIT_BASH = re.compile(r"^/([a-zA-Z])(?:/|$)")  # /d/... menjadi D:/...

# Satu potongan perintah shell: pemisah, redirect, atau kata (boleh berisi kutipan dan spasi yang di-escape)
SHELL_PIECE = re.compile(r"""&&|\|\||[;|\n()`]|\d*>>?\|?|(?:"[^"]*"|'[^']*'|\\.|&(?!&)|[^\s;|&><()`"'\\])+""")
SHELL_SEPARATORS = {"&&", "||", ";", "|", "\n", "(", ")", "`"}
SHELL_PREFIX = {"sudo", "env", "command", "builtin", "exec", "time", "nohup", "xargs", "busybox", "call", "do", "then",
                "else", "if", "while", "until", "!", "{", "}", "{}", "&"}
CD_VERBS = {"cd", "chdir", "pushd", "set-location", "sl"}
WRITE_VERBS = {"rm", "rmdir", "del", "erase", "rd", "unlink", "shred", "mv", "move", "ren", "rename", "cp", "copy", "xcopy",
               "robocopy", "rsync", "scp", "tee", "touch", "mkdir", "md", "ln", "truncate", "install", "curl", "wget", "tar",
               "unzip", "remove-item", "ri", "move-item", "mi", "rename-item", "rni", "copy-item", "cpi", "new-item", "ni",
               "set-content", "sc", "add-content", "ac", "clear-content", "clc", "out-file", "tee-object"}
INPLACE_VERBS = {"sed", "perl", "ruby", "awk", "gawk"}
INPLACE_FLAG = re.compile(r"^-[a-zA-Z]*i|^--in-place")
SHELL_WRAPPERS = {"bash", "sh", "zsh", "dash", "cmd", "powershell", "pwsh", "wsl"}
WRITE_WORD = re.compile(r"(?i)(?<![\w.-])(?:" + "|".join(sorted(WRITE_VERBS)) + r")(?![\w-])|(?<![\d&])>(?!&)")  # isi pembungkus shell
NULL_SINKS = {"/dev/null", "/dev/stdout", "/dev/stderr", "nul", "$null"}
UNRESOLVED = re.compile(r"[$%`]|\{\}")  # target yang baru diketahui saat jalan
PATH_END = r"(?=$|[\s;|&),\]}+])"  # akhir path sesudah kutipnya dilepas
WINDOWS_SWITCH = re.compile(r"/[a-zA-Z]")  # dir /b dan cmd /c, bukan /d milik Git Bash

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
    return [os.path.join(base, GIT_BASH.sub(r"\1:/", str(p).strip())) for p in paths if p and str(p).strip()]

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

def clean(word):
    return re.sub(r"""["']""", "", word).replace("\\ ", " ")

def mentions(text, folder):
    """Teks menyebut path folder, dalam bentuk D:/x, D:\\x, D:\\\\x, x\\ y, atau /d/x."""
    flat = re.sub(r"\\+", "/", clean(text)).lower()
    whole = os.path.abspath(folder).replace("\\", "/").lower()
    return whole in flat or f"/{whole[0]}{whole[2:]}" in flat

def touches(target, base, folders):
    """Folder terjaga yang kena target: target di dalamnya, atau target adalah induknya (menghapus induk ikut menghapus folder)."""
    path = GIT_BASH.sub(r"\1:/", target)
    wild = re.search(r"[*?\[]", path)
    if wild:
        path = os.path.dirname(path[:wild.start()]) or "."
    path = os.path.join(base, path)
    return [f for f in folders if inside(path, f) or inside(f, path)]

def shell_segments(command):
    """Pecah perintah menjadi (kata, target redirect) per bagian."""
    segments, words, outs, redirect = [], [], [], False
    for piece in SHELL_PIECE.findall(command):
        if piece in SHELL_SEPARATORS:
            segments.append((words, outs))
            words, outs = [], []
        elif re.fullmatch(r"\d*>>?\|?", piece):
            redirect = True
        elif redirect:
            outs.append(piece)
            redirect = False
        else:
            words.append(piece)
    segments.append((words, outs))
    return segments

def shell_touches(hook, folders):
    """Folder terjaga yang ditulis, dihapus, atau dituju cd oleh panggilan terminal/execute_code. cd dan workdir ikut ditolak
    karena terbawa ke panggilan berikutnya, sedangkan cwd di payload hook adalah folder proses, bukan folder sesi."""
    ti = hook.get("tool_input") or {}
    if hook.get("tool_name") == "execute_code":
        return [f for f in folders if mentions(str(ti.get("code") or ""), f)]
    base, command, found = str(hook.get("cwd") or os.getcwd()), str(ti.get("command") or ""), []
    if ti.get("workdir"):
        found += touches(str(ti["workdir"]), base, folders)
        base = os.path.join(base, GIT_BASH.sub(r"\1:/", str(ti["workdir"])))
    named = [f for f in folders if mentions(command, f)]
    for words, outs in shell_segments(command):
        while words and (words[0].lower() in SHELL_PREFIX or words[0].startswith("-") or words[0].isdigit()
                         or re.match(r"\w+=", words[0])):
            words = words[1:]
        verb = re.sub(r"\.(?:exe|cmd|bat)$", "", re.split(r"[\\/]", clean(words[0]))[-1].lower()) if words else ""
        args = [clean(w) for w in words[1:]]
        paths = [a for a in args if not a.startswith("-")]
        low = {a.lower() for a in args}
        moves = verb in CD_VERBS
        writes = (verb in WRITE_VERBS or (verb in INPLACE_VERBS and any(INPLACE_FLAG.match(a) for a in args))
                  or (verb == "find" and ("-delete" in low or low & WRITE_VERBS)))
        hit = [t for t in map(clean, outs) if not t.startswith("&") and t.lower() not in NULL_SINKS]
        hit += paths if writes or moves else []
        if ((writes and not paths) or any(UNRESOLVED.search(t) for t in hit)
                or (verb in SHELL_WRAPPERS and WRITE_WORD.search(" ".join(args)))):
            found += named + touches(".", base, folders)  # targetnya tidak terbaca, jadi cukup folder itu disebut
        for t in hit:
            found += touches(t, base, folders)
        if moves and paths:
            base = os.path.join(base, GIT_BASH.sub(r"\1:/", paths[0]))
    return list(dict.fromkeys(found))

def leaves(value):
    """Semua teks di dalam argumen tool, seberapa pun dalamnya."""
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return [s for v in value for s in leaves(v)]
    return [value] if isinstance(value, str) else []

def opens(text, folder):
    """Teks menyebut folder atau isinya (D:/x, D:\\x, x%20y, /d/x, /mnt/d/x), atau menyebut induknya sebagai path utuh,
    karena membaca induk ikut membaca folder itu. D:/x/y yang y-nya bukan folder itu tidak kena. Kutip dilepas dua cara:
    "D:/"x menyatu, sedangkan r"D:/x" dan "D:/x"/y dipisah spasi supaya awalan dan akhir path tetap terbaca."""
    raw = unquote(re.sub(r"\\+", "/", text.replace("\\ ", " "))).lower()
    variants = (re.sub(r"""["']""", "", raw), re.sub(r"""["']""", " ", raw))
    path = os.path.abspath(folder).replace("\\", "/").lower().rstrip("/")
    def forms(p):  # akar drive tidak punya bentuk /d, karena bentrok dengan switch Windows
        return [r"(?<![\w.-])" + re.escape(p)] + ([re.escape(f"/{p[0]}{p[2:]}")] if p[2:] else [])
    def found(pattern):
        return any(re.search(pattern, flat) for flat in variants)
    if any(found(f + r"(?=/)|" + f + PATH_END) for f in forms(path)):
        return True
    while len(path) > 2:
        path = os.path.dirname(path).rstrip("/")
        if any(found(f + r"(?:/?" + PATH_END + r"|/[*?\[])") for f in forms(path)):
            return True
    return False

def opened(hook, folders):
    """Folder --protect yang dibaca, ditulis, atau dicakup panggilan ini. Isi tulisan tidak ikut dinilai, jadi catatan yang
    sekadar menyebut path folder itu tetap boleh ditulis ke tempat lain."""
    if not folders:
        return []
    ti = hook.get("tool_input") or {}
    tool, base = hook.get("tool_name"), str(hook.get("cwd") or os.getcwd())
    texts = [] if tool in WRITE_TOOLS else leaves(ti)
    found = [f for f in folders if any(opens(t, f) for t in texts)]
    if tool == "terminal":
        pieces = [w for words, outs in shell_segments(str(ti.get("command") or "")) for w in words + outs]
        paths = [clean(w) for w in pieces if not w.startswith("-") and not WINDOWS_SWITCH.fullmatch(w)]
    elif tool == "execute_code":
        paths = []
    else:
        paths = targets(hook) or (["."] if tool == "search_files" else [])
    for p in paths:
        found += touches(p, base, folders)
    return list(dict.fromkeys(found))

def main():
    sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Hook sebelum tool jalan: tolak tulisan ke vault yang memuat data pribadi atau secret, tulisan lewat shell Hermes, dan semua akses ke folder --protect.")
    p.add_argument("--vault", required=True, help="Folder vault yang dijaga")
    p.add_argument("--words", help="File daftar kata terlarang (lokal, tidak di-commit)")
    p.add_argument("--secrets-from", action="append", default=[], help="File konfigurasi yang nilai secret-nya ikut dicari (boleh diulang)")
    p.add_argument("--protect", action="append", default=[], help="Folder yang tidak boleh dibaca atau ditulis sama sekali, misalnya vault pribadi (boleh diulang)")
    a = p.parse_args()  # argumen salah: argparse keluar dengan kode 2, jadi tetap diblokir
    try:
        hook = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        ti = hook.get("tool_input") or {}
        tool = hook.get("tool_name")
        closed = opened(hook, a.protect)
        if closed:
            print(f"Ditolak penjaga vault: panggilan {tool} ini membuka atau mencakup {closed[0]}, vault pribadi yang tidak boleh "
                  "dibaca atau ditulis agent. Kalau mencari di folder induknya, sebut subfolder yang dituju. Jangan mencari jalan lain. "
                  "Kalau isinya memang dibutuhkan, minta ke pengguna.", file=sys.stderr)
            return 2
        if tool in SHELL_TOOLS:
            found = shell_touches(hook, [a.vault, *a.protect])
            if found:
                print(f"Ditolak pagar terminal: panggilan ini menulis, menghapus, atau pindah folder ke {found[0]}. Tulis ke vault "
                      "memori lewat write_file atau patch supaya isinya diperiksa. Vault pribadi tidak boleh ditulis. Menghapus atau "
                      "memindahkan berkas vault: minta pengguna dulu. Membaca tetap boleh dengan path absolut, tanpa cd, workdir, "
                      "atau execute_code.", file=sys.stderr)
                return 2
            return 0
        if tool not in WRITE_TOOLS:
            return 0
        hit = [t for t in targets(hook) if inside(t, a.vault)]
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
