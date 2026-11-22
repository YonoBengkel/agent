# Asal Isi webapp-testing

Folder ini adalah skill `webapp-testing` dari repo resmi Anthropic, disesuaikan untuk Windows dan Edge yang sudah terpasang. Diambil 2026-11-03 atas izin pemilik workspace asal kit ini. Semua agent bisa membacanya, bukan hanya Claude.

## Sumber

- Repo: https://github.com/anthropics/skills, folder `skills/webapp-testing`, commit `ca45fc4` (main, 2026-10-28). Perubahan terakhir di folder itu ada di commit `ef74077` (2025-12-01).
- Lisensi folder: Apache-2.0 (`LICENSE.txt`, © 2026 Anthropic, PBC). Repo induknya tidak punya satu lisensi untuk semua skill.
- Cara ambil: enam berkas (22.394 byte) diunduh satu per satu dari raw.githubusercontent.com ke folder scratch yang kosong. Hash blob git setiap berkas cocok dengan tree commit di atas.
- Hasil pemeriksaan: kodenya hanya memakai standard library dan Playwright. Tidak ada panggilan jaringan selain cek port `localhost`, dan tidak ada instruksi tersembunyi untuk agent.

## Isi

| Path | Asal | Diubah? |
|---|---|---|
| `LICENSE.txt` | sama | Tidak |
| `SKILL.md` | sama | Ya, lihat di bawah |
| `scripts/with_server.py` | sama | Ya |
| `examples/console_logging.py`, `examples/element_discovery.py`, `examples/static_html_automation.py` | sama | Ya, hanya cara meluncurkan browser dan path keluaran |
| `SOURCE.md` | Dibuat kita | Berkas baru |

## Perubahan oleh Kita (Apache-2.0 §4b)

- **Browser:** `p.chromium.launch(channel="msedge", headless=True, timeout=90_000)`. Edge sudah terpasang, jadi `playwright install` tidak perlu dan tidak ada unduhan browser ke `C:`. Batas waktu dinaikkan karena Edge headless bisa lambat saat start pertama.
- **Profil sementara:** skrip mengarahkan `TEMP` dan `TMP` ke `tools\playwright-venv\tmp`, jadi profil Edge sementara buatan Playwright ada di folder workspace.
- **Path keluaran:** `/tmp` dan `/mnt/user-data/outputs` milik lingkungan Linux diganti folder kerja saat ini. URL `file://` dibuat dengan `Path.as_uri()` supaya sah di Windows.
- **`with_server.py`:**
  - Saat berhenti, seluruh pohon proses server dimatikan (`taskkill /T` di Windows, grup proses di POSIX). Versi asli hanya mematikan shell, sehingga `node` milik `npm run dev` tetap jalan dan port tetap terpakai.
  - Keluaran server dibuang, atau ditulis ke `--log-dir`. Versi asli menampungnya di pipe yang tidak pernah dibaca, sehingga server yang banyak menulis log bisa macet saat pipe penuh.
  - Menolak port yang sudah terpakai. Di mesin ini 5173, 8000, dan 8001 sering dipakai sesi lain, dan versi asli akan menganggap server siap padahal yang menjawab adalah server lain.
  - Berhenti menunggu kalau proses server keluar sebelum port terbuka.
  - Keluarannya sendiri di-line-buffer. Tanpa itu, saat stdout berupa pipe, baris "Server ready" bisa tercetak sesudah keluaran tes dan terbaca seolah tes jalan sebelum server siap.
- **`SKILL.md`:** bagian setup untuk workspace ini, perintah dengan Python venv, dan rujukan ke `webapp-audit` serta axe-core.

## Batas yang Diketahui

- Kalau `with_server.py` sendiri dimatikan paksa (misalnya kena batas waktu tool agent), blok pembersihannya tidak jalan. Sesudah run yang terputus, cek port dengan `Get-NetTCPConnection -LocalPort <port> -State Listen`.
- Memperbarui dari upstream: unduh ulang dengan cara yang sama, bandingkan diff-nya, lalu terapkan lagi perubahan di atas.
