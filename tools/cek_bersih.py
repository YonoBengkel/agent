"""Cek pembersih sebelum komit atau push repo workspace (dibuat 2026-11-22 untuk kit agent). Yang dipindai hanya berkas
yang bisa terbit: yang dilacak git ditambah berkas baru yang tidak diabaikan (`git ls-files -co --exclude-standard`).

Temuan per baris, juga pada path berkasnya sendiri:
- pola penjaga vault (`vault_guard.reasons`): angka 16 digit mirip NIK, assignment mirip secret, nilai secret yang dikenal
  dari --secrets-from, dan istilah dari --istilah (daftar lokal, satu per baris, tidak ikut komit)
- Unicode tak terlihat (`vault_guard.invisible`)
- email selain alamat noreply dan domain contoh
- path profil pengguna (C:\\Users\\<nama>, /c/Users/<nama>, /home/<nama>) dengan nama yang bukan placeholder atau contoh

Dengan --gitleaks, gitleaks ikut memindai salinan berkas yang sama (mode dir) dan seluruh riwayat git (mode git).
Temuan yang memang wajar dicatat di --izin sebagai `path | jenis | cuplikan | alasan`: temuan berjenis itu di baris
berkas itu yang memuat cuplikan dilewati. Untuk temuan gitleaks di riwayat, cuplikannya adalah fingerprint gitleaks.
Yang dicetak hanya path, nomor baris, dan jenis temuannya, tidak pernah isi barisnya, supaya keluaran cek ini sendiri
tidak membocorkan apa pun.

  python tools/cek_bersih.py [--istilah Konfigurasi/istilah_pribadi.txt] [--secrets-from .env]... [--gitleaks <exe>]
         [--izin kit/cek_bersih_izin.txt] [--akar <repo>]

Keluar 0 kalau bersih, 1 kalau ada temuan, 2 kalau cek tidak bisa jalan."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import vault_guard as g
from export_transcript import known_secrets

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JENIS = {"kata dari daftar terlarang (data pribadi)": "istilah", "angka 16 digit yang mirip NIK atau nomor KK": "nomor",
         "nilai secret yang dikenal": "secret", "assignment yang mirip secret": "secret"}
EMAIL = re.compile(r"(?<![\w.+%-])([A-Za-z0-9._+-]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})(?![\w-])")
DOMAIN_CONTOH = ("example.com", "example.org", "example.net")
AKHIRAN_CONTOH = (".example", ".test", ".invalid", ".localhost", "noreply.github.com")
# Path profil: nama tidak boleh memuat pemisah, kutip, atau tanda placeholder (<nama>, %USERNAME%, $USER, {{HOME}})
_NAMA = r"([^\\/\s\"'`<>|*?:;,()\[\]{}%$]+)"
PROFIL = [re.compile(r"(?i)(?:\b[a-z]:|(?<![\w.])/[a-z])[\\/]+users[\\/]+" + _NAMA),   # C:\Users\<nama>, C:/Users/<nama>, /c/Users/<nama>
          re.compile(r"(?<![\w:.])/Users/" + _NAMA),                                    # macOS
          re.compile(r"(?<![\w.])/home/" + _NAMA)]                                      # Linux
NAMA_CONTOH = {"public", "default", "default user", "all users", "user", "username", "nama", "you", "kamu", "contoh",
               "example", "budi", "runneradmin"}


def berkas_terbit(akar):
    """Path relatif (pemisah /) semua berkas yang bisa ikut komit."""
    out = subprocess.run(["git", "-C", akar, "ls-files", "-co", "--exclude-standard", "-z"],
                         capture_output=True, check=True).stdout.decode("utf-8")
    return sorted(p for p in out.split("\0") if p and os.path.isfile(os.path.join(akar, p)))


def baca_izin(path):
    """Entri izin: (path, jenis, cuplikan, alasan). Baris kosong dan baris berawalan # dilewati."""
    izin = []
    if not path or not os.path.exists(path):
        return izin
    with open(path, encoding="utf-8") as f:
        for n, baris in enumerate(f, 1):
            if not baris.strip() or baris.lstrip().startswith("#"):
                continue
            bagian = [b.strip() for b in baris.rstrip("\n").split(" | ")]
            if len(bagian) != 4 or not all(bagian):
                raise ValueError(f"{path}:{n}: format izin harus `path | jenis | cuplikan | alasan`")
            izin.append(tuple(bagian))
    return izin


def temuan_baris(teks, istilah, secrets):
    """Jenis temuan di satu baris teks, tanpa urutan ganda."""
    jenis = [JENIS.get(r, "pola") for r in g.reasons(teks, istilah, secrets)]
    if g.invisible(teks):
        jenis.append("unicode")
    for m in EMAIL.finditer(teks):
        lokal, domain = m.group(1).lower(), m.group(2).lower()
        if teks[m.end():m.end() + 1] == ":":   # git@github.com:pemilik/repo, alamat remote SSH
            continue
        if lokal in ("noreply", "no-reply") or domain in DOMAIN_CONTOH or domain.endswith(AKHIRAN_CONTOH):
            continue
        jenis.append("email")
    for pola in PROFIL:
        if any(m.group(1).lower() not in NAMA_CONTOH for m in pola.finditer(teks)):
            jenis.append("profil")
            break
    return list(dict.fromkeys(jenis))


def diizinkan(izin, path, jenis, teks, terpakai):
    for i, (p, j, cuplikan, _) in enumerate(izin):
        if p == path and j == jenis and cuplikan in teks:
            terpakai.add(i)
            return True
    return False


def pindai(akar, berkas, istilah, secrets, izin, terpakai):
    """Daftar (path, baris, jenis) yang tidak diizinkan. Baris 0 berarti path berkasnya sendiri."""
    hasil = []
    for rel in berkas:
        for jenis in temuan_baris(rel, istilah, secrets):
            if not diizinkan(izin, rel, jenis, rel, terpakai):
                hasil.append((rel, 0, jenis))
        with open(os.path.join(akar, rel), "rb") as f:
            data = f.read()
        if b"\0" in data:
            continue   # biner: gitleaks yang memindainya
        teks = data.decode("utf-8", "replace")
        for n, baris in enumerate(teks.splitlines(), 1):
            for jenis in temuan_baris(baris, istilah, secrets):
                if not diizinkan(izin, rel, jenis, baris, terpakai):
                    hasil.append((rel, n, jenis))
    return hasil


def gitleaks(exe, akar, berkas, izin, terpakai):
    """Temuan gitleaks atas salinan berkas yang bisa terbit (mode dir) dan atas seluruh riwayat git (mode git)."""
    hasil = []
    # Salinan sementara di drive repo, di folder yang diabaikan git, bukan di %TEMP% profil pengguna
    tmp = tempfile.mkdtemp(prefix=".cek_bersih-", dir=os.path.join(akar if os.path.isdir(os.path.join(akar, "tools")) else AKAR, "tools"))
    try:
        salinan = os.path.join(tmp, "berkas")
        for rel in berkas:
            dst = os.path.join(salinan, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(akar, rel), dst)
        for mode, sasaran in (("dir", salinan), ("git", akar)):
            laporan = os.path.join(tmp, f"{mode}.json")
            r = subprocess.run([exe, mode, sasaran, "--no-banner", "--redact", "--exit-code", "1",
                                "--report-format", "json", "--report-path", laporan], capture_output=True)
            if r.returncode not in (0, 1) or not os.path.exists(laporan):
                raise RuntimeError(f"gitleaks {mode} gagal (kode {r.returncode})")
            for f in json.load(open(laporan, encoding="utf-8")) or []:
                # Hanya aturan, berkas, baris, dan komit yang dipakai. Nama dan email pembuat komit tidak pernah dicetak.
                rel = os.path.relpath(f["File"], salinan).replace("\\", "/") if mode == "dir" else f["File"].replace("\\", "/")
                jenis = f"gitleaks:{f['RuleID']}"
                if mode == "dir":
                    isi = open(os.path.join(salinan, rel), encoding="utf-8", errors="replace").read().splitlines()
                    baris = isi[f["StartLine"] - 1] if 0 < f["StartLine"] <= len(isi) else ""
                    if not diizinkan(izin, rel, jenis, baris, terpakai):
                        hasil.append((rel, f["StartLine"], jenis))
                elif not diizinkan(izin, rel, jenis, f.get("Fingerprint", ""), terpakai):
                    # Fingerprint gitleaks berisi komit:berkas:aturan:baris, tanpa nilainya, jadi aman dicetak untuk daftar izin
                    hasil.append((rel, f["StartLine"], f"{jenis} di riwayat, fingerprint {f.get('Fingerprint', '')}"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return hasil


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Cek pembersih sebelum komit atau push: secret, nomor identitas, email, path "
                                            "profil pengguna, Unicode tak terlihat, dan istilah pribadi dari daftar lokal.")
    p.add_argument("--akar", default=AKAR, help="Folder repo yang dipindai (bawaan: workspace ini)")
    p.add_argument("--istilah", action="append", default=[],
                   help="Daftar istilah pribadi lokal, satu per baris, tidak ikut komit (boleh diulang), "
                        "misalnya Konfigurasi/istilah_pribadi.txt")
    p.add_argument("--secrets-from", action="append", default=[], help="Berkas yang nilai secret-nya ikut dicari, mis. .env (boleh diulang)")
    p.add_argument("--gitleaks", help="Path gitleaks.exe: ikut pindai salinan berkas (mode dir) dan seluruh riwayat git")
    p.add_argument("--izin", help="Daftar temuan yang diizinkan (bawaan: kit/cek_bersih_izin.txt di --akar)")
    a = p.parse_args()

    try:
        akar = os.path.abspath(a.akar)
        izin = baca_izin(a.izin or os.path.join(akar, "kit", "cek_bersih_izin.txt"))
        istilah = [w for path in a.istilah for w in g.banned_words(path)]
        berkas = berkas_terbit(akar)
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        print(f"[GALAT] {e}")
        return 2
    nilai_rahasia = known_secrets(a.secrets_from)
    if not a.istilah:
        print("[PERINGATAN] Tanpa --istilah: nama dan istilah pribadi tidak dicari.")
    terpakai = set()
    hasil = pindai(akar, berkas, istilah, nilai_rahasia, izin, terpakai)
    if a.gitleaks:
        try:
            hasil += gitleaks(a.gitleaks, akar, berkas, izin, terpakai)
        except (OSError, RuntimeError, ValueError, KeyError) as e:
            print(f"[GALAT] {e}")
            return 2
    for rel, n, jenis in hasil:
        print(f"[TEMUAN] {rel}:{n}: {jenis}")
    basi = [izin[i] for i in range(len(izin)) if i not in terpakai and (a.gitleaks or not izin[i][1].startswith("gitleaks"))]
    for p_, j, _, alasan in basi:
        print(f"[IZIN BASI] {p_} | {j}: tidak ada temuan yang cocok lagi ({alasan}). Hapus dari daftar izin.")
    print(f"{len(berkas)} berkas dipindai{', gitleaks dir dan git' if a.gitleaks else ''}, {len(istilah)} istilah, "
          f"{len(nilai_rahasia)} nilai secret dikenal: {len(hasil)} temuan.")
    return 1 if hasil else 0


if __name__ == "__main__":
    sys.exit(main())
