"""Penjaga repo luar: hook sebelum perintah shell, untuk aturan repo pihak ketiga di protokol D:\\CODE (sejak 2026-11-12).

Yang ditolak:
- `git clone` dan `gh repo clone` repo pihak ketiga dengan tujuan di dalam --projects-root.
- Menyalin atau memindah isi --repo-luar ke dalam --projects-root (cp, mv, robocopy, Copy-Item, dan sejenisnya).
Repo milik sendiri boleh: URL yang pemiliknya --own-owner, atau path lokal di dalam --projects-root. Pesan tolaknya menunjuk
tempat yang benar, jadi agent bisa mengulang dengan tujuan di --repo-luar.

Tiga format hook, sama dengan penjaga_desain.py:
- claude: PreToolUse Claude Code untuk Bash dan PowerShell. Keluar 2 dengan alasan di stderr.
- hermes: pre_tool_call Hermes untuk terminal. Keluar 2 dengan alasan di stderr. Folder sesi dibaca dari state.db.
- antigravity: PreToolUse Antigravity untuk run_command. Keputusan berupa JSON di stdout, selalu keluar 0.
Latar: uji sesi nyata 2026-11-12, Hermes meng-clone repo kiriman ke D:\\CODE dan menjalankan skrip pasangnya walau aturannya
sudah ada. Ini pengingat, bukan pagar keamanan penuh: perintah yang tidak dikenali dan galat pemeriksaan lolos (fail open)."""
import os
import re
import sys
import json
import argparse
from urllib.parse import unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vault_guard as g  # pemecah perintah shell, path gaya Git Bash, folder sesi Hermes, dan cek di dalam folder (Aturan 6)

SHELL = {"claude": ("Bash", "PowerShell"), "hermes": ("terminal",), "antigravity": ("run_command",)}
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


def main():
    sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Hook sebelum perintah shell: tolak clone repo pihak ketiga ke folder proyek "
                                            "tepercaya, dan salinan dari folder repo luar ke sana.")
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
    alasan = None
    try:
        hook = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
        command, base = perintah(a.format, hook)
        if command:
            alasan = periksa(command, base, a)
    except Exception as e:
        print(f"Penjaga repo luar gagal memeriksa ({type(e).__name__}: {e}), perintah dibiarkan lewat.", file=sys.stderr)
        g.catat_keputusan("penjaga_repo", a.format, "galat", "gagal memeriksa, dibiarkan lewat", galat=type(e).__name__)
    if alasan:   # kategori saja: pesan tolaknya bisa memuat URL repo
        g.catat_keputusan("penjaga_repo", a.format, "deny", "repo pihak ketiga ke folder proyek")
    if a.format == "antigravity":
        print(json.dumps({"decision": "deny", "reason": alasan} if alasan else {"decision": "allow"}))
        return 0
    if alasan:
        print(alasan, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
