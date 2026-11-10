"""Putar log wiki per bulan (Aturan 4, sejak 2026-11-10).

Entri `## [YYYY-MM-DD] ...` dari bulan sebelum bulan berjalan di Wiki/log.md dan Wiki/log_id.md dipindah ke
Riwayat/log <YYYY-MM>.md dan Riwayat/log_id <YYYY-MM>.md di vault, supaya berkas log yang dibaca agent tetap kecil.
Kepala log tidak diubah. Aman dijalankan berulang: entri yang sudah ada di berkas riwayat tidak ditulis dua kali.
Dijalankan di langkah 1 Kompilasi (Konfigurasi/Operasi Vault.md).

Pakai: python tools/putar_log.py --vault "<vault>" [--cek] [--bulan YYYY-MM]
"""
import argparse
import datetime
import os
import re
import sys

ENTRI = re.compile(r"(?m)^## \[(\d{4})-(\d{2})-\d{2}\]")
KEPALA = {
    "log": ("Wiki Log", "Wiki operations of {b}, moved out of [[log]] by `tools/putar_log.py`. Entries of the current month stay in that file.",
            "Related: [[log]], [[Obsidian Workflow]]"),
    "log_id": ("Log Wiki", "Operasi wiki bulan {b}, dipindah dari [[log_id]] oleh `tools/putar_log.py`. Entri bulan berjalan tetap di berkas itu.",
               "Terkait dengan: [[log_id]], [[Obsidian Workflow]]"),
}

def pecah(teks):
    """(kepala, [(YYYY-MM, teks entri)]). Teks entri berlanjut sampai entri berikutnya."""
    awal = [m.start() for m in ENTRI.finditer(teks)]
    if not awal:
        return teks, []
    entri = []
    for a, b in zip(awal, awal[1:] + [len(teks)]):
        m = ENTRI.match(teks, a)
        entri.append((f"{m.group(1)}-{m.group(2)}", teks[a:b]))
    return teks[:awal[0]], entri

def segarkan_kepala(kepala, vault, nama):
    """Baris kepala yang menyebut putar_log.py diakhiri daftar tautan ke semua berkas riwayatnya."""
    d = os.path.join(vault, "Riwayat")
    pola = re.compile(rf"{re.escape(nama)} (\d{{4}}-\d{{2}})\.md$")
    bulan = sorted(m.group(1) for f in (os.listdir(d) if os.path.isdir(d) else []) if (m := pola.match(f)))
    baris = kepala.splitlines(keepends=True)
    for i, l in enumerate(baris):
        if "putar_log.py" in l and ": " in l[l.index("putar_log.py"):]:
            akhir = l[len(l.rstrip("\r\n")):]
            j = l.index(": ", l.index("putar_log.py")) + 2
            baris[i] = l[:j] + ", ".join(f"[[{nama} {b}]]" for b in bulan) + "." + akhir
            break
    return "".join(baris)

def tulis_atomik(path, isi):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:   # UTF-8 tanpa BOM, akhir baris apa adanya
        f.write(isi)
    os.replace(tmp, path)

def putar(vault, nama, bulan_ini, tulis=True):
    """Pindahkan entri bulan lama dari Wiki/<nama>.md. Kembalikan {bulan: jumlah entri yang dipindah}."""
    path = os.path.join(vault, "Wiki", nama + ".md")
    with open(path, encoding="utf-8", newline="") as f:
        teks = f.read()
    kepala, entri = pecah(teks)
    lama = [(b, e) for b, e in entri if b < bulan_ini]
    if not lama:
        return {}
    nl = "\r\n" if "\r\n" in teks else "\n"
    per_bulan = {}
    for b, e in lama:
        per_bulan.setdefault(b, []).append(e)
    hasil = {}
    for b, es in sorted(per_bulan.items()):
        dest = os.path.join(vault, "Riwayat", f"{nama} {b}.md")
        if os.path.exists(dest):
            with open(dest, encoding="utf-8", newline="") as f:
                ada = f.read()
        else:
            judul, tujuan, kait = KEPALA[nama]
            ada = f"# {judul} {b}{nl}{nl}> {tujuan.format(b=b)}{nl}{nl}{kait}{nl}{nl}---{nl}{nl}"
        baru = [e for e in es if e.strip() not in ada]
        hasil[b] = len(es)
        if tulis and baru:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            isi = ada if ada.endswith(nl + nl) else ada.rstrip() + nl + nl
            tulis_atomik(dest, isi + "".join(e.rstrip() + nl + nl for e in baru).rstrip() + nl)
    if tulis:   # berkas riwayat ditulis dulu, baru log-nya dipangkas
        sisa = "".join(e for b, e in entri if b >= bulan_ini)
        tulis_atomik(path, (segarkan_kepala(kepala, vault, nama) + sisa).rstrip() + nl)
    return hasil

def main():
    p = argparse.ArgumentParser(description="Pindahkan entri bulan lalu dari Wiki/log.md dan log_id.md ke folder Riwayat/ di vault.")
    p.add_argument("--vault", required=True, help="Folder vault memori, tempat Wiki/log.md")
    p.add_argument("--bulan", default=datetime.date.today().strftime("%Y-%m"), help="Bulan berjalan YYYY-MM (bawaan: hari ini)")
    p.add_argument("--cek", action="store_true", help="Hanya laporkan, tanpa menulis. Keluar 1 kalau ada yang perlu diputar")
    a = p.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}", a.bulan):
        p.error("--bulan harus YYYY-MM")
    ada = False
    for nama in ("log", "log_id"):
        hasil = putar(a.vault, nama, a.bulan, tulis=not a.cek)
        for b, n in hasil.items():
            ada = True
            print(f"{nama}.md: {n} entri {b} {'perlu dipindah' if a.cek else 'dipindah'} ke Riwayat/{nama} {b}.md")
    if not ada:
        print(f"Tidak ada entri sebelum {a.bulan}.")
    sys.exit(1 if a.cek and ada else 0)

if __name__ == "__main__":
    main()
