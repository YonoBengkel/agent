# LLM Wiki Pattern

> Pola memori untuk agent: pengetahuan disimpan sebagai wiki Markdown yang ditulis, dirawat, dan diperiksa agent sendiri, bukan hanya diingat di riwayat percakapan satu platform.

Terkait dengan: [[Arsitektur AI]], [[Obsidian Workflow]], [[Obsidian]]

## Inti pola

1. **Sumber luar diolah sekali** menjadi halaman wiki (Ingest), lalu dirujuk berkali-kali.
2. **Pengalaman sendiri dikompilasi** dari log sesi menjadi halaman `system/` (Kompilasi).
3. **Lint menjaga kesehatan**: halaman yatim, link putus, klaim basi, dan isi yang tidak boleh ada.
4. **Cache kecil di depan**: `hot.md` dibaca pertama, `index.md` sebagai katalog.

## Kaitan dengan sistem ini

Pola ini dipakai langsung oleh [[Arsitektur AI]]: lapisan memori adalah vault ini, dan Aturan 11 di workspace merinci operasinya. Asal-usul istilahnya belum dicatat (unverified).
