# Kit agent

Kit ini memasang satu ekosistem agent coding di Windows: aturan bersama untuk beberapa agent, hook
penjaga, vault memori Obsidian, pencarian RAG atas vault itu, dan enam skill. Semuanya dipasang dari
templat oleh satu skrip, `pasang.py`, dengan nama dan folder milikmu sendiri.

Repo ini hanya memuat perkakas dan templatnya. Isi vault, transkrip percakapan, secret, dan pengaturan
akun milik pemilik repo tidak ikut.

## Isi kit

| Bagian | Isinya | Dipasang ke |
|---|---|---|
| Aturan | Protokol folder kerja dan aturan lengkap workspace, masing-masing dengan cermin Bahasa Indonesia `AGENTS_id.md` | `AGENTS.md` di folder kerja dan di folder repo ini |
| Salinan aturan | Blok protokol yang sama untuk tiap agent, dijaga tetap sama oleh `tools\sync_rules.py` | `CLAUDE.md`, `GEMINI.md`, `AGENTS.md` Zed, `SOUL.md` Hermes |
| Hook | Penjaga vault, penjaga repo luar, penjaga desain, konteks awal sesi, ekspor transkrip tersensor, cek proses sisa, cek jurnal, dan dua hook hemat token Claude Code | Pengaturan tiap agent, digabung dengan yang sudah ada |
| Kerangka vault | Struktur folder, halaman contoh, dan aturan format yang lulus `vault_lint.py` | Folder vault pilihanmu |
| RAG | venv kecil tanpa torch, model `intfloat/multilingual-e5-small` versi ONNX, dan indeks pertama vault | `tools\rag-venv`, `tools\models`, `tools\rag_db` |
| Skill | `grill-me`, `grilling`, `obsidian-workflow`, `oper-kerja`, `webapp-audit`, `webapp-testing` | `skills\` |
| Subagent Claude Code | `pencari`, `peneliti`, `peninjau`, masing-masing dengan model dan alat yang sempit | `~\.claude\agents` |
| LLM lokal | Templat `docker-compose.yml` 9Router dan `.env` berisi secret acak | `9router\` dan `.env` |

## Yang tidak ikut

| Tidak ikut | Alasannya |
|---|---|
| Isi vault, transkrip, dan riwayat percakapan pemilik repo | Data pribadi. Yang dibagikan hanya kerangkanya |
| Secret apa pun | `.env` dibuat baru di mesinmu dengan nilai acak. Bentuknya ada di `.env.example` |
| Skill lain milik pemilik repo | Sebagian buatan pihak ketiga tanpa lisensi yang jelas, sebagian memuat aset bermerek dagang, sebagian terikat akun pribadi. Rinciannya di `kit\skills\LISENSI.md` |
| Pengaturan akun Claude (connector, skill akun, plugin) | Melekat ke akun, jadi tidak bisa dibawa lewat repo. Pakai akunmu sendiri |
| OpenCode | Belum termasuk kit. `oper_kerja.py` tetap bisa memakai Hermes |
| macOS dan Linux | Hook dan pembungkusnya baru diuji di Windows |
| axe-core dan Design Kit | axe-core berlisensi MPL-2.0, unduh sendiri kalau perlu (lihat `kit\skills\LISENSI.md`). Design Kit belum bisa dibagikan |

## Yang kamu butuhkan

- Windows 10 atau 11.
- Python 3.10 atau lebih baru dari python.org. Pemasangan penuh diuji dengan 3.14, tes unitnya juga
  dengan 3.12. Hook memakai Python yang menjalankan `pasang.py`, jadi jangan dicopot sesudah memasang.
- Git for Windows. Claude Code menjalankan hook lewat Git Bash.
- Paling sedikit satu agent yang sudah terpasang dan sudah login dengan akunmu sendiri: Claude Code,
  Antigravity, Hermes Agent, atau Zed. `pasang.py` hanya memasang ke agent yang foldernya sudah ada.
- Docker Desktop, hanya kalau mau memakai 9Router untuk Hermes.
- Obsidian untuk membuka vault. Tidak wajib, karena vault-nya berkas Markdown biasa.
- Internet sekali jalan untuk paket RAG dan modelnya. Ruang disknya sekitar 1 GB (venv RAG sekitar
  430 MB, model sekitar 490 MB), ditambah cache unduhan pip.

## Memasang

1. Pilih folder kerja, yaitu folder tempat semua proyekmu, misalnya `D:\Proyek`. Clone repo ini ke
   dalamnya. Folder hasil clone menjadi workspace agent, dan induknya menjadi folder kerja.

   ```powershell
   git clone <url repo ini> "D:\Proyek\Agent"
   ```

2. Tutup semua sesi agent yang sedang berjalan.
3. Dari folder hasil clone, coba dulu dengan `--uji-kering`. Rencananya dicetak tanpa menulis apa pun.

   ```powershell
   python pasang.py --vault "D:\Obsidian\Memori Agent" --nama Budi --github budi --uji-kering
   ```

4. Kalau rencananya sudah benar, jalankan tanpa `--uji-kering`.

   ```powershell
   python pasang.py --vault "D:\Obsidian\Memori Agent" --nama Budi --github budi
   ```

| Opsi | Arti |
|---|---|
| `--vault` | Folder vault memori. Kalau belum ada atau masih kosong, kerangkanya dibuat. Vault yang sudah berisi tidak disentuh |
| `--nama` | Nama panggilanmu, dipakai di aturan |
| `--github` | Akun GitHub-mu. Repo milik akun ini boleh di-clone ke folder kerja, repo orang lain diarahkan ke folder repo luar |
| `--platform` | Agent yang dipasang, misalnya `claude,hermes`. Bawaannya keempatnya, dan yang belum terpasang dilewati |
| `--lindungi` | Folder yang sama sekali tidak boleh dibuka agent. Boleh diulang. Bawaannya `~\.ssh` |
| `--repo-luar` | Folder untuk repo pihak ketiga. Bawaannya `Repo Luar` di sebelah folder kerja |
| `--hermes-home` | Folder data Hermes, kalau bukan `HERMES_HOME` atau `~\.hermes` |
| `--tanpa-rag` | Lewati venv, model, dan indeks RAG |
| `--model-dari` | Folder berisi `model.onnx` dan `tokenizer.json` yang sudah diunduh, supaya tidak mengunduh lagi |
| `--paksa` | Timpa berkas aturan yang sudah ada. Berkas lamanya dicadangkan dulu |

Path tidak boleh memuat kutip, `%`, `$`, atau backtick. Vault dan folder kerja harus terpisah, tidak
saling memuat.

Setiap berkas di keluarannya diberi tanda:

- `DITULIS`: baru atau diperbarui. Kalau berkasnya sudah ada, cadangannya `<nama>.bak-<waktu>` di sebelahnya.
- `ADA`: sudah ada, dibiarkan.
- `SAMA`: isinya sudah sama.
- `LEWAT`: tidak bisa dipasang otomatis. Alasannya ikut dicetak.

Di akhir, `pasang.py` menjalankan `sync_rules.py --check` dan `uji_penjaga.py`, lalu keluar dengan
kode 1 kalau ada yang bermasalah.

`pasang.py` aman dijalankan ulang dengan opsi yang sama, misalnya sesudah `git pull`. Hook kit diganti
dengan versi terbaru, dan hook milikmu sendiri dibiarkan. Aturan, isi vault, `.env`, dan skill yang
sudah ada tidak ditimpa, kecuali aturan dengan `--paksa`.

## Sesudah memasang

Buka ulang sesi agent. Sesi yang sudah berjalan masih memakai aturan dan hook lama.

### Claude Code

- Hook dan aturan izin ditambahkan ke `~\.claude\settings.json`. Aturannya ada di `~\.claude\CLAUDE.md`
  dan di `CLAUDE.md` folder kerja.
- Di sesi baru di folder proyek, konteks vault proyek itu muncul di awal. Di folder repo ini, yang
  dimuat `hot.md` vault.
- `penjaga_subagent.py` menolak pemanggilan subagent yang tidak menyebut model, supaya subagent tidak
  diam-diam memakai model sesi yang mahal. `penahan_jeda.py` memperingatkan saat kamu kembali ke sesi
  besar sesudah jeda lama, karena pesan pertama sesudah jeda menulis ulang seluruh konteks ke cache.
  Tambahkan `--tahan` di perintah hook-nya kalau mau pesan itu ditahan sekali.

### Antigravity

- Empat hook ada di `~\.gemini\config\hooks.json`, dengan pembungkus `.cmd` di
  `~\.gemini\config\hooks\`. Aturannya di `~\.gemini\GEMINI.md`.
- Hook tidak dipasang kalau path profilmu memuat spasi atau huruf non-ASCII, dan `pasang.py`
  menyebutnya di keluaran. Aturannya tetap dipasang.

### Hermes dan 9Router

1. Jalankan 9Router dari folder `9router` (butuh Docker Desktop). Port-nya hanya terbuka untuk
   komputer ini.

   ```powershell
   docker compose --env-file ..\.env up -d
   ```

2. Buka `http://localhost:20128`, masuk dengan sandi `NINEROUTER_INITIAL_PASSWORD` dari `.env`,
   sambungkan akun penyedia LLM milikmu sendiri, lalu buat API key. Simpan kuncinya di
   `NINEROUTER_API_KEY` di `.env`.
3. Jalankan `hermes model`, pilih endpoint kustom `http://localhost:20128/v1`, lalu isi API key tadi.
4. Hook Hermes yang belum disetujui dilewati diam-diam. Setujui sekali dengan menjalankan Hermes
   memakai `--accept-hooks`, lalu periksa dengan `hermes hooks doctor`. Ulangi setiap kali perintah
   hook di `config.yaml` berubah, termasuk sesudah `pasang.py` dijalankan ulang.
5. Kalau `config.yaml` Hermes sudah punya bagian `hooks` sendiri atau belum ada, `pasang.py` tidak
   menyentuhnya dan menulis potongannya ke `Konfigurasi\hermes-hooks.yaml`. Gabungkan sendiri, lalu
   lakukan langkah 4.
6. Matikan 9Router sesudah selesai, dari folder yang sama.

   ```powershell
   docker compose --env-file ..\.env down
   ```

Di Hermes, isi vault baru dikirim ke model kalau pesanmu memuat `pakai konteks`. Giliran lain hanya
mendapat satu kalimat bahwa konteks proyek tersedia.

### Zed

- Aturannya di `%APPDATA%\Zed\AGENTS.md`.
- Pola penolakan untuk folder yang dilindungi ada di `Konfigurasi\zed-settings-contoh.json`. Gabungkan
  sendiri ke `settings.json` Zed, karena berkas itu biasanya berisi pengaturan pribadimu.

### Vault dan RAG

- Buka folder vault sebagai vault di Obsidian. Isi `Wiki\system\Profil Pengguna.md` dulu, lalu ganti
  `Contoh Proyek` dengan proyek pertamamu.
- Perintah lengkap tiap alat untuk mesinmu ada di halaman `Wiki\system\Tools CLI.md` di vault.
- Mencari di vault. Indeksnya diperbarui sendiri setiap kali mencari.

  ```powershell
  tools\rag-venv\Scripts\python.exe tools\rag_engine.py search "pertanyaan"
  ```

### Mengubah aturan

Sunting `AGENTS.md` di folder kerja, lalu jalankan `python tools\sync_rules.py`. Bagian bersamanya
disalin ke semua agent, dan cermin terjemahannya ditandai `PERIKSA`. Sesudah cerminnya diterjemahkan
ulang, cap dengan `--stamp <berkas cermin>`, lalu ulangi dengan `--check` sampai bersih. Langkah
lengkapnya di bagian Changing rules di `AGENTS.md` folder kerja.

### Melepas kit

Cadangan tiap berkas konfigurasi ada di sebelahnya (`.bak-<waktu>`). Untuk melepas hook, pulihkan
cadangannya, atau hapus entri yang perintahnya menunjuk ke folder `tools` repo ini. Blok kit di
`~\.claude\CLAUDE.md` diapit penanda `agent-kit:begin` dan `agent-kit:end`, begitu juga di
`config.yaml` Hermes.

## Ketentuan LLM

- Setiap orang memakai akun dan API key sendiri. Kit ini tidak membawa kunci apa pun.
- Baca ketentuan layanan tiap penyedia sebelum menyambungkannya ke 9Router. Sebagian penyedia
  melarang langganan pribadi dipakai lewat proxy atau oleh aplikasi lain, dan akun bisa diblokir
  karenanya.
- Model gratis sering memakai percakapan untuk pelatihan, atau percakapannya dibaca peninjau manusia.
  Jangan kirim isi vault atau data pribadi ke model seperti itu.
- Di mesin pemilik repo, Claude Code dan Zed memakai akun Claude, Antigravity memakai akun Google, dan
  Hermes memakai 9Router dengan Gemini Flash Lite sebagai model bawaan. Itu contoh, bukan syarat.

## Perkakas

Semua skrip di `tools\` memakai pustaka standar, kecuali `rag_engine.py` dan `rag_eval.py` yang jalan
di `tools\rag-venv`. Tiap skrip punya `--help`.

| Berkas | Fungsi |
|---|---|
| `pasang.py` | Pemasang kit ini |
| `lokasi.py` | Lokasi vault dan folder kerja dibaca dari registry aturan, supaya tidak ada tool yang menanam path satu mesin |
| `rag_engine.py` | Retrieval hibrida atas vault Markdown: BM25 dan embedding, index inkremental, judul bagian per chunk |
| `rag_eval.py` | Harness evaluasi: recall, precision, dan MRR terhadap set soal berlabel, dengan pemisahan dev dan holdout, plus uji randomisasi berpasangan (`--compare`) |
| `vault_lint.py` | Penjaga mutu catatan: tautan putus, catatan yatim, pelanggaran format, secret dan teks terlarang di catatan, serta proyek yang berubah tanpa catatan |
| `vault_guard.py` | Hook sebelum alat menulis: menolak tulisan ke vault yang memuat nomor identitas, kata terlarang, atau secret (gagal berarti tolak), dan menutup folder `--protect` dari pembacaan dan penulisan |
| `penjaga_repo.py` | Hook sebelum perintah shell dan tulisan berkas: repo pihak ketiga tidak boleh di-clone atau disalin ke folder kerja |
| `penjaga_desain.py` | Hook sebelum alat menulis: berkas tampilan baru dan `DESIGN.md` ditolak selama halaman Referensi Desain belum dibaca di sesi itu. Ini pengingat, jadi gagal memeriksa berarti lolos |
| `penjaga_subagent.py` | Hook Claude Code: subagent wajib menyebut model |
| `penahan_jeda.py` | Hook Claude Code: peringatan saat kembali ke sesi besar sesudah jeda yang lebih lama dari umur cache |
| `session_context.py` | Merakit konteks awal sesi dari vault untuk Claude Code, Hermes, dan Antigravity |
| `export_transcript.py` | Mengekspor transkrip percakapan sambil menyensor nilai secret dari `.env` dan berkas konfigurasi proyek |
| `cek_proses_sisa.py` | Hook Stop: melaporkan proses uji yang tertinggal, seperti server dev dan browser |
| `cek_jurnal.py` | Hook Stop: mengingatkan sekali kalau sesi mengubah berkas proyek tanpa menulis log sesi di vault |
| `sync_rules.py` | Menjaga aturan yang punya beberapa salinan dan terjemahan tetap sinkron, dengan mode `--check` |
| `uji_penjaga.py` | Uji hidup hook terpasang: dijalankan persis seperti di konfigurasinya, dengan payload yang wajib ditolak dan kembarannya yang wajib lolos |
| `uji_agen.py` | Canary lintas agent: tugas uji yang sama di Antigravity atau Hermes, dinilai dari alat yang dipanggil |
| `uji_peta.py` | Menguji setiap baris peta kemampuan `PETA_SKILLS_TOOLS.md` |
| `oper_kerja.py` | Mengoper tugas kode kecil ke agent gratis di git worktree terpisah, dengan alat berkas yang dikunci ke worktree itu |
| `cadangkan_vault.py` | Mencadangkan vault ke repo git privatnya, sesudah semua berkasnya dipindai pola penjaga vault |
| `putar_log.py` | Memindahkan entri log wiki bulan lalu ke `Riwayat\`, supaya log yang dibaca agent tetap kecil |
| `laporan_harian.py` | Cek harian lewat Task Scheduler. Tidak dipasang `pasang.py` |
| `ukur_token.py` | Ukuran anggaran token mingguan dari transkrip Claude Code |
| `pdf_parser.py` | Mengambil teks PDF ke Markdown |
| `cek_bersih.py` | Cek sebelum repo ini terbit: gitleaks, pola secret penjaga vault, email, path profil, dan daftar istilah pribadi lokal |
| `test_tools.py` | Tes kecil untuk logika skrip di atas dan `pasang.py` |

`uji_peta.py` mengikuti peta kemampuan workspace pemilik repo, jadi di kit ini skill dan tool yang
tidak ikut dilaporkan GAGAL. Itu wajar. `PETA_PERAWATAN.md` adalah peta perawatan skrip-skrip ini.

## Evaluasi retrieval

Bagian yang paling banyak memakan waktu bukan menulis retrieval-nya, melainkan membuktikan
pilihan-pilihannya. `rag_eval.py` dijalankan terhadap set soal berlabel yang dipisah menjadi dev
(untuk menyetel) dan holdout (dipakai sekali di akhir), sehingga angkanya bukan hasil menyetel ke soal
yang sama.

**Model embedding multibahasa menentukan hasil untuk catatan berbahasa Indonesia.**

| Model | Recall (vector, dev) |
|---|---|
| `all-MiniLM-L6-v2` | 0.278 |
| `multilingual-e5-small` | 0.694 |

Model Inggris saja hampir tidak berguna di sini. Temuan ini tidak akan kelihatan tanpa evaluasi,
karena keduanya sama-sama jalan kalau hanya dicoba sekilas.

**Hibrida mengalahkan kedua komponennya.** Pada set dev, BM25 saja mencapai recall 0.625, vector saja
0.694, dan hibrida 0.800. Keduanya gagal pada soal yang berbeda, jadi gabungannya saling menambal.

**Penguatan lewat backlink membantu, tetapi hanya sampai titik tertentu.** Bobot 0.5 untuk catatan
yang ditautkan oleh hasil teratas menaikkan recall dev dari 0.800 ke 0.856. Bobot 1 dan 2 justru
menurunkannya lagi (0.789 dan 0.733), karena penguatan yang terlalu besar menenggelamkan kecocokan
langsung. Konfigurasi itu diuji sekali terhadap holdout: **recall 0.889, MRR 1.0**.

**Pembaruan Oktober 2026.** Penguatan backlink kemudian dimatikan karena kalah di set holdout
berikutnya, yang lebih besar dan memuat soal lintas konteks. Konfigurasi sekarang adalah
`multilingual-e5-small` dan BM25 lewat RRF (bobot 2:1), chunk 1000 dengan overlap 100, dan skor
halaman log sesi dikali 0,97. Holdout 14 soal terbaru: Recall@5 0,58, MRR 0,72. Kandidat perbaikan
(reranker cross-encoder kecil, judul bagian untuk BM25) ditolak setelah diuji dengan uji randomisasi
berpasangan. Model di kit ini adalah ekspor ONNX resmi dari model yang sama.

Set soal evaluasi tidak ikut terbit karena menunjuk ke catatan pribadi. Formatnya satu objek JSON per
baris dengan kunci `id`, `query`, dan `relevant` (daftar path yang seharusnya terambil).

## Menjalankan tes

```powershell
tools\rag-venv\Scripts\python.exe tools\test_tools.py
```

## Lisensi

Repo ini belum punya berkas LICENSE, jadi tanyakan ke pemiliknya sebelum memakai ulang kodenya di
luar kit. Lisensi tiap skill ada di `kit\skills\LISENSI.md`. Image Docker 9Router (`decolua/9router`)
dan model embedding (`intfloat/multilingual-e5-small`, MIT) milik pembuatnya masing-masing.
