"""Pasang kit agent di Windows: aturan, hook penjaga, kerangka vault, skill, dan RAG, dari templat di kit/.

Jalankan dari folder hasil clone. Folder itu sekaligus menjadi workspace agent, dan induknya menjadi folder kerja
(tempat proyek-proyekmu). Jadi clone repo ini langsung ke dalam folder kerja, misalnya D:\\Proyek\\Agent.

  python pasang.py --vault "D:/Obsidian/Memori Agent" --nama Budi [--github budi]
         [--platform claude,antigravity,hermes,zed] [--lindungi "<folder>"]... [--repo-luar "<folder>"]
         [--hermes-home "<folder>"] [--tanpa-rag] [--model-dari <folder>] [--uji-kering] [--paksa]

Berkas yang sudah ada tidak ditimpa: aturan, isi vault, .env, 9Router, dan skill dibiarkan, kecuali --paksa untuk
aturan (dengan cadangan .bak). Konfigurasi agent (settings.json Claude, hooks.json Antigravity, config.yaml Hermes)
digabung: hook milik sendiri tetap ada, hook kit lama diganti, dan berkas aslinya dicadangkan dulu ke .bak-<waktu>.
config.yaml Hermes yang sudah punya bagian hooks sendiri tidak disentuh: potongannya ditulis ke Konfigurasi/.
Hanya library bawaan Python. Logikanya diuji di tools/test_tools.py."""
import argparse
import copy
import datetime
import hashlib
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import sys
import urllib.request

WS = pathlib.Path(__file__).resolve().parent
KIT = WS / "kit"
TEMPLAT = KIT / "templat"
LABEL = "protokol folder kerja"
PLATFORM = ("claude", "antigravity", "hermes", "zed")
NAMA_PLATFORM = {"claude": "Claude Code", "antigravity": "Antigravity", "hermes": "Hermes", "zed": "Zed"}
BEGIN_KIT, END_KIT = "<!-- agent-kit:begin -->", "<!-- agent-kit:end -->"
BEGIN_YAML, END_YAML = "# agent-kit:begin", "# agent-kit:end"
# Model embedding RAG: ekspor ONNX resmi di repo Hugging Face-nya (lisensi MIT), dipatok ke satu revisi dan dicek hash-nya.
MODEL_REPO, MODEL_REV = "intfloat/multilingual-e5-small", "614241f622f53c4eeff9890bdc4f31cfecc418b3"
MODEL_BERKAS = {"model.onnx": (470268510, "ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665"),
                "tokenizer.json": (17082730, "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39")}
MODEL_DIR = WS / "tools" / "models" / "onnx" / MODEL_REPO.replace("/", "--")
TULIS_AG = "write_file|edit_file|write_to_file|replace_file_content|multi_replace_file_content"
VAULT_AG = TULIS_AG + "|read_file|view_file|list_dir|find_by_name|grep_search|run_command"
VAULT_HERMES = "write_file|patch|terminal|execute_code|read_file|search_files|vision_analyze|video_analyze|browser_navigate|web_extract"
LARANGAN = set('"%$`\n\r')   # tidak bisa dikutip aman sekaligus di Git Bash, .cmd, JSON, dan YAML
SKILL_KIT = ("grill-me", "grilling", "obsidian-workflow", "oper-kerja", "webapp-audit", "webapp-testing")

posix = lambda p: str(p).replace("\\", "/")
win = lambda p: str(p).replace("/", "\\")
waktu = lambda: datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def render(teks, nilai):
    """Ganti setiap {{KUNCI}}. Penanda yang tersisa berarti templat dan pemasang tidak cocok, jadi berhenti."""
    for k, v in nilai.items():
        teks = teks.replace("{{" + k + "}}", v)
    sisa = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", teks)))
    if sisa:
        raise ValueError(f"penanda templat belum terisi: {', '.join(sisa)}")
    return teks


def di_dalam(anak, induk):
    a, b = (os.path.normcase(os.path.abspath(p)) for p in (anak, induk))
    try:
        return os.path.commonpath([a, b]) == b
    except ValueError:   # beda drive
        return False


def kutip(p):
    """Program di awal perintah hook: tanpa kutip kalau bisa, supaya jalan di Git Bash, PowerShell, dan pemecah Hermes."""
    return f'"{p}"' if " " in str(p) else str(p)


def aturan_deny(folder):
    """Aturan deny izin Claude Code untuk satu folder: //<drive>/<path>/**, seperti bentuk yang dipakai pemilik kit."""
    p = posix(os.path.abspath(folder)).rstrip("/")
    drive, rest = (p[0].lower(), p[2:]) if re.match(r"^[A-Za-z]:", p) else ("", p)
    akar = f"//{drive}{rest}" if drive else f"/{rest.lstrip('/')}"
    return [f"Edit({akar}/**)", f"Read({akar}/**)"]


def pola_zed(folder):
    """Regex always_deny Zed untuk satu folder: dua bagian terakhir path-nya, huruf kecil, pemisah apa pun."""
    bagian = [b for b in re.split(r"[\\/]+", str(folder)) if b and not b.endswith(":")][-2:]
    def satu(b):
        return "".join(c.lower() if c.isalnum() or c in "_-" else ".{1,2}" if c == " " else f"[{c}]" if c not in "^]\\" else re.escape(c)
                       for c in b)
    return ".{1,2}".join(satu(b) for b in bagian) + "([^a-z0-9_]|$)"


def sisip_blok(teks, blok, begin=BEGIN_KIT, end=END_KIT):
    """Ganti blok berpenanda di teks, atau tambahkan di akhir kalau belum ada."""
    blok = blok.strip("\n")
    pola = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
    if pola.search(teks):
        return pola.sub(lambda m: blok, teks, count=1)
    return (teks.rstrip("\n") + "\n\n" if teks.strip() else "") + blok + "\n"


def gabung_claude(settings, hooks_kit, deny_kit, penanda):
    """Gabungkan hook kit ke settings Claude Code. Hook yang perintahnya memuat `penanda` (folder tools workspace ini)
    dianggap pasangan kit yang lama dan diganti. Hook lain dan aturan izin milik pengguna tetap ada."""
    s = copy.deepcopy(settings)
    hooks = s.setdefault("hooks", {})
    for event in list(hooks):
        grup = []
        for g in hooks[event]:
            sisa = [h for h in g.get("hooks", []) if penanda not in str(h.get("command", ""))]
            if sisa:
                grup.append({**g, "hooks": sisa})
        if grup:
            hooks[event] = grup
        else:
            del hooks[event]
    for event, grup in hooks_kit.items():
        hooks.setdefault(event, []).extend(copy.deepcopy(grup))
    if deny_kit:
        deny = s.setdefault("permissions", {}).setdefault("deny", [])
        deny.extend(r for r in deny_kit if r not in deny)
    return s


def gabung_hermes(teks, blok):
    """config.yaml Hermes dengan blok hooks kit, atau None kalau config punya bagian hooks sendiri yang tidak berpenanda.
    Bagian hooks yang kosong (`hooks:`, `hooks: {}`, atau `hooks: null` tanpa isi di bawahnya) diganti blok kit."""
    pola = re.compile(re.escape(BEGIN_YAML) + r".*?" + re.escape(END_YAML) + r"[^\n]*\n?", re.S)
    if pola.search(teks):
        return pola.sub(lambda m: blok, teks, count=1)
    kosong = re.compile(r"(?m)^hooks[ \t]*:[ \t]*(?:\{[ \t]*\}|\[[ \t]*\]|null|~)?[ \t]*(?:#[^\n]*)?(?:\n(?![ \t]+\S)|\Z)")
    if kosong.search(teks):
        teks = kosong.sub("", teks, count=1)
    elif re.search(r"(?m)^hooks[ \t]*:", teks):
        return None
    return (teks.rstrip("\n") + "\n\n" if teks.strip() else "") + blok


def yaml_kutip(s):
    return "'" + s.replace("'", "''") + "'"


class Penulis:
    """Semua tulisan lewat sini, supaya --uji-kering cukup mencetak rencananya."""
    def __init__(self, kering):
        self.kering, self.ditulis = kering, []

    def lapor(self, status, path, ket=""):
        print(f"  [{status}] {path}{'  ' + ket if ket else ''}")

    def cadangkan(self, path):
        bak = path.with_name(f"{path.name}.bak-{waktu()}")
        if not self.kering:
            shutil.copy2(path, bak)
        return bak

    def tulis(self, path, teks, timpa=False, ket=""):
        path = pathlib.Path(path)
        if path.exists() and not timpa:
            self.lapor("ADA", path, "dibiarkan")
            return False
        if path.exists():
            if path.read_bytes().decode("utf-8-sig", "replace") == teks:   # tanpa ubah akhir baris, supaya .cmd ber-CRLF dikenali sama
                self.lapor("SAMA", path)
                return False
            ket = f"cadangan {self.cadangkan(path).name}" + (f", {ket}" if ket else "")
        self.lapor("DITULIS", path, ket)
        if not self.kering:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(teks, encoding="utf-8", newline="\n")
        self.ditulis.append(path)
        return True

    def salin_folder(self, sumber, tujuan, nilai=None):
        """Salin pohon folder. Dengan `nilai`, berkas teks dan nama berkasnya dirender. Berkas yang ada dibiarkan."""
        for f in sorted(pathlib.Path(sumber).rglob("*")):
            if f.is_dir() or "__pycache__" in f.parts:
                continue
            rel = f.relative_to(sumber)
            dst = pathlib.Path(tujuan) / (render(str(rel), nilai) if nilai else rel)
            if nilai:
                self.tulis(dst, render(f.read_text(encoding="utf-8"), nilai))
            elif dst.exists():
                self.lapor("ADA", dst, "dibiarkan")
            else:
                self.lapor("DISALIN", dst)
                if not self.kering:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dst)


def baca_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig") or "{}")
    except ValueError as e:
        raise SystemExit(f"{path} bukan JSON yang sah ({e}). Perbaiki dulu, pasang.py tidak menimpanya.")


def tulis_json(p, path, data, ket=""):
    teks = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return p.tulis(path, teks, timpa=True, ket=ket)


def jalan(argv, **kw):
    print("  $ " + " ".join(f'"{a}"' if " " in str(a) else str(a) for a in argv))
    return subprocess.run([str(a) for a in argv], **kw).returncode


def unduh_model(tujuan, dari=None):
    """model.onnx dan tokenizer.json, dari folder lokal atau Hugging Face, dicek ukuran dan sha256-nya."""
    tujuan.mkdir(parents=True, exist_ok=True)
    for nama, (ukuran, sha) in MODEL_BERKAS.items():
        dst = tujuan / nama
        if dst.exists() and dst.stat().st_size == ukuran:
            print(f"  [ADA] {dst}")
            continue
        tmp = dst.with_name(dst.name + ".part")
        h = hashlib.sha256()
        if dari:
            with open(pathlib.Path(dari) / nama, "rb") as s, open(tmp, "wb") as d:
                for b in iter(lambda: s.read(1 << 20), b""):
                    h.update(b)
                    d.write(b)
        else:
            url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REV}/onnx/{nama}"
            print(f"  Mengunduh {url} ({ukuran / 1e6:.0f} MB)")
            req = urllib.request.Request(url, headers={"User-Agent": "agent-kit-pasang"})
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as d:
                n, tanda = 0, 0
                for b in iter(lambda: r.read(1 << 20), b""):
                    h.update(b)
                    d.write(b)
                    n += len(b)
                    if n * 10 // ukuran > tanda:
                        tanda = n * 10 // ukuran
                        print(f"    {tanda * 10}%", flush=True)
        if tmp.stat().st_size != ukuran or h.hexdigest() != sha:
            tmp.unlink()
            raise SystemExit(f"{nama}: ukuran atau sha256 tidak cocok dengan revisi {MODEL_REV[:12]}. Tidak dipakai.")
        os.replace(tmp, dst)
        print(f"  [DITULIS] {dst} (sha256 cocok)")


def main():
    # Per baris, supaya urutannya tetap benar di antara keluaran subproses (pip, sync_rules) saat dialihkan ke berkas log
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    p = argparse.ArgumentParser(description="Pasang kit agent: aturan, hook penjaga, kerangka vault, skill, dan RAG (Windows).")
    p.add_argument("--vault", required=True, help="Folder vault memori. Dibuat dari kerangka kalau belum ada atau kosong")
    p.add_argument("--nama", required=True, help="Nama panggilanmu, dipakai di aturan (misalnya 'Budi')")
    p.add_argument("--github", help="Nama akun GitHub-mu: repo milik akun ini boleh di-clone ke folder kerja")
    p.add_argument("--folder-kerja", help="Folder proyek-proyekmu. Harus induk folder repo ini (bawaannya memang begitu)")
    p.add_argument("--platform", default=",".join(PLATFORM), help="Agent yang dipasang, dipisah koma (bawaan: semua)")
    p.add_argument("--lindungi", action="append", help="Folder yang sama sekali tidak boleh dibuka agent (boleh diulang, bawaan ~/.ssh)")
    p.add_argument("--repo-luar", help="Folder untuk repo pihak ketiga (bawaan: 'Repo Luar' di sebelah folder kerja)")
    p.add_argument("--hermes-home", help="Folder data Hermes (bawaan: HERMES_HOME atau ~/.hermes)")
    p.add_argument("--home", help="Folder profil pengguna pengganti, untuk uji")
    p.add_argument("--tanpa-rag", action="store_true", help="Lewati venv, model embedding, dan indeks RAG")
    p.add_argument("--model-dari", help="Folder berisi model.onnx dan tokenizer.json yang sudah diunduh, alih-alih mengunduh")
    p.add_argument("--uji-kering", action="store_true", help="Cetak rencana tanpa menulis apa pun")
    p.add_argument("--paksa", action="store_true", help="Timpa berkas aturan yang sudah ada (dicadangkan dulu)")
    a = p.parse_args()

    if os.name != "nt":
        sys.exit("Kit ini baru untuk Windows.")
    if sys.version_info < (3, 10):
        sys.exit("Butuh Python 3.10 atau lebih baru.")
    home = pathlib.Path(a.home).resolve() if a.home else pathlib.Path.home()
    # Dengan --home (uji), APPDATA dan HERMES_HOME milik mesin ini sengaja tidak dipakai, supaya konfigurasi asli tidak tersentuh
    appdata = home / "AppData" / "Roaming" if a.home else pathlib.Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
    hermes_home = pathlib.Path(a.hermes_home or (None if a.home else os.environ.get("HERMES_HOME")) or home / ".hermes").resolve()
    fk = WS.parent
    if a.folder_kerja and os.path.normcase(os.path.abspath(a.folder_kerja)) != os.path.normcase(str(fk)):
        sys.exit(f"Folder kerja harus induk folder repo ini ({fk}). Clone repo ini ke dalam {a.folder_kerja}, lalu jalankan dari sana.")
    if fk.parent == fk:
        sys.exit("Repo ini ada langsung di akar drive. Clone ke dalam sebuah folder kerja, misalnya D:\\Proyek\\Agent.")
    vault = pathlib.Path(a.vault).resolve()
    if vault.parent == vault:
        sys.exit("Vault tidak boleh akar drive. Pilih sebuah folder, misalnya D:\\Obsidian\\Memori Agent.")
    py = pathlib.Path(sys.base_prefix) / "python.exe"   # Python dasar, bukan venv: hook harus tetap jalan walau venv dihapus
    py = py if py.exists() else pathlib.Path(sys.executable)
    repo_luar = pathlib.Path(a.repo_luar).resolve() if a.repo_luar else fk.parent / "Repo Luar"
    lindungi = [pathlib.Path(x).expanduser().resolve() for x in (a.lindungi or [str(home / ".ssh")])]
    platform = [x.strip() for x in a.platform.split(",") if x.strip()]
    if bad := [x for x in platform if x not in PLATFORM]:
        sys.exit(f"Platform tidak dikenal: {', '.join(bad)}. Pilihan: {', '.join(PLATFORM)}")
    if a.github and not re.fullmatch(r"[A-Za-z0-9-]{1,39}", a.github):
        sys.exit("--github harus nama akun GitHub saja, tanpa URL.")
    nama = a.nama.strip()
    if not nama or any(c in nama for c in '"{}\n\r'):
        sys.exit("--nama tidak boleh kosong atau memuat kutip dan kurung kurawal.")
    for label, path in [("workspace", WS), ("vault", vault), ("repo luar", repo_luar), ("profil", home), ("Hermes", hermes_home),
                        ("Python", py), *[("folder dilindungi", x) for x in lindungi]]:
        if any(c in LARANGAN for c in str(path)):
            sys.exit(f"Path {label} memuat karakter yang tidak didukung (kutip, %, $, atau backtick): {path}")
    if di_dalam(vault, fk) or di_dalam(fk, vault):
        sys.exit("Vault dan folder kerja harus terpisah, tidak boleh saling memuat.")
    if di_dalam(repo_luar, fk):
        sys.exit("Folder repo luar tidak boleh di dalam folder kerja. Pilih dengan --repo-luar.")
    for x in lindungi:
        if di_dalam(vault, x) or di_dalam(x, vault) or di_dalam(WS, x) or di_dalam(x, WS):
            sys.exit(f"Folder dilindungi {x} tidak boleh memuat atau berada di dalam vault atau workspace.")
    reg_path = WS / "Konfigurasi" / "rule_sync.json"
    if reg_path.exists() and baca_json(reg_path).get("dipasang_oleh") != "pasang.py" and not a.paksa:
        sys.exit(f"{reg_path} ada tapi bukan buatan pasang.py: workspace ini sudah dipasang dengan cara lain. "
                 "Jalankan di clone baru, atau pakai --paksa kalau memang mau ditimpa (berkas lama dicadangkan).")
    fk_agents = fk / "AGENTS.md"
    if fk_agents.exists() and not a.paksa and f"<!-- sync:begin {LABEL} -->" not in fk_agents.read_text(encoding="utf-8-sig"):
        sys.exit(f"{fk_agents} sudah ada tanpa penanda sync kit. Pindahkan isinya dulu, atau pakai --paksa (berkas lama dicadangkan).")

    ada = {"claude": (home / ".claude").is_dir(), "antigravity": (home / ".gemini").is_dir(),
           "hermes": hermes_home.is_dir(), "zed": (appdata / "Zed").is_dir()}
    lewat = [x for x in platform if not ada[x]]
    platform = [x for x in platform if ada[x]]
    tanggal = datetime.date.today().isoformat()
    ag_hooks = home / ".gemini" / "config" / "hooks"
    # Antigravity memecah perintah hook per spasi, dan cmd.exe membaca berkas .cmd dengan code page OEM, bukan UTF-8
    ag_masalah = ((" " in str(ag_hooks) and f"path {ag_hooks} memuat spasi")
                  or (not all(str(x).isascii() for x in (py, WS, fk, vault, repo_luar, ag_hooks, *lindungi)) and "ada path berhuruf non-ASCII"))
    ag_berhook = "antigravity" in platform and not ag_masalah
    hermes_cfg = hermes_home / "config.yaml"

    PY, WSP, VP, FKP, RLP = kutip(posix(py)), posix(WS), posix(vault), posix(fk), posix(repo_luar)
    nama_ws = WS.name
    protect = "".join(f' --protect "{posix(x)}"' for x in lindungi)
    protect_win = "".join(f' --protect "{win(x)}"' for x in lindungi)
    owner = f" --own-owner {a.github}" if a.github else ""
    uji = ["python tools/uji_penjaga.py"]
    if "claude" in platform:
        uji.append(f'--claude-settings "{posix(home)}/.claude/settings.json"')
    if ag_berhook:
        uji.append(f'--antigravity-hooks "{posix(home)}/.gemini/config/hooks.json"')
    if "hermes" in platform:
        uji.append(f'--hermes-config "{posix(hermes_cfg)}"')
    uji_teks = " ".join(uji) if len(uji) > 1 else "(tidak ada platform berhook yang terpasang)"
    rag = not a.tanpa_rag
    daftar = [f"- Aturan: protokol di `{fk}\\AGENTS.md`, aturan lengkap di `{WS}\\AGENTS.md`, keduanya dengan cermin `AGENTS_id.md`.",
              f"- Platform: {', '.join(NAMA_PLATFORM[x] for x in platform) or 'tidak ada'}"
              + (f". Dilewati karena belum terpasang: {', '.join(NAMA_PLATFORM[x] for x in lewat)}." if lewat else "."),
              f"- Folder yang dilindungi: {', '.join(f'`{x}`' for x in lindungi)}.",
              f"- Skill: {', '.join(f'`{s}`' for s in SKILL_KIT)}.",
              f"- RAG: {'model ' + MODEL_REPO + ' (ONNX), indeks vault dibuat saat pemasangan' if rag else 'dilewati (--tanpa-rag)'}."]
    nilai = {"NAMA": nama, "TANGGAL": tanggal, "BULAN": tanggal[:7], "LABEL": LABEL, "WORKSPACE": str(WS), "WORKSPACE_POSIX": WSP,
             "NAMA_WORKSPACE": nama_ws, "FOLDER_KERJA": str(fk), "FOLDER_KERJA_POSIX": FKP, "VAULT": str(vault), "VAULT_POSIX": VP,
             "REPO_LUAR": str(repo_luar), "DILINDUNGI": ", ".join(f"`{x}`" for x in lindungi), "HOME_POSIX": posix(home),
             "HERMES_HOME_POSIX": posix(hermes_home), "UJI_PENJAGA": uji_teks, "DAFTAR_PASANG": "\n".join(daftar)}

    print(f"Workspace   : {WS}\nFolder kerja: {fk}\nVault       : {vault}\nRepo luar   : {repo_luar}\n"
          f"Dilindungi  : {', '.join(map(str, lindungi))}\nPlatform    : {', '.join(platform) or '-'}"
          + (f"  (dilewati, belum terpasang: {', '.join(lewat)})" if lewat else ""))
    if "antigravity" in platform and not ag_berhook:
        print(f"  Catatan Antigravity: {ag_masalah}, jadi hook-nya tidak dipasang (perintah hook dipecah per spasi, dan berkas "
              ".cmd dibaca dengan code page OEM). Aturannya tetap dipasang.")
    w = Penulis(a.uji_kering)

    print("\n# Vault")
    isi = [x for x in vault.iterdir() if x.name != ".obsidian"] if vault.is_dir() else []
    if isi:
        print(f"  [ADA] {vault} sudah berisi, kerangka tidak ditulis. Pastikan ada Wiki/system/Referensi Desain.md dan hot.md.")
    else:
        w.salin_folder(KIT / "vault", vault, nilai)

    print("\n# Aturan")
    for d, sumber in ((fk, TEMPLAT / "folder-kerja"), (WS, TEMPLAT / "workspace")):
        for f in sorted(sumber.iterdir()):
            w.tulis(d / f.name, render(f.read_text(encoding="utf-8"), nilai), timpa=a.paksa)
    konf = WS / "Konfigurasi"
    for f in sorted((TEMPLAT / "konfigurasi").iterdir()):
        w.tulis(konf / f.name, render(f.read_text(encoding="utf-8"), nilai), timpa=a.paksa and f.name != "penjaga_vault_terlarang.txt")

    # Salinan aturan: kepala berkas plus blok sync kosong, isinya ditulis sync_rules.py di bawah
    salinan = []   # (path, templat, nama platform)
    if "claude" in platform:
        salinan.append((fk / "CLAUDE.md", "CLAUDE.md", "Claude Code"))
    if "antigravity" in platform:
        salinan.append((home / ".gemini" / "GEMINI.md", "GEMINI.md", "Antigravity (aturan global)"))
    if "zed" in platform:
        salinan.append((appdata / "Zed" / "AGENTS.md", "Zed AGENTS.md", "Zed (aturan global)"))
    if "hermes" in platform:
        salinan.append((hermes_home / "SOUL.md", "SOUL.md", "Hermes (SOUL.md dimuat di setiap sesi)"))
    for path, tpl, _ in salinan:
        kepala = render((TEMPLAT / "salinan" / tpl).read_text(encoding="utf-8"), nilai)
        lama = path.read_text(encoding="utf-8-sig") if path.exists() else ""
        if f"<!-- sync:begin {LABEL} -->" in lama:
            w.lapor("ADA", path, "blok sync sudah ada")
        else:
            w.tulis(path, (lama.rstrip("\n") + "\n\n" if lama.strip() else "") + kepala, timpa=True,
                    ket="blok sync ditambahkan" if lama.strip() else "")

    print("\n# Agent")
    cadangan_files, redact = [], []
    tools = f"{WSP}/tools/"
    if "claude" in platform:
        claude = home / ".claude"
        blok = render((TEMPLAT / "claude" / "CLAUDE.md").read_text(encoding="utf-8"), nilai)
        lama = (claude / "CLAUDE.md").read_text(encoding="utf-8-sig") if (claude / "CLAUDE.md").exists() else "# CLAUDE.md\n\nAturan global Claude Code di komputer ini.\n"
        w.tulis(claude / "CLAUDE.md", sisip_blok(lama, blok), timpa=True)
        cmd = lambda alat, arg, aman=False: f'{PY} "{tools}{alat}" {arg}'.rstrip() + (" 2>/dev/null || true" if aman else "")
        hooks = {
            "PreToolUse": [
                {"matcher": "Write|Edit|MultiEdit", "hooks": [
                    {"type": "command", "command": cmd("vault_guard.py", f'--vault "{VP}" --words "{WSP}/Konfigurasi/penjaga_vault_terlarang.txt" --secrets-from "{WSP}/.env"'),
                     "timeout": 10, "onFailure": "block"},
                    {"type": "command", "command": cmd("penjaga_desain.py", f'--format claude --projects-root "{FKP}" --vault "{VP}"'), "timeout": 10}]},
                {"matcher": "Bash|PowerShell", "hooks": [
                    {"type": "command", "command": cmd("penjaga_repo.py", f'--format claude --projects-root "{FKP}" --repo-luar "{RLP}"{owner}'), "timeout": 10},
                    {"type": "command", "command": cmd("vault_guard.py", f'--format claude --vault "{VP}"{protect}'), "timeout": 10, "onFailure": "block"}]},
                # Untuk hemat token, subagent wajib menyebut model, dan peringatan saat kembali ke sesi besar sesudah jeda.
                # Pemilik kit memakai penahan_jeda dengan --tahan, kit memasangnya hanya memperingatkan.
                {"matcher": "Agent|Task", "hooks": [
                    {"type": "command", "command": cmd("penjaga_subagent.py", f'--agents "{posix(claude)}/agents"', True), "timeout": 10}]}],
            "UserPromptSubmit": [{"hooks": [
                {"type": "command", "command": cmd("penahan_jeda.py", "", True), "timeout": 10}]}],
            "SessionStart": [{"hooks": [
                {"type": "command", "command": cmd("session_context.py", f'--projects-root "{FKP}" --vault "{VP}" --skip "{nama_ws}"', True), "timeout": 15}]}],
            "Stop": [{"hooks": [
                {"type": "command", "command": cmd("export_transcript.py", f'--out "{WSP}/Riwayat Perckapan" --projects-root "{FKP}" --skip "{nama_ws}" --secrets-from "{WSP}/.env"', True),
                 "timeout": 30, "async": True},
                {"type": "command", "command": cmd("cek_proses_sisa.py", "--hook", True), "timeout": 15},
                {"type": "command", "command": cmd("cek_jurnal.py", f'--hook --vault "{VP}" --projects-root "{FKP}"', True), "timeout": 20}]}]}
        deny = [r for x in lindungi for r in aturan_deny(x)]
        st = claude / "settings.json"
        tulis_json(w, st, gabung_claude(baca_json(st), hooks, deny, tools), "hook kit digabung")
        cadangan_files.append(st)
        redact.append(st)
        lokal = WS / ".claude" / "settings.local.json"
        hooks_ws = {"SessionStart": [{"hooks": [{"type": "command", "command": cmd("session_context.py", f'"{VP}/hot.md"'), "timeout": 15}]}],
                    "Stop": [{"hooks": [{"type": "command", "command": cmd("export_transcript.py", f'--out "{WSP}/Riwayat Perckapan" --secrets-from "{WSP}/.env"', True),
                                         "timeout": 30, "async": True}]}]}
        tulis_json(w, lokal, gabung_claude(baca_json(lokal), hooks_ws, [], tools))
        cadangan_files.append(lokal)
        for f in sorted((TEMPLAT / "claude" / "agents").iterdir()):
            w.tulis(claude / "agents" / f.name, f.read_text(encoding="utf-8"))
    if ag_berhook:
        bungkus = {
            "konteks_vault": f'"{win(py)}" "{win(WS)}\\tools\\session_context.py" --format antigravity --projects-root "{fk}" --vault "{vault}" --skip "{nama_ws}" "{vault}\\hot.md"',
            "penjaga_desain": f'"{win(py)}" "{win(WS)}\\tools\\penjaga_desain.py" --format antigravity --projects-root "{fk}" --vault "{vault}"',
            "penjaga_repo": f'"{win(py)}" "{win(WS)}\\tools\\penjaga_repo.py" --format antigravity --projects-root "{fk}" --repo-luar "{repo_luar}"{owner}',
            "vault_guard": f'"{win(py)}" "{win(WS)}\\tools\\vault_guard.py" --format antigravity --vault "{vault}" --words "{WS}\\Konfigurasi\\penjaga_vault_terlarang.txt" --secrets-from "{WS}\\.env"{protect_win}'}
        for n, c in bungkus.items():
            w.tulis(ag_hooks / f"{n}.cmd", f"@echo off\r\nrem Ditulis pasang.py dari kit agent pada {tanggal}. Sumber: {WS}\\tools\r\n{c}\r\n", timpa=True)
            cadangan_files.append(ag_hooks / f"{n}.cmd")
        hp = lambda n: posix(ag_hooks / f"{n}.cmd")
        grup = {"konteks-vault": {"SessionStart": [{"type": "command", "command": hp("konteks_vault"), "timeout": 20}]},
                "penjaga-desain": {"PreToolUse": [{"matcher": TULIS_AG, "hooks": [{"type": "command", "command": hp("penjaga_desain"), "timeout": 20}]}]},
                "penjaga-repo": {"PreToolUse": [{"matcher": "run_command", "hooks": [{"type": "command", "command": hp("penjaga_repo"), "timeout": 20}]}]},
                "penjaga-vault": {"PreToolUse": [{"matcher": VAULT_AG, "hooks": [{"type": "command", "command": hp("vault_guard"), "timeout": 20}]}]}}
        hj = home / ".gemini" / "config" / "hooks.json"
        tulis_json(w, hj, {**baca_json(hj), **grup}, "grup hook kit diganti")
        cadangan_files.append(hj)
    hermes_berhook = False
    if "hermes" in platform:
        # Argumen dirakit di luar f-string: backslash di dalam ekspresi f-string baru boleh mulai Python 3.12
        hcmd = lambda alat, arg: "command: " + yaml_kutip(f'{PY} "{tools}{alat}" {arg}')
        arg_vault = f'--vault "{VP}" --words "{WSP}/Konfigurasi/penjaga_vault_terlarang.txt" --secrets-from "{WSP}/.env"{protect}'
        arg_desain = f'--format hermes --projects-root "{FKP}" --vault "{VP}"'
        arg_repo = f'--format hermes --projects-root "{FKP}" --repo-luar "{RLP}"{owner}'
        arg_konteks = f'--format hermes --projects-root "{FKP}" --vault "{VP}" --skip "{nama_ws}" "{VP}/hot.md"'
        blok = "\n".join([
            f"{BEGIN_YAML} (ditulis pasang.py dari kit agent pada {tanggal}. Jangan disunting, jalankan ulang pasang.py)",
            "hooks:", "  pre_tool_call:",
            f'    - matcher: "{VAULT_HERMES}"',
            "      " + hcmd("vault_guard.py", arg_vault),
            "      timeout: 20", "      fail_closed: true",
            '    - matcher: "write_file|patch"',
            "      " + hcmd("penjaga_desain.py", arg_desain),
            "      timeout: 20",
            '    - matcher: "terminal|write_file|patch"',
            "      " + hcmd("penjaga_repo.py", arg_repo),
            "      timeout: 20",
            "  pre_llm_call:",
            "    - " + hcmd("session_context.py", arg_konteks),
            "      timeout: 20", END_YAML, ""])
        baru = gabung_hermes(hermes_cfg.read_text(encoding="utf-8-sig"), blok) if hermes_cfg.exists() else None
        if baru is not None:
            w.tulis(hermes_cfg, baru, timpa=True, ket="blok hooks kit")
            hermes_berhook = True
            cadangan_files.append(hermes_cfg)
            redact.append(hermes_cfg)
        else:
            alasan = "belum ada (jalankan hermes setup dulu)" if not hermes_cfg.exists() else "sudah punya bagian hooks sendiri"
            print(f"  [LEWAT] {hermes_cfg}: {alasan}. Potongan hook-nya ditulis ke Konfigurasi, gabungkan sendiri.")
            w.tulis(konf / "hermes-hooks.yaml", blok, timpa=True)
        w.tulis(WS / "9router" / "docker-compose.yml", (TEMPLAT / "9router" / "docker-compose.yml").read_text(encoding="utf-8"))
    if "zed" in platform:
        pola = [{"pattern": pola_zed(x)} for x in lindungi]
        alat = {t: {"always_deny": pola} for t in ("terminal", "edit_file", "write_file", "delete_path", "move_path", "copy_path", "create_directory")}
        contoh = {"file_scan_exclusions": ["**/.git", "**/node_modules", "**/*-venv", *[f"**/{x.name}/**" for x in lindungi]],
                  "agent": {"tool_permissions": {"tools": alat}}}
        tulis_json(w, konf / "zed-settings-contoh.json", contoh, "gabungkan sendiri ke settings.json Zed")

    print("\n# .env, skill")
    env = WS / ".env"
    if not env.exists():
        teks = (WS / ".env.example").read_text(encoding="utf-8")
        teks = re.sub(r"(?m)^(NINEROUTER_(?:JWT_SECRET|INITIAL_PASSWORD|API_KEY_SECRET))=<diisi-pasang\.py>$",
                      lambda m: f"{m.group(1)}={secrets.token_urlsafe(24)}", teks)
        w.tulis(env, teks, ket="tiga secret 9Router diisi acak")
    else:
        w.lapor("ADA", env, "dibiarkan")
    if (WS / "skills" / ".git").exists():
        print(f"  [LEWAT] {WS / 'skills'} adalah repo git sendiri, skill kit tidak disalin ke sana.")
    else:
        w.salin_folder(KIT / "skills", WS / "skills")

    # Registry aturan: satu sumber protokol dengan salinan per platform, cermin terjemahan, dan cadangan ke vault
    terjemahan = [{"source": posix(fk / "AGENTS.md"), "mirror": posix(fk / "AGENTS_id.md"), "note": "cermin Indonesia protokol"},
                  {"source": posix(WS / "AGENTS.md"), "mirror": posix(WS / "AGENTS_id.md"), "note": "cermin Indonesia aturan lengkap"},
                  {"source": posix(konf / "Operasi Vault.md"), "mirror": posix(konf / "Operasi Vault_id.md"), "note": "cermin Indonesia operasi vault"}]
    if "claude" in platform:
        terjemahan.append({"source": posix(WS / "AGENTS.md"), "section": "## Rule 13", "mirror": posix(home / ".claude" / "CLAUDE.md"),
                           "note": "cermin Indonesia Aturan 13 saja"})
    reg = {"about": "Registry aturan: satu sumber, banyak salinan, dipakai tools/sync_rules.py. Ditulis pasang.py. Path salinan di profil "
                    f"pengguna di sini diizinkan {nama} untuk ditulis agent, khusus untuk sinkronisasi aturan ({tanggal}).",
           "dipasang_oleh": "pasang.py", "vault": VP, "folder_kerja": FKP,
           "syncs": [{"name": "Protokol folder kerja", "source": posix(fk / "AGENTS.md"),
                      "copies": [{"path": posix(pth), "platform": pf} for pth, _, pf in salinan]}],
           "translations": terjemahan,
           "backup": {"note": "Cadangan otomatis setiap sinkronisasi ke folder vault, supaya ikut ke mana pun vault dicadangkan. "
                              "Konfigurasi agent disensor nilai rahasianya.",
                      "dir": posix(vault / "Cadangan Aturan"), "folders": [posix(konf)],
                      "files": sorted({posix(f) for f in cadangan_files}), "redact": sorted({posix(f) for f in redact}),
                      "exclude": ["penjaga_vault_terlarang.txt", "istilah_pribadi.txt"],
                      "readme": "# Cadangan Aturan\n\n> Salinan otomatis sumber aturan, terjemahannya, dan isi folder Konfigurasi workspace agent, "
                                "ditulis `tools/sync_rules.py` setiap kali aturan disinkronkan, supaya ikut ke mana pun vault dicadangkan.\n\n"
                                "Terkait dengan: [[Arsitektur AI]], [[Obsidian Workflow]]\n\n## Jangan disunting\n\n"
                                "- Ini cadangan, bukan aturan. Sumbernya tetap di path aslinya, dan susunan folder di sini mengikuti path itu.\n"
                                "- Perubahan aturan tetap lewat sumbernya dan `sync_rules.py` (protokol folder kerja, bagian Changing rules).\n"
                                "- Folder ini memuat `.no-vault`, jadi RAG melewatinya.\n\n## Memulihkan\n\n"
                                "Salin berkas dari sini kembali ke path aslinya, lalu jalankan `sync_rules.py --check`.\n"}}
    tulis_json(w, reg_path, reg)

    if a.uji_kering:
        print("\nUji kering: tidak ada yang ditulis, sinkronisasi, RAG, dan uji penjaga dilewati.")
        return 0
    masalah = []
    print("\n# Sinkronisasi aturan")
    stamp = [x for t in terjemahan for x in ("--stamp", t["mirror"])]
    jalan([sys.executable, WS / "tools" / "sync_rules.py", "--registry", reg_path, *stamp])
    if jalan([sys.executable, WS / "tools" / "sync_rules.py", "--registry", reg_path, "--check"]):
        masalah.append("sync_rules.py --check melaporkan masalah (lihat di atas)")

    if rag:
        print("\n# RAG")
        venv_py = WS / "tools" / "rag-venv" / "Scripts" / "python.exe"
        if not venv_py.exists() and jalan([py, "-m", "venv", WS / "tools" / "rag-venv"]):
            sys.exit("Gagal membuat venv RAG.")
        if jalan([venv_py, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", WS / "tools" / "requirements" / "rag-kit.txt"]):
            sys.exit("Gagal memasang paket RAG. Jalankan ulang pasang.py sesudah koneksi atau versi Python diperbaiki.")
        unduh_model(MODEL_DIR, a.model_dari)
        env_rag = {**os.environ, "AGENT_VAULT": str(vault)}
        if jalan([venv_py, WS / "tools" / "rag_engine.py", "index", vault], env=env_rag):
            masalah.append("indeks RAG gagal dibuat")

    print("\n# Uji penjaga terpasang")
    konfig = (["--claude-settings", home / ".claude" / "settings.json"] if "claude" in platform else []) \
        + (["--antigravity-hooks", home / ".gemini" / "config" / "hooks.json"] if ag_berhook else []) \
        + (["--hermes-config", hermes_cfg] if hermes_berhook else [])
    if konfig:
        if jalan([sys.executable, WS / "tools" / "uji_penjaga.py", "--vault", vault, "--projects-root", fk, *konfig]):
            masalah.append("uji_penjaga.py menemukan penjaga yang GAGAL")
    else:
        print("  Tidak ada hook yang terpasang untuk diuji.")

    print("\n# Selesai" + (" dengan masalah:" if masalah else ""))
    for m in masalah:
        print(f"  - {m}")
    print("Langkah berikutnya ada di README.md, bagian Sesudah memasang. Sesi agent yang sedang berjalan perlu dibuka ulang.")
    return 1 if masalah else 0


if __name__ == "__main__":
    sys.exit(main())
