# Peta Skills dan Tools AI Agent

> Pustaka tunggal pemetaan kemampuan (skills dan tools) lintas operator (Claude Code, Antigravity IDE, Zed, Hermes Agent, OpenCode).
> Rujukan utama saat pengguna meminta: "gunakan skills/tools yang necessary" atau saat tugas membutuhkan kemampuan spesifik.

Semua skill dan tools disimpan terpusat di folder `skills\` dan `tools\` workspace ini, yaitu folder tempat berkas ini berada. Path absolut workspace tertulis di protokol folder kerja (`<folder kerja>\AGENTS.md`).
Folder `skills\` tidak ikut repo workspace. Di mesin pemilik ia repo git terpisah, sedangkan di mesin yang dipasang dari kit isinya disalin `pasang.py` dari `kit\skills\`.
Prinsip kerja: **Just-in-Time (JIT)**. Agent membaca instruksi skill atau menjalankan tool hanya saat dibutuhkan agar hemat token dan menjaga context window tetap bersih.

---

## Cara Pemakaian oleh Agent

1. **Cocokkan Kebutuhan**: Saat pengguna memberi instruksi atau tugas, cek tabel di bawah untuk menemukan skill atau tool yang relevan.
2. **Baca Petunjuk (Just-in-Time)**: Baca berkas `SKILL.md` dari path yang tertera menggunakan tool baca berkas standar operator. Path yang bukan `SKILL.md` adalah sub-peta: baca dulu, lalu pilih satu skill di dalamnya.
3. **Sebutkan ke pengguna**: satu kalimat, misalnya *"Menggunakan skill [nama] dari lumbung untuk [alasan ringkas]"*.
4. **Eksekusi**: Jalankan instruksi di dalam skill tersebut dengan cermat.
5. **Efisiensi Token**: Muat hanya 1 skill yang paling tepat per sub-tugas, dan paling banyak 2 skill atau tool untuk satu tugas.

Cara tiap operator mengakses skill dan tool, serta cara menambah atau mengubah baris peta, ada di `PETA_PERAWATAN.md` di folder yang sama. Berkas itu tidak perlu dibaca saat memilih skill.

---

## 1. Peta Skills (Instruksi Kerja Mandiri)

Path relatif terhadap folder `skills\` workspace ini. Dari workspace proyek lain, gabungkan dengan path workspace yang tertulis di protokol folder kerja.
Skill yang foldernya tidak ada di `skills\` tidak terpasang di mesin ini: katakan begitu, lalu lanjut tanpa skill itu. Kit hanya memasang enam skill: `grill-me`, `grilling`, `oper-kerja`, `obsidian-workflow`, `webapp-testing`, dan `webapp-audit` (asal dan lisensinya di `kit\skills\LISENSI.md`).

### A. Desain, Frontend & Antarmuka

Sebelum memilih arah desain, buka halaman vault `Wiki\system\Referensi Desain.md`, daftar lengkap referensi desain kita (protokol folder kerja sejak 2026-11-08).

| Nama Skill | Kapan Digunakan (Trigger) | Path Berkas | Operator |
|---|---|---|---|
| `design-kit` | Membuat halaman web, landing page, dashboard, komponen HTML/CSS, menentukan arah visual, audit anti-AI-slop, memilih design system | `design-kit/SKILL.md` | Universal (Claude, Antigravity, OpenCode) |
| `logo-design` | Merancang logo, wordmark, monogram, brand mark SVG, favicon, evaluasi logo, mencari referensi 1.400+ SVG | `logo-design/SKILL.md` | Universal |
| `break-ui` | Uji stres UI dengan data ekstrem (nama sangat panjang, nol item, angka raksasa, emoji, layout patah) | `break-ui/SKILL.md` | Universal |
| `emil-design-eng` | Review estetika UI, hierarki visual, micro-interactions, craft bar tinggi ala Emil Kowalski | `emil-design-eng/SKILL.md` | Universal |
| `mobile-native` | Mengoptimasi web app agar terasa seperti aplikasi native di HP (tap delay, notch, 100vh bug, scroll) | `mobile-native/SKILL.md` | Universal |
| `design-taste-breakdown` | Membedah dan mengekstrak token desain (warna, tipografi, ritme) dari situs referensi | `design-taste-breakdown/SKILL.md` | Universal |
| `animate` | Animasi dan motion (web, React Native, istilah, review, audit) serta video demo. Sub-peta | `animate/animate.md` | Universal |
| `print-and-slides` | Bahan cetak (banner, poster, brosur, leaflet), slide (PPT, deck, naskah, aset Canva), dan teks pendamping tugas (paragraf proses, refleksi, pengungkapan AI) | `print-and-slides/SKILL.md` | Universal |
| `apple-design` | Menerapkan prinsip desain antarmuka dan motion fisik khas Apple ke web | `apple-design/SKILL.md` | Universal |
| `pick-ui-library` | Memilih pustaka frontend yang tepat dari kurasi teruji (tabel, dnd, modal, chart, toast). Sesudah memilih Sonner, baca `ask-sonner` | `pick-ui-library/SKILL.md` | Universal |
| `prototype` | Membuat beberapa alternatif variasi UI untuk dipilih secara visual | `prototype/SKILL.md` | Universal |

### B. Perencanaan, Wawancara & Review

| Nama Skill | Kapan Digunakan (Trigger) | Path Berkas | Operator |
|---|---|---|---|
| `grilling` | Wawancara tajam berputaran (drill, grill, `/grill-me`) untuk mematangkan rencana, arsitektur, atau keputusan, dan menguji asumsinya | `grilling/SKILL.md` | Universal |
| `oper-kerja` | Mengoper tugas kode kecil yang jelas dan bisa diuji ke agent gratis (OpenCode, Hermes), supaya agent utama cukup merencanakan dan memeriksa | `oper-kerja/SKILL.md` | Universal, perlu terminal |

### C. Dokumen, Data Science & Rekayasa

| Nama Skill | Kapan Digunakan (Trigger) | Path Berkas | Operator |
|---|---|---|---|
| `markdown-to-docx` | Mengonversi teks atau berkas Markdown ke dokumen Word (.docx) dengan styling rapi | `markdown-to-docx/SKILL.md` | Universal |
| `data-notebook` | Notebook Jupyter, Kaggle, atau Colab, EDA, machine learning, validasi tanpa kebocoran, submisi kompetisi, dan grafik Python | `data-notebook/SKILL.md` | Universal |
| `schema-mapping` | Pemetaan skema antar basis data, transformasi data, ETL dan ELT | `schema-mapping/SKILL.md` | Universal |
| `managing-python-dependencies` | Tata kelola virtualenv dan dependensi Python tanpa merusak lingkungan sistem | `managing-python-dependencies/SKILL.md` | Universal |

### D. Memori & Produktivitas

| Nama Skill | Kapan Digunakan (Trigger) | Path Berkas | Operator |
|---|---|---|---|
| `obsidian-workflow` | Mengelola catatan vault Obsidian, struktur link, log sesi, dan konsep wiki | `obsidian-workflow/SKILL.md` | Universal |
| `microsoft-onenote` | Membaca dan mencari catatan di Microsoft OneNote pengguna via CLI | `microsoft-onenote/SKILL.md` | Universal |
| `web-browser` | Mengambil dan memeriksa isi halaman web atau endpoint API tanpa browser GUI berat | `web-browser/SKILL.md` | Universal |

### E. Pengujian & Audit Aplikasi Web

| Nama Skill | Kapan Digunakan (Trigger) | Path Berkas | Operator |
|---|---|---|---|
| `webapp-testing` | Menjalankan dan menguji aplikasi web lokal di browser sungguhan (Playwright di Edge terpasang): klik, isi form, tangkapan layar, log konsol, server uji yang dimatikan lagi sesudahnya | `webapp-testing/SKILL.md` | Universal |
| `webapp-audit` | Audit tampilan, integrasi, dan kesesuaian fitur aplikasi web yang sudah dibangun: sapu rute (luberan, target sentuh, axe, galat konsol, request gagal, kata terlarang), matriks aksi ke request dan tabel, cek tersimpan sesudah muat ulang, layar saat backend mati, alur lintas peran, matriks fitur terhadap ide bisnis, peta hubungan antarfitur, janji terhadap kode, lensa logika bisnis, laporan berperingkat | `webapp-audit/SKILL.md` | Universal |

---

## 2. Peta Tools CLI (Perkakas Skrip)

Path relatif terhadap folder workspace ini. `<vault>` dan `<folder kerja>` adalah path yang dipakai saat pemasangan, tertulis di protokol folder kerja.

| Nama Tool | Kebutuhan / Fungsi | Perintah Eksekusi |
|---|---|---|
| `rag_engine.py` | Pencarian semantik hybrid di vault catatan atau folder dokumen lain | `tools\rag-venv\Scripts\python.exe tools\rag_engine.py search "<kata>" [--root <folder>]` |
| `vault_lint.py` | Cek integritas vault (link putus, file kosong, secret bocor, Unicode tak terlihat, dokumen proyek basi) | `python tools\vault_lint.py <vault>` |
| `sync_rules.py` | Sinkronisasi aturan lintas agent (Claude, Antigravity, Zed, Hermes) | `python tools\sync_rules.py` (tulis) atau `--check` (lapor) |
| `markitdown` | Mengubah dokumen (PDF, Word, PPT), YouTube, atau audio menjadi Markdown | `tools\markitdown-venv\Scripts\markitdown.exe <file> -o <file.md>` |
| `pdf_parser.py` | Parsing PDF berstruktur kompleks menjadi Markdown | `tools\opendataloader-venv\Scripts\python.exe tools\pdf_parser.py <file.pdf> --output <folder>` |
| `design_lint.mjs` | Linter anti-AI-slop untuk berkas HTML/CSS | `node tools\design-kit\design_lint.mjs <file.html>` |
| `export_transcript.py` | Ekspor transkrip percakapan ke Markdown dengan sensor secret. `--format antigravity` atau `hermes` mengekspor semua percakapan proyek di folder kerja dari data agent itu, dijalankan saat kompilasi | `python tools\export_transcript.py <file.jsonl> --out <folder>`, atau `--format antigravity --app-dir <folder data> --projects-root <folder kerja> --out <folder>` |
| `uji_agen.py` | Canary lintas agent (Antigravity, Hermes): tugas uji yang sama di repo biasa dan repo `.no-vault`, skor N dari M dihitung skrip | `python tools\uji_agen.py siapkan --root <folder kerja>`, lalu `jalan agy a --root <folder kerja> --vault <vault> --hasil <berkas.jsonl>`, `skor --hasil <berkas.jsonl>`, `bersihkan --root <folder kerja>` |
| `cek_proses_sisa.py` | Daftar proses alat sisa uji (server dev, uvicorn, Hermes, 9Router, agy, Docker, Playwright) beserta port dan asalnya. Di Claude jalan sendiri lewat hook Stop, agent lain menjalankannya manual sesudah uji | `python tools\cek_proses_sisa.py --sejak 3h` |
| `putar_log.py` | Pindahkan entri bulan lalu dari `Wiki/log.md` dan `log_id.md` ke folder `Riwayat/` di vault. Dijalankan di langkah 1 Kompilasi | `python tools\putar_log.py --vault <vault>` (tulis) atau `--cek` (lapor) |
| `cadangkan_vault.py` | Cadangkan vault ke repo git privatnya: pindai semua berkas teks (secret, kata terlarang, nomor identitas), lalu gitleaks sebagai gerbang kedua, dan commit serta push hanya kalau bersih. Dijalankan di langkah terakhir Kompilasi | `python tools\cadangkan_vault.py --vault <vault> --words Konfigurasi\penjaga_vault_terlarang.txt --secrets-from <berkas secret> --gitleaks <gitleaks.exe>` (atau `--cek`) |
| `penjaga_repo.py` | Hook sebelum perintah shell: menolak clone repo pihak ketiga ke folder kerja dan salinan dari folder repo luar ke sana, lalu menunjuk tujuan yang benar. Terpasang di Claude, Hermes, dan Antigravity | Dipasang sebagai hook (`--format claude`, `hermes`, atau `antigravity`), bukan dijalankan manual |
| `uji_penjaga.py` | Uji hidup penjaga yang terpasang: perintah hook `vault_guard.py`, `penjaga_repo.py`, dan `penjaga_desain.py` di Claude, Antigravity, dan Hermes dijalankan persis seperti di konfigurasinya, dengan payload wajib tolak dan kembarannya yang wajib lolos. Keluar 1 kalau ada penjaga yang mati atau salah pasang. Dari `config.yaml` Hermes hanya bagian hooks yang dibaca | `python tools\uji_penjaga.py --claude-settings ~/.claude/settings.json --antigravity-hooks ~/.gemini/config/hooks.json --hermes-config <HERMES_HOME>/config.yaml` (tambah `--hermes-doctor <HERMES_HOME>/bin/hermes.exe` untuk ringkasan `hermes hooks doctor`) |
| `laporan_harian.py` | Laporan harian terjadwal: lint vault, pindai cadangan dengan gitleaks tanpa push, salinan aturan, uji hidup penjaga, dan proses sisa, ditulis ke `Riwayat Perckapan\laporan-harian.json`. Dijalankan Task Scheduler ("AI Agent Laporan Harian", harian dan saat login, sekali sehari), dan hook awal sesi workspace menampilkan satu baris kalau ada temuan atau laporannya basi. Tidak pernah commit, push, atau menulis vault | `python tools\laporan_harian.py jalan --vault <vault> --words <daftar> --secrets-from <berkas secret> --gitleaks <exe> --claude-settings <settings> --antigravity-hooks <hooks> --hermes-config <config>` (atau `baris`) |
| `cek_jurnal.py` | Hook Stop Claude: kalau berkas proyek di folder kerja berubah sesudah tulisan terakhir ke folder Log vault di sesi itu, agent ditahan sekali untuk menulis log (Aturan 4) atau menyebut kenapa tidak perlu. Tidak menahan saat `stop_hook_active` atau dua kali untuk perubahan yang sama, dan melewati proyek `.no-vault` | `python tools\cek_jurnal.py --hook --vault <vault> --projects-root <folder kerja>` (dari hook Stop di `~/.claude/settings.json`) |
| `cek_bersih.py` | Cek pembersih sebelum komit atau push repo workspace: gitleaks, pola `vault_guard.py` (nomor identitas, kata terlarang, secret), email selain alamat noreply dan contoh, path profil pengguna, dan istilah pribadi dari daftar lokal. Keluar 1 kalau ada temuan | `python tools\cek_bersih.py [--istilah Konfigurasi\istilah_pribadi.txt] [--gitleaks <gitleaks.exe>]` |
| `medusa` | Pindai keamanan konfigurasi agent, hook, dan MCP | `tools\medusa-venv\Scripts\medusa.exe scan .` |
| `oper_kerja.py` | Oper tugas kecil ke agent gratis di git worktree, kumpulkan bukti, terapkan sesudah diperiksa. Baca skill `oper-kerja` dulu | `python tools\oper_kerja.py jalan --repo <repo> --tugas <berkas> --cek "<uji>"`, lalu `cek <id>`, `terapkan <id>`, `buang <id>` |
| `test_tools.py` | Pengujian unit untuk logika tools internal | `tools\rag-venv\Scripts\python.exe tools\test_tools.py` |
| `playwright-venv` | Python dengan Playwright 1.64.1 untuk skill `webapp-testing` dan `webapp-audit`. Browsernya Edge terpasang, jadi jangan jalankan `playwright install` | `tools\playwright-venv\Scripts\python.exe <skrip.py>` |
| `axe-core` | Mesin uji aksesibilitas (WCAG) yang disuntikkan ke halaman yang sedang jalan | `tools\axe-core\axe.min.js`, dimuat otomatis oleh `skills\webapp-audit\scripts\sweep_routes.py` |

---

## 3. Padanan

Skill yang hanya ada di Claude, dan penggantinya untuk agent lain. Penggantinya dicatat dari nama skill atau alatnya, belum diuji (unverified).

| Kebutuhan | Claude | Agent lain |
|---|---|---|
| Browser | `built-in-browser`, `chrome-browser` | `web-browser`, `webapp-testing` |
| Grafik | `dataviz` | `data-notebook` bagian 6 |
| PDF | `pdf` | `markitdown`, `pdf_parser.py`. Hermes: `pdf` |
| Word | `docx`, `docs`, `markdown-to-docx` | `markdown-to-docx`. Hermes: `docx` |
| Slide | `pptx` | `print-and-slides`. Hermes: `powerpoint` |
| Spreadsheet | `xlsx` | Python. Hermes: `xlsx` |
| Riset | `deep-research` | Belum ada. Hermes: `grounded-citations` |
