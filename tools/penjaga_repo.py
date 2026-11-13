"""Penjaga repo luar: hook sebelum perintah shell dan tulisan berkas, untuk jalur kepercayaan di protokol D:\\CODE.

Yang ditolak (sejak 2026-11-12):
- `git clone` dan `gh repo clone` repo pihak ketiga dengan tujuan di dalam --projects-root.
- Menyalin atau memindah isi --repo-luar ke dalam --projects-root (cp, mv, robocopy, Copy-Item, dan sejenisnya).
Repo milik sendiri boleh: URL yang pemiliknya --own-owner, atau path lokal di dalam --projects-root. Pesan tolaknya menunjuk
tempat yang benar, jadi agent bisa mengulang dengan tujuan di --repo-luar.

Yang ditanyakan ke pengguna, hanya di Hermes lewat gerbang persetujuan manusianya (sejak 2026-11-13, riset M1: insiden
2025-2026 masuk lewat konfigurasi yang kemudian dijalankan komponen lain; dibatasi ke Hermes atas keputusan pengguna 2026-11-14).
Di Claude dan Antigravity penjaga ini hanya menolak clone dan salinan repo luar:
- Tulisan agent, lewat alat tulis atau shell, ke konfigurasi yang berjalan otomatis di proyek: .vscode/tasks.json,
  .vscode/settings.json, *.code-workspace, .agents/hooks.json, .claude/settings*.json, .mcp.json, .zed/settings.json,
  .git/config, dan .git/hooks.
- Tulisan ke bidang penegakan: skrip penjaga dan hook di folder alat ini, konfigurasi hook Claude, Antigravity, dan Hermes,
  dan daftar kata terlarang.
- Pemasangan paket pihak ketiga (npm install <paket>, pip install <paket>, npx, uvx, dan sejenisnya; instal dari lockfile
  atau path lokal tidak), unduhan berkas ke --projects-root, dan unduhan yang langsung dijalankan shell.

Tiga format hook, sama dengan penjaga_desain.py:
- claude: PreToolUse Claude Code untuk Bash dan PowerShell. Tolak = keluar 2 dengan alasan di stderr.
- hermes: pre_tool_call Hermes. Tolak = keluar 2, tanya = JSON action approve (gerbang persetujuan manusia Hermes, yang
  menolak kalau tidak ada manusia). Folder sesi dibaca dari state.db.
- antigravity: PreToolUse Antigravity. Keputusan berupa JSON decision di stdout, selalu keluar 0.
Latar: uji sesi nyata 2026-11-12, Hermes meng-clone repo kiriman ke D:\\CODE dan menjalankan skrip pasangnya walau aturannya
sudah ada. Ini pengingat, bukan pagar keamanan penuh: perintah yang tidak dikenali, skrip yang menulis sendiri, dan galat
pemeriksaan lolos (fail open)."""
import os
import re
import sys
import json
import argparse
from urllib.parse import unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vault_guard as g  # pemecah perintah shell, path gaya Git Bash, folder sesi Hermes, dan cek di dalam folder (Aturan 6)

SHELL = {"claude": ("Bash", "PowerShell"), "hermes": ("terminal",), "antigravity": ("run_command",)}
TULIS = {"claude": ("Write", "Edit", "MultiEdit"), "hermes": ("write_file", "patch"), "antigravity": g.AGY_TULIS}
# Konfigurasi proyek yang dijalankan komponen lain tanpa ditanya: (folder induk, nama berkas), dicocokkan tanpa beda huruf
OTOMATIS = {(".vscode", "tasks.json"), (".vscode", "settings.json"), (".agents", "hooks.json"), (".claude", "settings.json"),
            (".claude", "settings.local.json"), (".zed", "settings.json"), (".git", "config")}
SKRIP_HOOK = ("vault_guard.py", "penjaga_repo.py", "penjaga_desain.py", "session_context.py", "export_transcript.py",
              "cek_proses_sisa.py")
# Pengelola paket: subperintah yang menambah paket pihak ketiga. Tanpa nama paket (dari lockfile) tidak ditanyakan
PAKET = {"npm": {"install", "i", "add", "isntall", "in"}, "pnpm": {"add", "install", "i"}, "yarn": {"add"},
         "bun": {"add", "install", "i"}, "pip": {"install"}, "pip3": {"install"}, "uv": {"add"}, "poetry": {"add"},
         "cargo": {"add", "install"}, "go": {"install", "get"}, "gem": {"install"}, "composer": {"require"},
         "conda": {"install"}, "pipx": {"install"}, "dotnet": {"add"}}
JALANKAN_UNDUH = {"npx", "bunx", "pnpx", "uvx"}   # unduh paket lalu langsung jalankan
SALIN_TUJUAN = {"cp", "copy", "xcopy", "copy-item", "cpi", "rsync", "scp", "install"}   # yang ditulis hanya argumen terakhir
NILAI_OPSI = {"-r", "--requirement", "-c", "--constraint", "-e", "--editable", "-i", "--index-url", "--extra-index-url",
              "-t", "--target", "--prefix", "--root", "-f", "--find-links", "--registry", "--cache", "-w", "--workspace",
              "--filter", "-C", "--dir", "--cwd"}
UNDUH = {"curl", "wget", "iwr", "invoke-webrequest", "irm", "invoke-restmethod", "start-bitstransfer"}
KELUARAN_UNDUH = {"-o", "--output", "-outfile", "-destination", "--output-document"}
PENERIMA_SKRIP = {"bash", "sh", "zsh", "python", "python3", "py", "node", "iex", "invoke-expression", "powershell", "pwsh", "cmd"}
SALIN = {"cp", "copy", "xcopy", "robocopy", "rsync", "mv", "move", "copy-item", "cpi", "move-item", "mi"}
BUNGKUS = {"bash", "sh", "zsh", "cmd", "powershell", "pwsh"}
# Opsi git clone yang mengambil nilai di kata berikutnya, supaya nilainya tidak dikira sumber atau tujuan
CLONE_NILAI = {"-b", "--branch", "-o", "--origin", "-u", "--upload-pack", "--template", "-c", "--config", "--depth",
               "--reference", "--reference-if-able", "--separate-git-dir", "-j", "--jobs", "--filter", "--shallow-since",
               "--shallow-exclude", "--server-option"}
SCP_LIKE = re.compile(r"^[\w.-]+@[\w.-]+:(.+)$")  # git@github.com:pemilik/repo.git


def perintah(fmt, hook):
    """(teks perintah, folder dasar) untuk panggilan shell, atau (None, None)."""
    if fmt == "antigravity":
        call = hook.get("toolCall") or {}
        if call.get("name") not in SHELL[fmt]:
            return None, None
        args = call.get("args") or {}
        base = args.get("Cwd") or next(iter(hook.get("workspacePaths") or []), None) or os.getcwd()
        return str(args.get("CommandLine") or ""), str(base)
    if hook.get("tool_name") not in SHELL[fmt]:
        return None, None
    ti = hook.get("tool_input") or {}
    base = (g.session_cwd(hook) if fmt == "hermes" else None) or hook.get("cwd") or os.getcwd()
    if ti.get("workdir"):
        base = os.path.join(str(base), g.GIT_BASH.sub(r"\1:/", str(ti["workdir"])))
    return str(ti.get("command") or ""), str(base)


def tujuan_tulis(fmt, hook):
    """Path penuh yang ditulis alat tulis berkas, atau None kalau panggilan ini bukan alat tulis."""
    if fmt == "antigravity":
        if (hook.get("toolCall") or {}).get("name") not in TULIS[fmt]:
            return None
        return g.targets(g.dari_antigravity(hook))
    if hook.get("tool_name") not in TULIS[fmt]:
        return None
    folder = g.session_cwd(hook) if fmt == "hermes" else None
    return g.targets({**hook, "cwd": folder} if folder else hook)


def bidang_penegakan():
    """Berkas dan folder yang menegakkan aturan: skrip hook di folder ini, konfigurasi hook tiga agent, dan daftar kata
    terlarang. Menyunting semua ini lewat agent ditanyakan dulu, karena penjaga yang ditukar diam-diam tampak sama dengan
    penjaga yang bekerja (riset M1, bidang penegakan)."""
    sini, home = os.path.dirname(os.path.abspath(__file__)), os.path.expanduser("~")
    daftar = [os.path.join(sini, n) for n in SKRIP_HOOK]
    daftar += [os.path.join(home, ".claude", "settings.json"), os.path.join(home, ".claude", "settings.local.json"),
               os.path.join(home, ".gemini", "config", "hooks.json"), os.path.join(home, ".gemini", "config", "hooks"),
               os.path.join(os.path.dirname(sini), "Konfigurasi", "penjaga_vault_terlarang.txt")]
    if os.environ.get("HERMES_HOME"):
        daftar.append(os.path.join(os.environ["HERMES_HOME"], "config.yaml"))
    return daftar


def jenis_berkas(path, a):
    """'konfigurasi yang berjalan otomatis' atau 'bidang penegakan' untuk satu path tujuan tulis, atau None."""
    if any(g.inside(path, b) for b in bidang_penegakan()):
        return "bidang penegakan"
    if not g.inside(path, a.projects_root):
        return None
    bagian = [b.lower() for b in os.path.normpath(os.path.abspath(path)).split(os.sep)]
    nama, induk = bagian[-1], (bagian[-2] if len(bagian) > 1 else "")
    if nama.endswith(".code-workspace") or nama == ".mcp.json" or (induk, nama) in OTOMATIS:
        return "konfigurasi yang berjalan otomatis"
    if ".git" in bagian and bagian[bagian.index(".git") + 1:bagian.index(".git") + 2] == ["hooks"]:
        return "konfigurasi yang berjalan otomatis"
    return None


def alasan_tanya(jenis, apa):
    if jenis == "bidang penegakan":
        return (f"Penjaga repo: {apa} termasuk bidang penegakan (skrip penjaga atau konfigurasi hook). Penjaga yang ditukar diam-diam "
                "tampak sama dengan penjaga yang bekerja, jadi perubahan di sini ditanyakan ke pengguna dulu.")
    if jenis == "paket":
        return (f"Penjaga repo: {apa} memasang atau menjalankan paket pihak ketiga, yang skrip pasangnya ikut jalan dengan hak "
                "penuh di folder proyek tepercaya. Pastikan paketnya memang yang dimaksud.")
    if jenis == "unduhan":
        return (f"Penjaga repo: {apa} mengunduh berkas ke folder proyek tepercaya, atau langsung menjalankan unduhannya. "
                "Pastikan sumbernya dikenal.")
    return (f"Penjaga repo: {apa} adalah konfigurasi yang dijalankan komponen lain tanpa ditanya (task editor, hook agent, "
            "server MCP, hook git). Pastikan isinya memang yang dimaksud.")


def periksa_tulis(paths, a):
    """(keputusan, alasan) untuk alat tulis berkas: tanya kalau menulis konfigurasi otomatis atau bidang penegakan."""
    for path in paths:
        jenis = jenis_berkas(path, a)
        if jenis:
            return "ask", alasan_tanya(jenis, path), jenis
    return None, None, None


def paket_baru(verb, args, base):
    """Apakah satu bagian perintah memasang atau menjalankan paket pihak ketiga. Instal dari lockfile, requirements, atau
    path lokal tidak dihitung, begitu juga npx untuk alat yang sudah terpasang di node_modules/.bin proyek itu."""
    if verb in ("python", "python3", "py") and args[:2] == ["-m", "pip"]:
        verb, args = "pip", args[2:]
    if verb == "uv" and args[:2] == ["pip", "install"]:
        verb, args = "pip", args[1:]
    if verb in ("npx", "bunx", "pnpx"):
        nama = next((w for w in args if not w.startswith("-")), "")
        nama = re.sub(r"(?<=.)@[^/]*$", "", nama).split("/")[-1]
        terpasang = nama and any(os.path.exists(os.path.join(base, "node_modules", ".bin", nama + e)) for e in ("", ".cmd"))
        return not terpasang and "--no-install" not in args
    if verb in JALANKAN_UNDUH or (verb in ("pnpm", "yarn") and args[:1] == ["dlx"]) or (verb == "pipx" and args[:1] == ["run"]):
        return True
    if verb not in PAKET or not args or args[0].lower() not in PAKET[verb]:
        return False
    posisi, i, rest = [], 0, args[1:]
    while i < len(rest):
        w = rest[i]
        if w in NILAI_OPSI:
            i += 2
            continue
        if not w.startswith("-"):
            posisi.append(w)
        i += 1
    lokal = lambda w: w in (".", "..") or w.startswith(("./", "../", ".\\", "..\\", "file:")) or re.match(r"^[a-zA-Z]:[\\/]", w) or w.endswith((".whl", ".tgz", ".tar.gz"))
    return any(not lokal(w) for w in posisi)


def unduhan(verb, args, outs, base, a, pipa_ke):
    """Apakah satu bagian perintah mengunduh berkas ke folder proyek, atau unduhannya dialirkan ke shell (pipa_ke)."""
    if verb not in UNDUH:
        return False
    url = [w for w in args if re.match(r"(?i)https?://", w)]
    if url and all(re.match(r"(?i)https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?(?:/|$)", u) for u in url):
        return False   # server sendiri di mesin ini
    if pipa_ke in PENERIMA_SKRIP:
        return True
    tujuan = [args[i + 1] for i, w in enumerate(args[:-1]) if w.lower() in KELUARAN_UNDUH] + list(outs)
    if verb == "wget" and not any(w.lower() in ("-o", "-o-", "--output-document", "--spider") or w.startswith("--output-document=")
                                  for w in args):
        tujuan.append(".")   # wget menyimpan ke folder aktif secara bawaan; -O- dan -O - berarti ke stdout
    if verb == "curl" and any(w in ("-O", "--remote-name", "-OJ", "-JO") for w in args):
        tujuan.append(".")
    return any(t not in ("-", "/dev/null") and g.inside(path_lokal(t, base), a.projects_root) for t in tujuan)


def path_lokal(teks, base):
    """Path lokal penuh dari argumen: /d/x, D:\\x, file:///d/x, atau relatif terhadap base."""
    if teks.lower().startswith("file:"):
        teks = unquote(urlparse(teks).path)
    teks = g.GIT_BASH.sub(r"\1:/", teks)
    if re.match(r"^/[a-zA-Z]:", teks):  # /D:/x dari URL file Windows
        teks = teks[1:]
    return os.path.normpath(os.path.join(base, os.path.expanduser(teks)))


def pemilik_url(src):
    """Pemilik repo dari URL jarak jauh, atau None kalau src bukan URL jarak jauh."""
    m = SCP_LIKE.match(src)
    if m:
        return m.group(1).strip("/").split("/")[0]
    u = urlparse(src)
    if u.scheme in ("http", "https", "ssh", "git"):
        bagian = [b for b in u.path.split("/") if b]
        return bagian[0] if bagian else ""
    return None


def nama_repo(src):
    akhir = re.split(r"[\\/:]", src.rstrip("/\\"))[-1]
    return re.sub(r"\.git$", "", akhir) or "repo"


def sendiri(src, base, a):
    """Apakah sumber clone milik sendiri: URL dengan pemilik --own-owner, atau path lokal di --projects-root."""
    pemilik = pemilik_url(src)
    if pemilik is not None:
        return pemilik.lower() in {o.lower() for o in a.own_owner}
    lokal = path_lokal(src, base)
    return g.inside(lokal, a.projects_root) and not g.inside(lokal, a.repo_luar)


def cek_tanya(words, outs, base, a, pipa_ke=""):
    """(alasan tanya, jenis) untuk satu bagian perintah shell, atau (None, None) (riset M1)."""
    words = [g.clean(w) for w in words]
    while words and (words[0].lower() in g.SHELL_PREFIX or re.match(r"\w+=", words[0])):
        words = words[1:]
    if not words:
        return None, None
    verb = re.sub(r"\.(?:exe|cmd|bat)$", "", re.split(r"[\\/]", words[0])[-1].lower())
    args = words[1:]
    if paket_baru(verb, args, base):
        return alasan_tanya("paket", " ".join(words)[:120]), "paket"
    if unduhan(verb, args, [g.clean(o) for o in outs], base, a, pipa_ke):
        return alasan_tanya("unduhan", " ".join(words)[:120]), "unduhan"
    tulis = verb in g.WRITE_VERBS or (verb in g.INPLACE_VERBS and any(g.INPLACE_FLAG.match(w) for w in args))
    calon = [g.clean(o) for o in outs if g.clean(o).lower() not in g.NULL_SINKS and not o.startswith("&")]
    posisi = [w for w in args if not w.startswith("-")] if tulis else []
    # Salinan membiarkan sumbernya utuh, jadi hanya tujuannya yang ditulis (salah tangkap 2026-11-13: cp dari settings.json)
    calon += posisi[1:2] if verb == "robocopy" else posisi[-1:] if verb in SALIN_TUJUAN else posisi
    for c in calon:
        jenis = jenis_berkas(path_lokal(os.path.expandvars(c), base), a)
        if jenis:
            return alasan_tanya(jenis, c), jenis
    return None, None


def cek_kata(words, base, a, kedalaman=0):
    """Alasan tolak untuk satu bagian perintah, atau None. Mengembalikan (alasan, base baru)."""
    words = [g.clean(w) for w in words]
    while words and (words[0].lower() in g.SHELL_PREFIX or re.match(r"\w+=", words[0])):
        words = words[1:]
    if not words:
        return None, base
    verb = re.sub(r"\.(?:exe|cmd|bat)$", "", re.split(r"[\\/]", words[0])[-1].lower())
    args = words[1:]
    if verb in g.CD_VERBS:
        tujuan = next((w for w in args if not w.startswith("-")), None)
        return None, (path_lokal(tujuan, base) if tujuan else base)
    if verb in BUNGKUS and kedalaman < 2:  # bash -c "...", powershell -Command "..."
        for i, w in enumerate(args):
            if w.lower() in ("-c", "/c", "-command", "-lc", "/k"):
                return periksa(" ".join(args[i + 1:]), base, a, kedalaman + 1), base
        return None, base
    if verb == "git":
        while args and args[0].startswith("-"):  # opsi global git, misalnya -C <folder> dan -c kunci=nilai
            if args[0] == "-C" and len(args) > 1:
                base = path_lokal(args[1], base)
                args = args[2:]
            elif args[0] == "-c" and len(args) > 1:
                args = args[2:]
            else:
                args = args[1:]
        if args[:1] == ["clone"]:
            return cek_clone(args[1:], base, a), base
        return None, base
    if verb == "gh" and args[:2] == ["repo", "clone"]:
        posisi = []
        for w in args[2:]:
            if w == "--":
                break
            if not w.startswith("-"):
                posisi.append(w)
        if posisi:
            src = posisi[0]
            if "/" in src and pemilik_url(src) is None and not re.match(r"^[a-zA-Z]:|^[./\\]", src):
                src = f"https://github.com/{src}"  # gh repo clone pemilik/repo
            return cek_clone_ke(src, posisi[1] if len(posisi) > 1 else None, base, a), base
        return None, base
    if verb in SALIN:
        lokal = [path_lokal(w, base) for w in args if not w.startswith("-") and not g.WINDOWS_SWITCH.fullmatch(w)]
        dari_luar = any(g.inside(p, a.repo_luar) for p in lokal)
        ke_dalam = [p for p in lokal if g.inside(p, a.projects_root)]
        if dari_luar and ke_dalam:
            return (f"Ditolak penjaga repo luar: perintah ini menyalin atau memindah isi {a.repo_luar} ke {ke_dalam[0]}, "
                    f"padahal semua folder di {a.projects_root} dipercaya dan langsung menjalankan hook repo. Aturan Always di "
                    f"{os.path.join(a.projects_root, 'AGENTS.md')}: repo pihak ketiga tetap di {a.repo_luar}. Kalau pengguna "
                    "ingin memakainya di proyek, minta persetujuannya dulu dan biarkan pengguna yang memindahnya."), base
    return None, base


def cek_clone(args, base, a):
    posisi, i = [], 0
    while i < len(args):
        w = args[i]
        if w == "--":
            posisi += args[i + 1:]
            break
        if w in CLONE_NILAI:
            i += 2
            continue
        if not w.startswith("-"):
            posisi.append(w)
        i += 1
    if not posisi:
        return None
    return cek_clone_ke(posisi[0], posisi[1] if len(posisi) > 1 else None, base, a)


def cek_clone_ke(src, dst, base, a):
    tujuan = path_lokal(dst, base) if dst else os.path.normpath(os.path.join(base, nama_repo(src)))
    if not g.inside(tujuan, a.projects_root) or sendiri(src, base, a):
        return None
    benar = os.path.join(a.repo_luar, nama_repo(src))
    return (f"Ditolak penjaga repo luar: {src} adalah repo pihak ketiga, dan tujuannya {tujuan} ada di dalam {a.projects_root}, "
            "yang dipercaya dan langsung menjalankan hook repo. Aturan Always di "
            f"{os.path.join(a.projects_root, 'AGENTS.md')}: clone ke {benar}, lalu sebelum dipakai periksa apa yang bisa jalan "
            "sendiri (hook, aturan, dan skill di .agents, .vscode\\tasks.json, .claude\\settings.json, .mcp.json) dan laporkan ke "
            f"pengguna. Jangan jalankan skrip pasangnya sebelum diperiksa. Ulangi dengan tujuan {benar}.")


def periksa(command, base, a, kedalaman=0):
    """Alasan tolak pertama di seluruh perintah, atau None. cd di bagian awal ikut mengubah folder dasar bagian berikutnya."""
    for words, _ in g.shell_segments(command):
        alasan, base = cek_kata(words, base, a, kedalaman)
        if alasan:
            return alasan
    return None


def periksa_shell(command, base, a):
    """(keputusan, alasan, jenis) untuk satu perintah shell: tolak (clone dan salinan repo luar) didahulukan, lalu tanya
    (riset M1). Pemisah | dicatat supaya `curl ... | bash` dikenali."""
    alasan = periksa(command, base, a)
    if alasan:
        return "deny", alasan, "repo pihak ketiga ke folder proyek"
    segmen, potong = g.shell_segments(command), [p for p in g.SHELL_PIECE.findall(command) if p in g.SHELL_SEPARATORS]
    for i, (words, outs) in enumerate(segmen):
        if words and g.clean(words[0]).lower() in g.CD_VERBS:
            tujuan = next((w for w in words[1:] if not w.startswith("-")), None)
            base = path_lokal(g.clean(tujuan), base) if tujuan else base
            continue
        berikut = segmen[i + 1][0] if i + 1 < len(segmen) and i < len(potong) and potong[i] == "|" else []
        pipa_ke = re.sub(r"\.(?:exe|cmd|bat)$", "", re.split(r"[\\/]", g.clean(berikut[0]))[-1].lower()) if berikut else ""
        alasan, jenis = cek_tanya(words, outs, base, a, pipa_ke)
        if alasan:
            return "ask", alasan, jenis
    for b in bidang_penegakan():
        if g.inline_write(command, b):
            return "ask", alasan_tanya("bidang penegakan", b), "bidang penegakan"
    return None, None, None


def main():
    sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Hook sebelum perintah shell dan tulisan berkas: tolak clone repo pihak ketiga ke "
                                            "folder proyek tepercaya dan salinan dari folder repo luar ke sana, lalu tanyakan "
                                            "tulisan ke konfigurasi otomatis dan bidang penegakan, pemasangan paket, dan unduhan.")
    p.add_argument("--format", choices=("claude", "hermes", "antigravity"), required=True)
    p.add_argument("--projects-root", required=True, help="Folder proyek tepercaya, mis. D:/CODE")
    p.add_argument("--repo-luar", required=True, help="Folder untuk repo pihak ketiga, mis. 'D:/Repo Luar'")
    p.add_argument("--own-owner", action="append", default=[], help="Pemilik repo GitHub milik sendiri (boleh diulang)")
    try:
        a = p.parse_args()
    except SystemExit:  # argumen salah tidak boleh menahan semua perintah
        print('{"decision": "allow"}' if "antigravity" in sys.argv else "", end="")
        return 0
    a.projects_root, a.repo_luar = os.path.normpath(a.projects_root), os.path.normpath(a.repo_luar)
    keputusan = alasan = jenis = None
    try:
        hook = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
        command, base = perintah(a.format, hook)
        if command:
            keputusan, alasan, jenis = periksa_shell(command, base, a)
        else:
            paths = tujuan_tulis(a.format, hook)
            if paths:
                keputusan, alasan, jenis = periksa_tulis(paths, a)
    except Exception as e:
        print(f"Penjaga repo luar gagal memeriksa ({type(e).__name__}: {e}), perintah dibiarkan lewat.", file=sys.stderr)
        g.catat_keputusan("penjaga_repo", a.format, "galat", "gagal memeriksa, dibiarkan lewat", galat=type(e).__name__)
        keputusan = None
    if keputusan == "ask" and a.format != "hermes":   # tanya hanya untuk Hermes (keputusan pengguna 2026-11-14)
        keputusan = alasan = jenis = None
    if keputusan:   # kategori saja: pesannya bisa memuat URL repo atau nama paket
        g.catat_keputusan("penjaga_repo", a.format, keputusan, jenis)
    if a.format == "antigravity":
        print(json.dumps({"decision": keputusan, "reason": alasan} if keputusan else {"decision": "allow"}))
        return 0
    if keputusan == "ask":   # Hermes: gerbang persetujuan manusia, menolak kalau tidak ada manusia (approval.py)
        print(json.dumps({"action": "approve", "message": alasan}))
        return 0
    if keputusan:
        print(alasan, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
