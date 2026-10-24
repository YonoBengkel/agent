# Perkakas workspace agent

Sembilan skrip Python tanpa dependensi berat yang menjalankan satu *knowledge workspace*
berbasis Markdown untuk coding agent: pencarian atas catatan, evaluasi kualitas
pencariannya, penjagaan mutu catatan, penjaga tulisan ke catatan, dan penyensoran transkrip.

Repo ini sengaja hanya memuat perkakasnya. Isi workspace-nya sendiri — catatan, transkrip
percakapan, dan konfigurasi — tidak ikut terbit.

## Perkakasnya

| Berkas | Fungsi |
|---|---|
| `rag_engine.py` | Retrieval hibrida atas vault Markdown: BM25 + embedding, index inkremental, judul bagian per chunk |
| `rag_eval.py` | Harness evaluasi: recall, precision, dan MRR terhadap set soal berlabel, dengan pemisahan dev/holdout, plus uji randomisasi berpasangan (`--compare`) untuk membandingkan dua hasil |
| `vault_lint.py` | Penjaga mutu catatan: cari tautan putus, catatan yatim, pelanggaran format, nilai secret dan teks terlarang di dalam catatan, serta proyek yang berubah tanpa catatan |
| `vault_guard.py` | Hook PreToolUse untuk coding agent: menolak tulisan ke vault yang memuat nomor identitas, kata terlarang, atau secret (gagal berarti tolak) |
| `test_tools.py` | Tes kecil untuk logika skrip di atas |
| `sync_rules.py` | Menjaga berkas aturan yang punya beberapa salinan dan terjemahan tetap sinkron, lengkap dengan mode `--check` untuk CI |
| `session_context.py` | Merakit konteks awal satu sesi agent dari vault |
| `pdf_parser.py` | Mengambil teks PDF ke Markdown |
| `export_transcript.py` | Mengekspor transkrip percakapan sambil menyensor nilai secret yang ditemukan di `.env` dan berkas konfigurasi proyek |

## Evaluasi retrieval

Bagian yang paling banyak memakan waktu bukan menulis retrieval-nya, melainkan membuktikan
pilihan-pilihannya. `rag_eval.py` dijalankan terhadap set soal berlabel yang dipisah menjadi
dev (untuk menyetel) dan holdout (dipakai sekali di akhir), sehingga angkanya bukan hasil
menyetel ke soal yang sama.

Tiga hal yang keluar dari evaluasinya:

**Model embedding multibahasa menentukan segalanya untuk catatan berbahasa Indonesia.**

| Model | Recall (vector, dev) |
|---|---|
| `all-MiniLM-L6-v2` | 0.278 |
| `multilingual-e5-small` | 0.694 |

Model Inggris-saja hampir tidak berguna di sini. Ini temuan yang tidak akan kelihatan tanpa
evaluasi — keduanya sama-sama "jalan" kalau cuma dicoba sekilas.

**Hibrida mengalahkan kedua komponennya.** Pada set dev: BM25 saja recall 0.625, vector saja
0.694, hibrida 0.800. Keduanya gagal pada soal yang berbeda, jadi menggabungkannya menambal
keduanya.

**Penguatan lewat backlink membantu, tapi hanya sampai titik tertentu.** Menambah bobot 0.5
untuk catatan yang ditautkan oleh hasil teratas menaikkan recall dev dari 0.800 ke 0.856.
Bobot 1 dan 2 justru menurunkannya kembali (0.789 dan 0.733): penguatan yang terlalu besar
menenggelamkan kecocokan langsung.

Konfigurasi akhir — `multilingual-e5-small`, hibrida, chunk 1000, bobot vektor 2.0,
penguatan backlink 0.5 — diuji sekali terhadap holdout: **recall 0.889, MRR 1.0**.

**Pembaruan (Oktober 2026):** penguatan backlink kemudian dimatikan karena kalah di set
holdout berikutnya, yang lebih besar dan memuat soal lintas konteks. Konfigurasi sekarang:
`multilingual-e5-small` + BM25 lewat RRF (bobot 2:1), chunk 1000 dengan overlap 100, dan skor
halaman log sesi dikali 0,97. Holdout 14 soal terbaru: Recall@5 0,58, MRR 0,72. Kandidat
perbaikan (reranker cross-encoder kecil, judul bagian untuk BM25) ditolak setelah diuji dengan
uji randomisasi berpasangan.

## Menjalankannya

Semuanya memakai pustaka standar kecuali `rag_engine.py` dan `rag_eval.py`, yang butuh
`chromadb` dan `sentence-transformers`. Versi paket setiap virtualenv tercatat di
`tools/requirements/`. Tiap skrip punya `--help`.

```
python tools/rag_engine.py index <folder>
python tools/rag_engine.py search "pertanyaan" --root <folder>
python tools/rag_eval.py   <folder> --set eval/soal.jsonl --k 5
python tools/rag_eval.py   --compare hasil_a.json hasil_b.json
python tools/vault_lint.py <folder> --secrets-from .env --words kata_terlarang.txt --projects-root <folder-proyek>
python tools/test_tools.py
```

Set soal evaluasi tidak ikut terbit karena menunjuk ke catatan pribadi; formatnya satu objek
JSON per baris dengan kunci `id`, `query`, dan `relevant` (daftar path yang seharusnya
terambil).
