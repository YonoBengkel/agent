"""Laporan harian terjadwal (rancangan 1 di log vault 073, dipasang 2026-11-21). Windows Task Scheduler menjalankan cek
yang sudah ada sekali sehari, lalu hasilnya ditulis ke satu berkas JSON lokal. Hook awal sesi workspace
(`session_context.py`) menampilkan satu baris kalau laporan terakhir memuat temuan atau sudah basi, jadi cek ini tidak
bergantung pada ingatan agent. Skrip ini tidak pernah commit, push, atau menulis vault.

  python tools/laporan_harian.py jalan --vault <vault> --words <daftar> --secrets-from <compose> --gitleaks <exe>
         --claude-settings <settings.json> --antigravity-hooks <hooks.json> --hermes-config <config.yaml> [--paksa]
  python tools/laporan_harian.py baris

Laporannya `Riwayat Perckapan/laporan-harian.json` (lokal, tidak masuk git). `jalan` dilewati kalau laporan hari ini
sudah ada, kecuali dengan --paksa. Canary tidak ikut, karena hook awal sesi sudah memperingatkan canary yang basi."""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAPORAN = os.path.join(AKAR, "Riwayat Perckapan", "laporan-harian.json")
TANPA_JENDELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # dari penjadwal lewat pythonw: jangan munculkan jendela konsol
INFO_LINT = ("Link ke halaman", "Link lewat alias", "Index RAG", "Log keputusan penjaga", "Tidak dicek", "hot.md")
TAG_ATURAN = re.compile(r"\[(PERIKSA|BEDA|GAGAL|CADANGAN BASI|CADANGAN DISUNTING|TERLALU BESAR)\]")

def jalan(perintah, batas=600):
    """(kode keluar, keluaran) satu cek. Gagal menjalankan dikembalikan sebagai kode None, bukan sebagai bersih."""
    try:
        r = subprocess.run(perintah, cwd=AKAR, capture_output=True, timeout=batas, creationflags=TANPA_JENDELA)
        return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"{type(e).__name__}: {e}"

def ringkas_lint(keluaran):
    """Bagian lint yang angkanya di atas nol, tanpa bagian yang hanya informasi. hot.md hanya kalau melewati batas."""
    temuan = [f"{judul} {angka}" for judul, angka in re.findall(r"(?m)^## (.+?) — (\d+)", keluaran)
              if int(angka) and not judul.startswith(INFO_LINT)]
    return temuan + [l[3:].strip() for l in keluaran.splitlines() if l.startswith("## hot.md") and "⚠" in l]

def nilai(kode, keluaran, temuan):
    if kode is None:
        return {"status": "gagal jalan", "rincian": [keluaran.strip()[-200:]]}
    return {"status": "temuan" if temuan else "ok", "rincian": [t[:160] for t in temuan[:10]]}

def cek_semua(a):
    py = [sys.executable.replace("pythonw.exe", "python.exe"), "-B"]
    hasil = {}
    k, o = jalan(py + ["tools/vault_lint.py", a.vault, "--secrets-from", a.secrets_from])
    hasil["lint vault"] = nilai(k, o, ringkas_lint(o))
    k, o = jalan(py + ["tools/cadangkan_vault.py", "--vault", a.vault, "--words", a.words, "--secrets-from",
                       a.secrets_from, "--gitleaks", a.gitleaks, "--cek"])
    hasil["pindai cadangan"] = nilai(k, o, [] if k == 0 else [l for l in o.splitlines() if l.strip()][-5:])
    k, o = jalan(py + ["tools/sync_rules.py", "--check"])
    hasil["salinan aturan"] = nilai(k, o, [] if k == 0 else
                                    [l.strip() for l in o.splitlines() if TAG_ATURAN.search(l)] or [f"kode keluar {k}"])
    k, o = jalan(py + ["tools/uji_penjaga.py", "--claude-settings", a.claude_settings, "--antigravity-hooks",
                       a.antigravity_hooks, "--hermes-config", a.hermes_config])
    hasil["penjaga terpasang"] = nilai(k, o, [] if k == 0 else
                                       [l.strip() for l in o.splitlines() if "GAGAL" in l] or [o.strip()[-160:]])
    k, o = jalan(py + ["tools/cek_proses_sisa.py", "--sejak", "24h"])
    hasil["proses sisa"] = nilai(k, o, [] if "Tidak ada proses" in o else [l.strip() for l in o.splitlines() if l.strip()])
    # Laporan anggaran token mingguan (log vault 078, Q20): ditulis hanya kalau jatuh tempo; isinya tampil lewat
    # ukur_token.baris di hook awal sesi workspace, jadi di sini hanya gagal atau tidaknya yang dinilai.
    k, o = jalan(py + ["tools/ukur_token.py", "laporan", "--simpan", os.path.dirname(LAPORAN), "--jatuh-tempo"], batas=900)
    hasil["anggaran token"] = nilai(k, o, [] if k == 0 else [l.strip() for l in o.splitlines() if l.strip()][-3:])
    return hasil

def tulis(hasil, path=LAPORAN):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"tanggal": datetime.date.today().isoformat(), "waktu": datetime.datetime.now().isoformat(timespec="seconds"),
            "cek": hasil}
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)

def baris(path=LAPORAN, hari_ini=None):
    """Satu baris untuk hook awal sesi, atau ''. Tidak pernah melempar galat, supaya sesi tetap mulai."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        tanggal = datetime.date.fromisoformat(data["tanggal"])
        masalah = [f"{nama} ({c['status']}: {'; '.join(c['rincian'][:3])})" for nama, c in data["cek"].items()
                   if c["status"] != "ok"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return ""
    if ((hari_ini or datetime.date.today()) - tanggal).days >= 2:
        return f"\n\n[Laporan harian] Laporan terakhir {tanggal}, jadi tugas terjadwalnya mungkin tidak jalan. Cek Task Scheduler."
    if not masalah:
        return ""
    return (f"\n\n[Laporan harian {tanggal}] {len(masalah)} cek bermasalah: " + ". ".join(masalah)
            + ". Rincian di Riwayat Perckapan/laporan-harian.json.")

def main():
    p = argparse.ArgumentParser(description="Laporan harian terjadwal: jalankan cek ekosistem dan tulis hasilnya ke JSON lokal.")
    sub = p.add_subparsers(dest="perintah", required=True)
    j = sub.add_parser("jalan", help="Jalankan semua cek dan tulis laporan hari ini")
    for nama in ("--vault", "--words", "--secrets-from", "--gitleaks", "--claude-settings", "--antigravity-hooks",
                 "--hermes-config"):
        j.add_argument(nama, required=True)
    j.add_argument("--paksa", action="store_true", help="Tetap jalan walau laporan hari ini sudah ada")
    sub.add_parser("baris", help="Cetak baris peringatan untuk hook awal sesi")
    a = p.parse_args()
    if a.perintah == "baris":
        print(baris().strip())
        return
    try:
        with open(LAPORAN, encoding="utf-8") as f:
            if json.load(f).get("tanggal") == datetime.date.today().isoformat() and not a.paksa:
                print("Laporan hari ini sudah ada.")
                return
    except (OSError, ValueError):
        pass
    tulis(cek_semua(a))
    print(baris().strip() or "Semua cek bersih.")

if __name__ == "__main__":
    main()
