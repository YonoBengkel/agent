"""Oper tugas kecil ke agent gratis, supaya agent mahal cukup merencanakan dan memeriksa (skill oper-kerja).
Agent bekerja di git worktree terpisah, jadi folder kerja utama dan berkas yang tidak dilacak git (.env, data) tidak ikut.
Agent hanya punya alat baca dan sunting berkas: tanpa shell, tanpa web, dan keduanya dikunci ke worktree. Bukti diambil dari git dan
--cek, bukan dari laporan agent. Hasilnya JSON ringkas di stdout. --cek menjalankan kode buatan agent tanpa pagar apa pun, jadi jalan
hanya lewat perintah cek, sesudah perubahan.patch dibaca.
Hermes memakai profil sendiri. Semua profil dilayani satu gateway yang tidak membaca env klien, jadi HERMES_WRITE_SAFE_ROOT tidak bisa dipakai
per tugas. Yang mengunci baca dan tulis ke folder sesi adalah hook vault_guard.py --worker di profil itu, dan jejaknya wajib ada di folder tugas.

  jalan     --repo R --tugas T [--agen opencode,hermes] [--cek "..."] [--boleh "pola"] [--batas 600]
  cek ID [--tanpa-uji]    kumpulkan ulang bukti dan jalankan --cek. Agent manual di Zed atau Antigravity: --tanpa-uji dulu, baca patch-nya
  terapkan ID    pasang patch ke folder kerja utama, tanpa komit
  buang ID       hapus worktree. Tugas, log, dan patch tetap ada di folder kerja oper

Batas: hanya menolak secret yang dikenal dan nomor identitas di tugas. Isi repo yang dilacak git terkirim ke penyedia model."""
import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from export_transcript import known_secrets  # satu definisi secret untuk semua tool (Aturan 6)
from vault_guard import WORKER_CLOSED, reasons

KONTRAK = """Kamu pekerja untuk satu tugas kecil di folder ini. Aturannya:
- Kamu hanya punya alat baca dan sunting berkas. Uji dijalankan alat lain sesudah kamu selesai, jadi jangan mengklaim lulus.
- Hanya baca dan ubah berkas di dalam folder kerja ini. Jangan membuka path di luar folder ini.
- Ubah hanya yang diminta. Jangan merapikan kode di sekitarnya, dan jangan mengubah tes kecuali diminta.
- Kalau tugasnya kurang jelas atau butuh keputusan, jangan menebak. Berhenti dan tulis PERTANYAAN: lalu pertanyaannya.
- Akhiri dengan ringkasan pendek: berkas yang berubah dan yang belum selesai.

TUGAS:
"""
MODEL_OPENCODE = "opencode/deepseek-v4.1-flash-free"  # model gratis tanpa penyimpanan data menurut dokumen OpenCode Zen
TOOLSET_HERMES = "file"  # tanpa terminal
PROFIL_HERMES = "pekerja"  # dibuat dengan: hermes profile create pekerja --clone --no-alias, lalu lihat skill oper-kerja
KUOTA = re.compile(r"429|FreeUsageLimit|rate.?limit|RESOURCE_EXHAUSTED|quota|usage limit|413", re.I)
SEHAT_9ROUTER = "http://localhost:20128/api/health"
ENV_DIBUANG = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")  # kunci agent mahal tidak perlu ikut


def git(cwd, *args, cek=True, input_=None):
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, input=input_)
    if cek and r.returncode:
        raise SystemExit(f"git {' '.join(args)} gagal: {r.stderr.decode('utf-8', 'replace')[:300]}")
    return r.stdout.decode("utf-8", "replace")


def tolak_tugas(teks, secrets):
    """Alasan menolak isi tugas: nomor identitas, secret yang dikenal, atau bentuk assignment secret."""
    return reasons(teks, [], secrets)


def baca_hermes(baris):
    """Baris terakhir stream-json Hermes: type result dengan text, tokens, duration_ms, exit_code."""
    akhir = {}
    for l in baris:
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if e.get("type") == "result":
            akhir = e
    return {"teks": (akhir.get("text") or "").strip(), "token": akhir.get("tokens"), "kode": akhir.get("exit_code")}


def baca_opencode(baris):
    """Kejadian JSON opencode run: text per bagian, step_finish membawa token, error membawa alasan gagal."""
    teks, token, galat = [], {"input": 0, "output": 0, "cache": 0}, []
    for l in baris:
        try:
            e = json.loads(l)
        except ValueError:
            continue
        p = e.get("part") or {}
        if e.get("type") == "text" and p.get("text"):
            teks.append(p["text"])
        elif e.get("type") == "step_finish":
            t = p.get("tokens") or {}
            token["input"] += t.get("input") or 0
            token["output"] += t.get("output") or 0
            token["cache"] += (t.get("cache") or {}).get("read") or 0
        elif e.get("type") == "error":
            galat.append(json.dumps(e.get("error"), ensure_ascii=False)[:300])
    return {"teks": "\n".join(teks).strip(), "token": token, "kode": 1 if galat else 0, "galat": galat}


def di_luar_izin(berkas, pola):
    """Berkas berubah yang tidak cocok dengan pola --boleh. Tanpa pola, semua dianggap boleh."""
    return [b for b in berkas if pola and not any(fnmatch.fnmatch(b.replace("\\", "/"), p) for p in pola)]


def env_agen(**tambah):
    env = {k: v for k, v in os.environ.items() if k not in ENV_DIBUANG}
    env.update(tambah)
    return env


def izin_opencode():
    """Tolak semua kecuali baca dan sunting di worktree. Tanpa --auto, izin yang tidak tertulis di sini otomatis ditolak."""
    tutup = {p: "deny" for p in WORKER_CLOSED}
    return {"*": "deny", "read": {"*": "allow", **tutup}, "edit": {"*": "allow", **tutup}, "glob": "allow", "grep": "allow",
            "list": "allow", "external_directory": "deny"}


def perintah_opencode(kerja, model):
    konfig = {"permission": izin_opencode(), "snapshot": False, "autoupdate": False, "share": "disabled"}
    return ([shutil.which("opencode") or "opencode", "run", "--format", "json", "--pure", "--dir", str(kerja),
             "-m", model or MODEL_OPENCODE],
            env_agen(OPENCODE_CONFIG_CONTENT=json.dumps(konfig), OPENCODE_DISABLE_CLAUDE_CODE="1"), baca_opencode)  # aturan pribadi di ~/.claude tidak ikut terkirim


def home_pekerja():
    return os.path.join(os.environ.get("HERMES_HOME", ""), "profiles", PROFIL_HERMES)


def perintah_hermes(kerja, model, berkas_kueri):
    p = [shutil.which("hermes") or "hermes", "-p", PROFIL_HERMES, "chat", "--query-file", str(berkas_kueri), "--oneshot", "--ignore-rules",
         "-t", TOOLSET_HERMES, "--in", str(kerja), "--format", "stream-json"]
    env = env_agen(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return (p + (["-m", model] if model else []), env, baca_hermes)


def penjaga_hermes_aktif(home):
    """Hook yang belum disetujui dilewati diam-diam oleh Hermes (Pelajaran #61), jadi persetujuannya dicek sebelum dipakai.
    Hook tanpa --worker hanya menjaga vault dan tidak mengunci pekerja ke foldernya."""
    try:
        with open(os.path.join(home, "shell-hooks-allowlist.json"), encoding="utf-8") as f:
            izin = json.load(f).get("approvals") or []
        with open(os.path.join(home, "config.yaml"), encoding="utf-8") as f:
            konfig = f.read()
    except (OSError, ValueError):
        return False
    return any(a.get("event") == "pre_tool_call" and "vault_guard.py" in a.get("command", "") and "--worker" in a["command"] and a["command"] in konfig for a in izin)


def hentikan(proses):
    """Timeout: hentikan seluruh pohon proses, karena agent menjalankan anak proses sendiri."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proses.pid), "/T", "/F"], capture_output=True)
    else:
        proses.kill()


def jalankan_agen(agen, kerja, folder, kueri, model, batas):
    """Jalankan satu agent. Hasilnya berisi teks akhir, token, kode keluar, dan lama jalan."""
    log = folder / f"{agen}.jsonl"
    if agen == "hermes":
        try:
            urllib.request.urlopen(SEHAT_9ROUTER, timeout=3)
        except Exception:
            return {"agen": agen, "dilewati": "9Router tidak menyala, jadi Hermes tidak punya model"}
        if not penjaga_hermes_aktif(home_pekerja()):
            return {"agen": agen, "dilewati": f"hook vault_guard.py --worker di profil {PROFIL_HERMES} belum ada atau belum disetujui. Lihat skill oper-kerja"}
        berkas = folder / "kueri.txt"
        berkas.write_text(kueri, encoding="utf-8")
        perintah, env, baca = perintah_hermes(kerja, model, berkas)
        masukan = None
    elif agen == "opencode":
        perintah, env, baca = perintah_opencode(kerja, model)
        masukan = kueri.encode("utf-8")
    else:
        return {"agen": agen, "dilewati": "agent tidak dikenal"}
    mulai = time.time()
    with open(log, "wb") as keluar:
        proses = subprocess.Popen(perintah, stdin=subprocess.PIPE, stdout=keluar, stderr=subprocess.STDOUT, cwd=kerja, env=env)
        try:
            proses.communicate(masukan, timeout=batas)
            kode = proses.returncode
        except subprocess.TimeoutExpired:
            hentikan(proses)
            proses.wait()
            kode = "batas waktu"
    isi = log.read_text(encoding="utf-8", errors="replace")
    hasil = baca(isi.splitlines())
    if agen == "hermes" and not kode and not (folder / "pagar-aktif").exists():
        kode = "pagar tidak terbukti"  # hook yang tidak jalan itu diam (Pelajaran #61), jadi hasil tanpa buktinya tidak dipakai
    return {"agen": agen, "kode_keluar": kode, "detik": round(time.time() - mulai), "token": hasil.get("token"),
            "teks": hasil["teks"], "kuota": bool(KUOTA.search(isi)) and not hasil["teks"], "galat": hasil.get("galat") or None}


def pastikan_git_utuh(kerja, meta):
    """Berkas .git ada di dalam worktree, jadi agent bisa menggantinya. Git di folder itu lalu membaca konfigurasi pilihan agent,
    dan core.fsmonitor di sana menjalankan perintah. Jadi diperiksa sebelum git dijalankan di worktree."""
    try:
        utuh = (kerja / ".git").read_text(encoding="utf-8") == meta["git_berkas"]
    except OSError:
        utuh = False
    if not utuh:
        raise SystemExit(f"Ditolak: berkas .git di {kerja} berubah sesudah agent jalan. Git tidak dijalankan di folder itu. Periksa isinya dengan tangan.")


def bukti(folder, meta, uji=False):
    """Bukti dari git: berkas berubah, patch, dan folder utama tersentuh atau tidak. uji=True menjalankan --cek."""
    kerja, repo = folder / "kerja", meta["repo"]
    pastikan_git_utuh(kerja, meta)
    git(kerja, "add", "-A")
    berkas = [l for l in git(kerja, "diff", "--cached", "--name-only", meta["basis"]).splitlines() if l]
    (folder / "perubahan.patch").write_bytes(subprocess.run(["git", "-C", str(kerja), "diff", "--cached", "--binary", meta["basis"]],
                                                            capture_output=True).stdout)
    hasil = {"berkas": berkas, "stat": git(kerja, "diff", "--cached", "--shortstat", meta["basis"]).strip(),
             "di_luar_izin": di_luar_izin(berkas, meta.get("boleh") or []),
             "komit_agen": int(git(kerja, "rev-list", "--count", f"{meta['basis']}..HEAD").strip() or 0),
             "folder_utama_berubah": (git(repo, "status", "--porcelain"), git(repo, "rev-parse", "HEAD").strip()) != tuple(meta["utama"])}
    if uji and meta.get("cek"):
        try:
            r = subprocess.run(meta["cek"], shell=True, cwd=kerja, capture_output=True, timeout=300, env=env_agen())
            keluaran = (r.stdout + r.stderr).decode("utf-8", "replace").strip().splitlines()
            hasil["cek"] = {"perintah": meta["cek"], "kode_keluar": r.returncode, "akhir": keluaran[-8:]}
        except subprocess.TimeoutExpired:
            hasil["cek"] = {"perintah": meta["cek"], "kode_keluar": "batas waktu"}
    return hasil


def simpan(folder, meta, hasil):
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    keluaran = {"id": folder.name, "folder": str(folder), **hasil}
    (folder / "hasil.json").write_text(json.dumps(keluaran, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(keluaran, ensure_ascii=False))


def muat(akar, id_):
    import pathlib
    folder = pathlib.Path(akar) / id_
    if not (folder / "meta.json").exists():
        raise SystemExit(f"Oper {id_} tidak ditemukan di {akar}")
    return folder, json.loads((folder / "meta.json").read_text(encoding="utf-8"))


def akar_bawaan(repo):
    return os.path.join(os.path.splitdrive(os.path.abspath(repo))[0] + os.sep, "OperKerja")


def jalan(a):
    import pathlib
    repo = git(a.repo, "rev-parse", "--show-toplevel").strip()
    if os.path.exists(os.path.join(repo, ".no-vault")):
        raise SystemExit("Ditolak: repo ini memakai .no-vault, jadi isinya tidak dikirim ke model gratis.")
    tugas = pathlib.Path(a.tugas).read_text(encoding="utf-8-sig")
    secrets = known_secrets(a.secrets_from)
    alasan = tolak_tugas(tugas, secrets)
    if alasan:
        raise SystemExit(f"Ditolak: tugas memuat {', '.join(alasan)}. Tugas ini terkirim ke penyedia model gratis.")
    if secrets and subprocess.run(["git", "-C", repo, "grep", "-q", "-F", *[x for s in secrets for x in ("-e", s)], "HEAD"]).returncode == 0:
        raise SystemExit("Ditolak: berkas terlacak di repo ini memuat secret yang dikenal.")
    akar = pathlib.Path(a.akar or akar_bawaan(repo))
    id_ = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    folder = akar / id_
    folder.mkdir(parents=True)
    (folder / "tugas.md").write_text(KONTRAK + tugas, encoding="utf-8")
    basis = git(repo, "rev-parse", "HEAD").strip()
    git(repo, "worktree", "add", "--detach", "-q", str(folder / "kerja"), basis)
    meta = {"repo": repo, "basis": basis, "cek": a.cek, "boleh": a.boleh, "utama": [git(repo, "status", "--porcelain"), basis],
            "git_berkas": (folder / "kerja" / ".git").read_text(encoding="utf-8")}
    agen = [x.strip() for x in a.agen.split(",") if x.strip()]
    if agen == ["manual"]:
        simpan(folder, meta, {"status": "menunggu", "buka_folder": str(folder / "kerja"), "berkas_tugas": str(folder / "tugas.md"),
                              "langkah": "Tempel isi berkas tugas ke agent di Zed atau Antigravity, lalu jalankan: cek ID --tanpa-uji"})
        return
    riwayat = []
    for nama in agen:
        h = jalankan_agen(nama, folder / "kerja", folder, KONTRAK + tugas, a.model, a.batas)
        ringkas = {k: v for k, v in h.items() if k != "teks"}
        riwayat.append(ringkas)
        if h.get("dilewati") or h.get("kuota") or h.get("kode_keluar") or not h.get("teks"):
            pastikan_git_utuh(folder / "kerja", meta)
            git(folder / "kerja", "reset", "-q", "--hard", basis)  # sisa percobaan gagal tidak ikut ke agent berikutnya
            git(folder / "kerja", "clean", "-fdq")
            continue
        simpan(folder, meta, {"status": "selesai", "agen": nama, "percobaan": riwayat, "laporan_agen": h["teks"][-1500:], **bukti(folder, meta),
                              "langkah": "Baca perubahan.patch. Kalau aman, jalankan: cek ID"})
        return
    simpan(folder, meta, {"status": "gagal", "percobaan": riwayat})
    sys.exit(1)


def cek(a):
    folder, meta = muat(a.akar, a.id)
    simpan(folder, meta, {"status": "dicek", **bukti(folder, meta, uji=not a.tanpa_uji)})


def terapkan(a):
    folder, meta = muat(a.akar, a.id)
    patch = folder / "perubahan.patch"
    if not patch.exists() or not patch.stat().st_size:
        raise SystemExit("Tidak ada perubahan untuk diterapkan.")
    r = subprocess.run(["git", "-C", meta["repo"], "apply", "--3way", str(patch)], capture_output=True)
    if r.returncode:
        raise SystemExit(f"Patch gagal diterapkan: {r.stderr.decode('utf-8', 'replace')[:400]}")
    git(meta["repo"], "reset", "-q")  # hasilnya perubahan biasa, belum di-stage
    print(git(meta["repo"], "status", "--short"))


def buang(a):
    folder, meta = muat(a.akar, a.id)
    git(meta["repo"], "worktree", "remove", "--force", str(folder / "kerja"))
    print(f"Worktree {a.id} dihapus. Tugas, log, dan patch tetap di {folder}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Oper tugas kecil ke agent gratis di git worktree terpisah.")
    sub = p.add_subparsers(dest="aksi", required=True)
    j = sub.add_parser("jalan", help="Buat worktree, jalankan agent, kumpulkan bukti")
    j.add_argument("--repo", required=True)
    j.add_argument("--tugas", required=True, help="Berkas teks berisi tugas")
    j.add_argument("--agen", default="opencode,hermes", help="Urutan agent: opencode, hermes, atau manual. Yang gagal kuota digantikan berikutnya")
    j.add_argument("--model", help="Model untuk agent, kalau tidak memakai bawaannya")
    j.add_argument("--cek", help="Perintah uji untuk perintah cek. Menjalankan kode buatan agent, jadi tidak otomatis")
    j.add_argument("--boleh", action="append", default=[], help="Pola berkas yang boleh berubah (boleh diulang)")
    j.add_argument("--batas", type=int, default=600, help="Batas detik per agent")
    j.add_argument("--akar", help="Folder kerja oper. Bawaan: <drive repo>/OperKerja")
    j.add_argument("--secrets-from", action="append", default=[], help="Berkas konfigurasi yang nilai secret-nya ikut ditolak (boleh diulang)")
    j.set_defaults(fungsi=jalan)
    for nama, fungsi in (("cek", cek), ("terapkan", terapkan), ("buang", buang)):
        s = sub.add_parser(nama)
        s.add_argument("id")
        s.add_argument("--akar", default=os.path.join(os.path.splitdrive(os.getcwd())[0] + os.sep, "OperKerja"))
        if nama == "cek":
            s.add_argument("--tanpa-uji", action="store_true", help="Kumpulkan bukti tanpa menjalankan --cek")
        s.set_defaults(fungsi=fungsi)
    a = p.parse_args()
    a.fungsi(a)


if __name__ == "__main__":
    main()
