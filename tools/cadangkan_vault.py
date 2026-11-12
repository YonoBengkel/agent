"""Cadangkan vault memori ke repo git privatnya (sejak 2026-11-11, pilihan pengguna sesudah ternyata vault tidak
punya cadangan di luar mesin).

Sebelum apa pun dikirim, semua berkas teks di vault dipindai dengan pola penjaga vault: nilai secret dari
`--secrets-from`, kata terlarang dari `--words`, dan angka mirip nomor identitas. Kalau ada temuan, tidak ada yang
di-commit atau di-push, dan yang dicetak hanya nama berkas dan jenis temuannya, tidak pernah isinya. Lint vault
hanya membaca `.md`, padahal cadangan konfigurasi di vault berupa JSON dan YAML, jadi pemindaian ini mencakup
semuanya. Folder `.git` dan `.obsidian` dilewati: yang kedua hanya pengaturan aplikasi, dan angka pengaturan
grafiknya mirip nomor identitas.

Dijalankan di langkah terakhir Kompilasi (Konfigurasi/Operasi Vault.md).

Pakai: python tools/cadangkan_vault.py --vault "<vault>" --words <daftar kata> --secrets-from <berkas> [--cek]
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vault_guard  # pola yang sama dengan hook penjaga vault

LEWATI = {".git", ".obsidian"}
SECRET = re.compile(r"(?i)[A-Z0-9_]*(?:SECRET|PASSWORD|TOKEN|API_KEY)[A-Z0-9_]*\s*[=:]\s*([^\s\"']+)")   # sama dengan vault_lint.py

def nilai_secret(paths):
    hasil = set()
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                hasil.update(v for v in SECRET.findall(f.read()) if len(v) >= 6)
        except OSError:
            pass
    return hasil

def pindai(vault, banned, secrets):
    """[(path relatif, [alasan])] untuk berkas yang tidak boleh ikut dikirim."""
    temuan = []
    for dp, dn, fn in os.walk(vault):
        dn[:] = [d for d in dn if d not in LEWATI]
        for f in fn:
            p = os.path.join(dp, f)
            try:
                with open(p, encoding="utf-8", errors="replace") as h:
                    isi = h.read()
            except OSError:
                continue
            alasan = vault_guard.reasons(isi, banned, [])
            if any(v in isi for v in secrets):
                alasan.append("nilai secret dari --secrets-from")
            if alasan:
                temuan.append((os.path.relpath(p, vault), alasan))
    return temuan

def git(vault, *args):
    r = subprocess.run(["git", "-C", vault, *args], capture_output=True, timeout=300)
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace").strip()

def main():
    p = argparse.ArgumentParser(description="Pindai vault, lalu commit dan push ke repo git privatnya kalau bersih.")
    p.add_argument("--vault", required=True, help="Folder vault yang sudah menjadi repo git")
    p.add_argument("--words", help="Daftar kata terlarang (lokal, tidak pernah ikut dikirim)")
    p.add_argument("--secrets-from", action="append", default=[], help="Berkas berisi nilai secret yang tidak boleh ada di vault")
    p.add_argument("--cek", action="store_true", help="Hanya pindai dan hitung perubahan, tanpa commit atau push")
    a = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not os.path.isdir(os.path.join(a.vault, ".git")):
        sys.exit(f"{a.vault} belum menjadi repo git. Jalankan `git init` di sana dulu.")
    temuan = pindai(a.vault, vault_guard.banned_words(a.words), nilai_secret(a.secrets_from))
    for rel, alasan in temuan:
        print(f"DITAHAN {rel}: {', '.join(alasan)}")
    if temuan:
        sys.exit(f"{len(temuan)} berkas memuat teks yang tidak boleh keluar mesin. Tidak ada yang di-commit atau di-push.")
    git(a.vault, "add", "-A")
    _, status = git(a.vault, "status", "--porcelain")
    ubah = len([l for l in status.splitlines() if l.strip()])
    if a.cek:
        print(f"Pindaian bersih. {ubah} berkas akan masuk cadangan berikutnya.")
        return
    if ubah:
        k, out = git(a.vault, "commit", "-q", "-m", f"cadangan vault {datetime.datetime.now():%Y-%m-%d %H:%M}")
        if k:
            sys.exit(f"commit gagal: {out}")
    k, remote = git(a.vault, "remote")
    if not remote:
        print(f"{ubah} berkas di-commit lokal. Belum ada remote, jadi belum di-push.")
        return
    k, out = git(a.vault, "push", "-q", "origin", "HEAD")
    if k:
        sys.exit(f"push gagal: {out}")
    print(f"Cadangan terkirim: {ubah} berkas berubah.")

if __name__ == "__main__":
    main()
