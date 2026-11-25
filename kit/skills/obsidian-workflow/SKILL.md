---
name: obsidian-workflow
description: Peta vault memori agent dan langkah praktis membaca/menulis di dalamnya. Gunakan setiap kali tugas menyentuh Obsidian, wiki, log sesi, atau KONTEKS_PROYEK. Aturan penulisannya sendiri ada di AGENTS.md (Aturan 3, 4, 10, 11, 12) — skill ini tidak mengulangnya.
---

# Obsidian Workflow

Aturan menulis (format, backlink, tanpa BOM, kapan menjurnal, retraksi, operasi wiki,
pemicu) ada di `AGENTS.md` folder workspace agent. Skill ini hanya berisi **peta** dan
**langkah praktis**.

## Peta

Peta lengkap vault dan lokasi lainnya ada di tabel **Locations** `AGENTS.md` workspace,
sebagai satu-satunya sumber, supaya tidak ada peta kedua yang bisa basi.

Satu vault = satu ruang link. `[[Nama Halaman]]` hanya tersambung ke halaman di vault
yang sama, jadi semua memori agent harus berada di dalam vault memori yang disebut protokol folder kerja.

## Langkah Praktis

**Membaca:** `hot.md` → `index.md` → halaman spesifik. Cari kata kunci dengan pencarian
terarah; jangan membaca seluruh vault.

**Menulis halaman baru:**
1. Tentukan tempatnya: pengetahuan tentang sistem/user → `Wiki\system\`; dari sumber
   luar → `Wiki\sources\` + `concepts\`/`entities\`; catatan sesi → `Log\<Konteks>\`.
2. Tulis dengan format Aturan 3 (kalimat tujuan, heading, ≥2 backlink, UTF-8 tanpa BOM).
3. Halaman wiki baru → tambahkan ke `index.md` dan catat di `Wiki\log.md` lalu `log_id.md`.

**Memperbarui `KONTEKS_PROYEK.md`:** tulis ulang statusnya di tempat. Catatan perubahan
besar ditambahkan di "Log Perubahan" `Riwayat\KONTEKS <YYYY-MM>.md` bulan ini. Jika ada klaim lama yang terbukti salah, **koreksi di tempat** (Aturan 10).

Format entri log perubahan:
```markdown
### YYYY-MM-DD -- Judul Perubahan
- Apa yang berubah
- Keputusan yang diambil
- Status saat ini
```
