"""Hook sebelum tool menulis atau membuka folder terjaga (protokol D:\\CODE bagian Always, Aturan 9). Empat tugas:
1. Tool tulis berkas, PreToolUse Claude Code (Write/Edit/MultiEdit), pre_tool_call Hermes (write_file/patch), dan PreToolUse
   Antigravity (write_to_file dan kawannya, sejak 2026-11-13): tolak tulisan ke vault kalau teks barunya memuat nomor dokumen
   identitas, kata terlarang, atau secret. Daftar kata dan nilai secret dibaca dari file lokal lewat argumen, jadi tidak
   tertulis di sini. Pola muatan injeksi hanya dicatat ke log penjaga, tidak ditolak.
2. Pagar shell Hermes (terminal/execute_code, sejak 2026-11-06): tolak perintah yang menulis, menghapus, atau pindah folder
   ke vault, apa pun isinya, termasuk perintah git yang mengubah isi folder kerjanya. Kode execute_code ditolak kalau menyebut
   path vault. Claude (Bash/PowerShell) dan run_command Antigravity tidak memakai pagar ini (keputusan pengguna 2026-11-14): di
   shell mereka yang dijaga hanya vault pribadi (tugas 3).
3. Folder --protect (vault pribadi, sejak 2026-11-06): tolak setiap tool yang masuk ke hook kalau membaca, menulis, atau
   mencakup folder itu, termasuk lewat folder induknya. Di Claude hanya untuk shell, karena aturan deny Read dan Edit tidak
   menjangkau perintah shell.
4. Opsi --worker untuk pekerja oper_kerja.py (sejak 2026-11-07): hanya alat berkas, dan baca maupun tulis dikunci ke folder
   sesinya. Berkas pagar-aktif di folder tugas membuktikan ke oper_kerja.py bahwa hook ini benar-benar berjalan.
Input JSON hook di stdin. Claude dan Hermes: keluar 2 dengan alasan di stderr berarti diblokir, 0 berarti lanjut.
Antigravity: selalu keluar 0 dengan JSON decision. Gagal memeriksa berarti ditolak (fail closed), kecuali perintah shell Claude
dan Antigravity, yang dibiarkan lewat dan dicatat sebagai galat di log penjaga, supaya pengurai yang gagal tidak mengunci shell.
Batas: hanya pola yang dikenali. Path yang dirakit saat jalan dan cd bertahap lintas panggilan tidak terlihat, jadi
vault_lint.py tetap cek terakhir untuk tulisan. Membaca vault memori tidak dihalangi."""
import os
import re
import sys
import json
import time
import hashlib
import fnmatch
import pathlib
import sqlite3
import argparse
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from export_transcript import SECRET_ASSIGNMENT, known_secrets  # satu definisi secret untuk semua tool (Aturan 6)

NOMOR = re.compile(r"(?<!\d)\d{16}(?!\d)")       # NIK dan nomor KK: 16 digit (NRP boleh sejak 2026-10-21)
PLACEHOLDER = ("<", "[", "$", "{", "*", ".", "%")  # API_KEY=<kunci>, TOKEN: [DISENSOR], ${VAR} bukan secret
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "write_file", "patch")  # Claude Code, lalu Hermes
SHELL_TOOLS = ("terminal", "execute_code")  # Hermes
SHELL_LAIN = ("Bash", "PowerShell", "run_command")  # Claude dan Antigravity: di shell hanya vault pribadi yang dijaga (2026-11-14)
GIT_TREE = {"checkout", "reset", "restore", "clean", "rm", "mv", "stash", "merge", "pull", "rebase", "apply", "am",
            "cherry-pick", "revert", "switch"}   # subperintah git yang mengubah isi folder kerja
# Antigravity (riset 2026-11-13, M6): nama alat IDE dan CLI, dan argumen path-nya (dokumentasi hooks Antigravity, uji agy)
AGY_TULIS = ("write_file", "edit_file", "write_to_file", "replace_file_content", "multi_replace_file_content")
AGY_PATH = ("Path", "TargetFile", "AbsolutePath", "FilePath", "DirectoryPath", "SearchDirectory", "SearchPath")
# Pemanggilan tulis berkas di kode yang dijalankan langsung (python -c, heredoc, node -e), dipakai penjaga_repo untuk bidang
# penegakan. String .replace( sengaja tidak termasuk
WRITE_API = re.compile(r"""open\([^)\n]*,\s*(?:mode\s*=\s*)?['"][^'"\n]*[wax+]|\.write_(?:text|bytes)\(|(?<!stdout)(?<!stderr)\.write\("""
                       r"""|shutil\.(?:move|copy\w*|rmtree)\(|os\.(?:remove|unlink|rename|replace|rmdir|removedirs|makedirs|mkdir)\("""
                       r"""|\.(?:unlink|rmdir|touch|mkdir|rename)\(|fs\.(?:write|append|unlink|rm|rename|copy|mkdir)\w*\("""
                       r"""|(?i:set-content|add-content|out-file|new-item|remove-item|move-item|copy-item|rename-item|clear-content)"""
                       r"""|(?i:writeall\w*|appendall\w*)\(""")
V4A_FILE = re.compile(r"(?m)^\*\*\*[ \t]*(?:Add[ \t]+File|Update[ \t]+File|Delete[ \t]+File|Move[ \t]+File|Move[ \t]+to):[ \t]*(.+?)[ \t\r]*$")  # sama longgarnya dengan pengurai patch Hermes
DRIVE_RELATIVE = re.compile(r"^[a-zA-Z]:(?![\\/])")  # C:a.md: relatif ke folder aktif drive itu, bukan ke folder sesi
WORKER_TOOLS = ("read_file", "write_file", "patch", "search_files")  # toolset file Hermes
WORKER_CLOSED = ("*.env", "*.env.*", "*.kredensial*", "*.pem", "*id_rsa*")  # berkas kredensial, juga untuk pekerja OpenCode
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
TAK_TERLIHAT = re.compile("[​-‏⁠-⁤﻿‪-‮⁦-⁩"
                          "\U000e0000-\U000e007f\U000e0100-\U000e01ef︀-️]")  # zero-width, bidi, blok tag, selektor variasi
EMOJI = re.compile("[☀-➿\U0001f000-\U0001faff️]")

def invisible(text):
    """Unicode tak terlihat yang bisa menyembunyikan instruksi untuk agent, sebagai ringkasan 'U+200B ×2', atau ''.
    Riset 2026-11-13 (langkah C1). Yang dibiarkan karena wajar di catatan: BOM di awal teks (dicek terpisah), satu
    selektor variasi sesudah karakter biasa (tanda peringatan di penanda SUPERSEDED), dan ZWJ di dalam emoji gabungan."""
    found = {}
    for m in TAK_TERLIHAT.finditer(text):
        c, i = m.group(), m.start()
        before, after = text[i - 1:i], text[i + 1:i + 2]
        if c == "﻿" and i == 0:
            continue
        if "︀" <= c <= "️" and before and not before.isspace() and not TAK_TERLIHAT.match(before):
            continue
        if c == "‍" and EMOJI.match(before) and EMOJI.match(after):
            continue
        key = f"U+{ord(c):04X}"
        found[key] = found.get(key, 0) + 1
    return ", ".join(f"{k} ×{n}" for k, n in found.items())

# Muatan injeksi di teks yang akan menjadi memori tepercaya (riset 2026-11-13, M5). Sempit dan hanya dilaporkan: halaman
# yang membahas injeksi wajar memuatnya. "system prompt" dan placeholder <user> sengaja tidak termasuk, karena dipakai wajar.
INJEKSI = (
    ("instruksi yang ditujukan ke agent", re.compile(
        r"(?i)\b(?:ignore|disregard|forget)\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier|preceding)\s+"
        r"(?:instructions?|prompts?|rules?|messages?)|\babaikan\s+(?:semua\s+|seluruh\s+)?(?:instruksi|perintah|aturan|pesan)\s+"
        r"(?:sebelumnya|di\s+atas|sebelum\s+ini)|\byou\s+are\s+now\s+(?:a|an|in)\b|\b(?:kamu|anda)\s+sekarang\s+adalah\b|"
        r"\b(?:new|updated)\s+instructions?\s*:|\binstruksi\s+baru\s*:|\bdo\s+not\s+(?:tell|inform)\s+the\s+user\b|"
        r"\bjangan\s+(?:beri\s+tahu|bilang|kasih\s+tahu)\s+(?:pengguna|user)\b")),
    ("tag peran atau percakapan palsu", re.compile(
        r"(?im)<\|im_(?:start|end)\|>|\[/?INST\]|<</?SYS>>|</?(?:system|assistant|human|system-reminder|function_results|"
        r"tool_result)>|^\s*(?:Human|Assistant|System)\s*:\s")),
    ("sintaks pemanggilan tool", re.compile(
        r"(?i)</?function_calls>|<invoke\s+name=|</?tool_call>|\"tool_calls\"\s*:|antml:|\"function\"\s*:\s*\{\s*\"name\"")),
)
URL_PARAM = re.compile(r"https?://[^\s)>`\"'\]]+\?([^\s)>`\"'\]#]+)")
PARAM_WAJAR = re.compile(r"(?i)^(?:v|t|list|index|si|usp|page|lang|hl|tab|ref|feature|pp|utm_\w+)$")  # YouTube, Drive, utm

def injeksi(text):
    """Pola muatan injeksi sebagai [(kategori, nomor baris pertama)]: instruksi yang ditujukan ke agent, tag peran palsu,
    sintaks pemanggilan tool, dan URL dengan parameter di luar yang lazim (jalur kirim data keluar). Peracunan memori lewat
    Ingest dan Compile (MINJA, Unit 42), jadi dilaporkan, bukan ditolak."""
    found = []
    for kategori, pola in INJEKSI:
        m = pola.search(text)
        if m:
            found.append((kategori, text.count("\n", 0, m.start()) + 1))
    for m in URL_PARAM.finditer(text):
        nama = [kv.split("=", 1)[0] for kv in re.split(r"[&;]", m.group(1)) if "=" in kv]
        if any(not PARAM_WAJAR.match(n) for n in nama):
            found.append(("URL berparameter", text.count("\n", 0, m.start()) + 1))
            break
    return found

def folder_log():
    """Folder log keputusan penjaga: PENJAGA_LOG, atau Riwayat Perckapan/penjaga/ di workspace (lokal, tidak masuk git)."""
    sini = os.path.dirname(os.path.abspath(__file__))
    return os.environ.get("PENJAGA_LOG") or os.path.join(os.path.dirname(sini), "Riwayat Perckapan", "penjaga")

def catat_keputusan(penjaga, agen, keputusan, aturan, alat="", target="", galat=""):
    """Satu baris JSONL per penolakan, laporan, atau galat penjaga, untuk jejak audit dan tanda percobaan memutar (riset
    2026-11-13, langkah C10). Berkasnya per bulan di folder_log(). Isi yang ditolak tidak pernah dicatat, hanya kategori
    aturan dan path-nya. Gagal mencatat tidak mengubah keputusan penjaga."""
    try:
        sini = os.path.dirname(os.path.abspath(__file__))
        folder = folder_log()
        with open(os.path.join(sini, penjaga + ".py"), "rb") as f:
            skrip = hashlib.sha256(f.read()).hexdigest()[:12]
        baris = {"waktu": time.strftime("%Y-%m-%dT%H:%M:%S"), "penjaga": penjaga, "agen": agen, "keputusan": keputusan,
                 "aturan": aturan, "alat": alat or "", "target": target or "", "galat": galat, "skrip": skrip}
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, time.strftime("%Y-%m") + ".jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(baris, ensure_ascii=False) + "\n")
    except Exception:
        pass

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

def raw_targets(hook):
    """Path tujuan apa adanya: file_path (Claude), path (Hermes), dan berkas di patch V4A Hermes.
    Path gaya Git Bash (/d/...) diubah ke D:/... supaya tetap dikenali."""
    ti = hook.get("tool_input") or {}
    patched = [x for f in V4A_FILE.findall(str(ti.get("patch") or "")) for x in re.split(r"\s*->\s*", f)]  # Move File: a -> b
    paths = [ti.get("file_path"), ti.get("path"), *patched]
    return [GIT_BASH.sub(r"\1:/", str(p).strip()) for p in paths if p and str(p).strip()]

def targets(hook):
    """Path tujuan penuh, yang relatif dinilai dari cwd hook."""
    base = str(hook.get("cwd") or os.getcwd())
    return [os.path.join(base, os.path.expanduser(p)) for p in raw_targets(hook)]

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
        if verb == "git":   # perintah git yang mengubah isi folder kerja repo (-C <folder> atau folder dasar)
            gargs, gbase = list(args), base
            while gargs and gargs[0].startswith("-"):
                gbase = os.path.join(base, GIT_BASH.sub(r"\1:/", gargs[1])) if gargs[0] == "-C" and len(gargs) > 1 else gbase
                gargs = gargs[2:] if gargs[0] in ("-C", "-c") and len(gargs) > 1 else gargs[1:]
            if gargs and gargs[0] in GIT_TREE:
                found += touches(gbase, base, folders)
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
    if tool in ("terminal", *SHELL_LAIN):
        pieces = [w for words, outs in shell_segments(str(ti.get("command") or "")) for w in words + outs]
        paths = [clean(w) for w in pieces if not w.startswith("-") and not WINDOWS_SWITCH.fullmatch(w)]
    elif tool == "execute_code":
        paths = []
    else:
        paths = targets(hook) or (["."] if tool == "search_files" else [])
    for p in paths:
        found += touches(p, base, folders)
    return list(dict.fromkeys(found))

def session_cwd(hook):
    """Folder sesi Hermes dari state.db. Semua sesi jalan di satu gateway, jadi cwd di payload hanyalah folder gateway."""
    home, session = os.environ.get("HERMES_HOME"), hook.get("session_id")
    if hook.get("hook_event_name") != "pre_tool_call" or not home or not session:
        return None
    try:
        db = sqlite3.connect(pathlib.Path(home, "state.db").as_uri() + "?mode=ro", uri=True, timeout=5)
        try:
            row = db.execute("SELECT cwd FROM sessions WHERE id = ?", (session,)).fetchone()
        finally:
            db.close()
    except (sqlite3.Error, ValueError):
        return None
    return row[0] if row and row[0] else None

def worker_refusal(hook, folder):
    """Alasan menolak panggilan pekerja oper_kerja.py, atau None. Path dibandingkan sesudah symlink diikuti."""
    tool = hook.get("tool_name")
    if tool not in WORKER_TOOLS:
        return f"alat {tool} tidak tersedia untuk pekerja"
    if not folder:
        return "folder sesi pekerja tidak diketahui"
    if any(DRIVE_RELATIVE.match(p) for p in raw_targets(hook)):
        return "path tanpa folder setelah nama drive tidak diterima"
    paths = targets({**hook, "cwd": folder})
    for p in paths:
        if not inside(os.path.realpath(p), os.path.realpath(folder)):
            return f"{p} ada di luar folder kerja tugas ini"
        if any(fnmatch.fnmatch(os.path.basename(p).lower(), c) for c in WORKER_CLOSED):
            return f"{os.path.basename(p)} berkas kredensial, jadi tidak dibuka pekerja"
    # path yang tidak ada dipecah Hermes menjadi beberapa path ("a.py, D:/lain"), lalu yang ada ikut dicari
    if tool == "search_files" and not all(os.path.exists(p) for p in paths):
        return "path pencarian harus satu folder atau berkas yang ada di folder kerja"
    return None

def dari_antigravity(hook):
    """Payload PreToolUse Antigravity ({toolCall: {name, args}, workspacePaths}) dalam bentuk internal penjaga (riset M6):
    alat tulis menjadi Write dengan isi tulisannya saja (bukan teks lama TargetContent di potongan pengganti), run_command
    tetap run_command dengan folder Cwd-nya, dan alat lain dinilai sebagai alat baca beserta semua argumennya."""
    call = hook.get("toolCall") or {}
    name, args = call.get("name"), call.get("args") or {}
    base = str(args.get("Cwd") or next(iter(hook.get("workspacePaths") or []), None) or os.getcwd())
    path = next((str(args[k]).strip().strip('"') for k in AGY_PATH if args.get(k)), None)
    if name in AGY_TULIS:
        potong = [c.get("ReplacementContent") for c in args.get("ReplacementChunks") or [] if isinstance(c, dict)]
        isi = [args.get(k) for k in ("CodeContent", "Content", "content", "ReplacementContent")] + potong
        return {"tool_name": "Write", "cwd": base, "tool_input": {"file_path": path, "content": "\n".join(str(x) for x in isi if x)}}
    if name == "run_command":
        return {"tool_name": "run_command", "cwd": base, "tool_input": {"command": str(args.get("CommandLine") or "")}}
    return {"tool_name": name or "?", "cwd": base, "tool_input": dict(args, path=path) if path else dict(args)}

def inline_write(command, folder):
    """Kode yang dijalankan langsung (python -c, heredoc, node -e, skrip PowerShell) yang menyebut folder ini dan memuat
    pemanggilan tulis berkas. Path yang dirakit saat jalan tidak terbaca, jadi cukup keduanya ada di teks perintah."""
    return mentions(command, folder) and WRITE_API.search(command) is not None

def keluar(fmt, keputusan, alasan=""):
    """Kode keluar dan keluaran satu keputusan dalam bentuk yang dibaca platformnya. Claude dan Hermes: tolak berarti keluar 2
    dengan alasan di stderr. Antigravity: selalu keluar 0 dengan JSON decision di stdout (ASCII, aman untuk konsol mana pun)."""
    if fmt == "antigravity":
        print(json.dumps({"decision": keputusan, **({"reason": alasan} if alasan else {})}))
        return 0
    if keputusan == "deny":
        print(alasan, file=sys.stderr)
        return 2
    return 0

def main():
    sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Hook sebelum tool jalan: tolak tulisan ke vault yang memuat data pribadi atau secret, "
                                            "tolak tulisan ke vault lewat shell Hermes, dan tolak semua akses ke folder --protect.")
    p.add_argument("--vault", required=True, help="Folder vault yang dijaga")
    p.add_argument("--words", help="File daftar kata terlarang (lokal, tidak di-commit)")
    p.add_argument("--secrets-from", action="append", default=[], help="File konfigurasi yang nilai secret-nya ikut dicari (boleh diulang)")
    p.add_argument("--protect", action="append", default=[], help="Folder yang tidak boleh dibaca atau ditulis sama sekali, misalnya vault pribadi (boleh diulang)")
    p.add_argument("--worker", action="store_true", help="Pekerja oper_kerja.py: hanya alat berkas, dan hanya di folder sesinya")
    p.add_argument("--format", choices=("claude", "hermes", "antigravity"),
                   help="Bentuk payload dan keputusan. Bawaannya dikenali dari payload: toolCall berarti Antigravity, pre_tool_call berarti Hermes")
    a = p.parse_args()  # argumen salah: argparse keluar dengan kode 2, jadi tetap diblokir
    fmt, tool = a.format or "claude", None
    try:
        hook = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
        fmt = a.format or ("antigravity" if "toolCall" in hook else "hermes" if hook.get("hook_event_name") == "pre_tool_call" else "claude")
        if fmt == "antigravity":
            hook = dari_antigravity(hook)
        ti = hook.get("tool_input") or {}
        tool = hook.get("tool_name")
        catat = lambda keputusan, aturan, target="": catat_keputusan("vault_guard", fmt, keputusan, aturan, tool, target)
        folder = session_cwd(hook)
        if folder:
            hook["cwd"] = folder  # path relatif Hermes berarti relatif ke folder sesi
        if a.worker:
            if folder and pathlib.Path(folder).parent.joinpath("tugas.md").exists():
                pathlib.Path(folder).parent.joinpath("pagar-aktif").touch()
            refused = worker_refusal(hook, folder)
            if refused:
                catat("deny", "pekerja di luar folder kerja")
                return keluar(fmt, "deny", f"Ditolak penjaga vault: {refused}. Kerjakan di dalam folder kerja saja.")
        closed = opened(hook, a.protect)
        if closed:
            catat("deny", "vault pribadi", closed[0])
            return keluar(fmt, "deny", f"Ditolak penjaga vault: panggilan {tool} ini membuka atau mencakup {closed[0]}, vault pribadi "
                          "yang tidak boleh dibaca atau ditulis agent. Kalau mencari di folder induknya, sebut subfolder yang dituju. "
                          "Jangan mencari jalan lain. Kalau isinya memang dibutuhkan, minta ke pengguna.")
        if tool in SHELL_TOOLS:
            found = shell_touches(hook, [a.vault, *a.protect])
            if found:
                catat("deny", "pagar terminal", found[0])
                return keluar(fmt, "deny", f"Ditolak pagar terminal: panggilan ini menulis, menghapus, atau pindah folder ke {found[0]}. "
                              "Tulis ke vault memori lewat write_file atau patch supaya isinya diperiksa. Vault pribadi tidak boleh "
                              "ditulis. Menghapus atau memindahkan berkas vault: minta pengguna dulu. Membaca tetap boleh dengan path "
                              "absolut, tanpa cd, workdir, atau execute_code.")
            return keluar(fmt, "allow")
        if tool in SHELL_LAIN:   # Claude dan Antigravity: vault pribadi sudah dicek di atas, tulisan ke vault tidak ditanyakan
            return keluar(fmt, "allow")
        if tool not in WRITE_TOOLS:
            return keluar(fmt, "allow")
        hit = [t for t in targets(hook) if inside(t, a.vault)]
        if not hit:
            return keluar(fmt, "allow")
        found = reasons(new_text(ti), banned_words(a.words), known_secrets(a.secrets_from))
        if found:
            catat("deny", ", ".join(found), hit[0])   # kategori saja, bukan teks yang ditolak
            return keluar(fmt, "deny", f"Ditolak penjaga vault: tulisan ke {hit[0]} memuat {', '.join(found)}. "
                          "Ganti bagian itu dengan penanda seperti <nik> atau <nama> (protokol D:\\CODE, bagian Always).")
        pola = injeksi(new_text(ti))   # dilaporkan ke log, tidak ditolak (riset 2026-11-13, M5)
        if pola:
            catat("lapor", "pola injeksi: " + ", ".join(sorted({k for k, _ in pola})), hit[0])
        return keluar(fmt, "allow")
    except Exception as e:  # gagal berarti tolak (fail closed), bukan diam-diam lolos
        if tool in SHELL_LAIN:   # pengurai shell yang gagal tidak boleh mengunci semua perintah Claude dan Antigravity
            catat_keputusan("vault_guard", fmt, "galat", "gagal memeriksa shell, dibiarkan lewat", tool, galat=type(e).__name__)
            return keluar(fmt, "allow")
        catat_keputusan("vault_guard", fmt, "galat", "gagal memeriksa, ditolak", tool, galat=type(e).__name__)
        return keluar(fmt, "deny", f"Penjaga vault gagal memeriksa ({type(e).__name__}: {e}); tulisan ditolak supaya aman.")

if __name__ == "__main__":
    sys.exit(main())
