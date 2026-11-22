# Obsidian Workflow

> Cara vault ini disusun dan ditulisi agent, supaya semua sesi menulis dengan bentuk yang sama dan Graph View tetap berguna.

Terkait dengan: [[Arsitektur AI]], [[Obsidian]], [[LLM Wiki Pattern]]

## Susunan folder

| Folder | Isi |
|---|---|
| `Wiki/system/` | memori-diri: profil, arsitektur, tools, pelajaran |
| `Wiki/projects/` | satu halaman per proyek di folder kerja, bernama sama dengan folder proyeknya |
| `Wiki/concepts/`, `Wiki/entities/`, `Wiki/sources/` | pengetahuan dari luar hasil Ingest |
| `Log/<Konteks>/` | log sesi, satu berkas per topik per sesi, bernama `NNN <topik>.md` |
| `Riwayat/` | riwayat bulanan `KONTEKS_PROYEK.md` dan log wiki |

## Aturan format

1. Kalimat tujuan di awal, heading `##`, minimal 2 backlink, UTF-8 tanpa BOM.
2. Klaim yang belum dicek diberi `(unverified)`. Fakta kode atau path yang sudah dicek membawa tanggal dan tempatnya.
3. Entitas, nama tool, dan konsep dibungkus `[[...]]` di prosa (Aturan 3).
4. Halaman wiki baru ditambahkan ke `index.md`. `vault_lint.py` melaporkan halaman yatim dan halaman yang belum tercantum.

## Pencarian

Untuk mencari di luar halaman proyek, pakai mesin RAG (Aturan 5, perintahnya di [[Tools CLI]]). Hasilnya daftar halaman untuk dibuka, bukan jawaban.
