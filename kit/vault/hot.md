# Hot Cache

> Keadaan terkini lintas-sesi, dibaca pertama oleh agent (Aturan 1). Ini cache: **tulis ulang, jangan ditambahi**, maksimal ~500 kata. Keadaan lengkapnya di `KONTEKS_PROYEK.md`, riwayatnya di `Riwayat/`.

Terkait dengan: [[Profil Pengguna]], [[Arsitektur AI]], [[Obsidian Workflow]], [[Tools CLI]]

*Diperbarui: {{TANGGAL}} oleh `pasang.py`*

## Fokus Sekarang

- **Kit agent baru dipasang** ([[001 Pemasangan Kit]]). Langkah pertama: isi [[Profil Pengguna]], lalu buat halaman proyek pertama dengan mencontoh [[Contoh Proyek]].

## Keadaan Sistem

- **Aturan:** satu sumber, banyak salinan (`sync_rules.py`), diubah hanya atas permintaan langsung {{NAMA}}.
- **Penjaga:** `vault_guard.py` memeriksa tulisan ke vault dan menutup folder yang dilindungi. Cek dengan `uji_penjaga.py` ([[Tools CLI]]).
- **RAG:** indeks vault dibuat saat pemasangan. Pencarian menyegarkan berkas yang berubah sendiri.

## Keputusan Penting

1. **Netral-vendor:** aturan di `AGENTS.md`, memori di vault, tools sebagai CLI, skill sebagai `SKILL.md` ([[Arsitektur AI]]).
2. **Cek sumber primer sebelum mengusulkan koreksi**, termasuk laporan subagent ([[Pelajaran]]).

## Next Steps untuk sesi berikutnya (tawarkan dulu)

1. Isi [[Profil Pengguna]] bersama {{NAMA}}.
2. Buat halaman proyek pertama di `Wiki/projects/` dan catat di `index.md`.
