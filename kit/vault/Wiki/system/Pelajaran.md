# Pelajaran

> Kesalahan yang pernah terjadi, pola di baliknya, dan cara mencegahnya (Aturan 10). Sebelum bekerja di sebuah area, baca indeks per area lalu buka hanya pelajaran yang terdaftar untuk area itu.

Terkait dengan: [[Arsitektur AI]], [[Tools CLI]]

## Indeks per area

- **Vault dan memori:** #1
- **Tools dan penjaga:** (belum ada)

## Daftar

| # | Apa yang terjadi | Pola | Cara mencegah |
|---|---|---|---|
| 1 | Contoh dari kit: agent menulis klaim dari ingatan tanpa membuka sumbernya | klaim yang diingat dianggap sudah dicek | buka sumber primer sebelum mengulang atau mengoreksi klaim, dan tandai `(unverified)` kalau belum sempat |

Tambahkan pelajaran baru di tabel dengan nomor berikutnya, lalu sebut nomornya di indeks per area. `vault_lint.py` melaporkan nomor yang belum masuk indeks.
