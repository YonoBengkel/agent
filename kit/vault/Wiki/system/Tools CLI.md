# Tools CLI

> Daftar tool CLI di workspace agent, tabel kebutuhan ke alat yang sudah ada (Aturan 6, anak tangga 2), dan perintah lengkap yang dirujuk langkah Kompilasi.

Terkait dengan: [[Arsitektur AI]], [[Obsidian Workflow]], [[Pelajaran]]

## Kebutuhan ke alat

Semua perintah dijalankan dari folder workspace `{{WORKSPACE}}`. Daftar skill dan tool yang lebih rinci ada di `PETA_SKILLS_TOOLS.md` di workspace.

| Kebutuhan | Alat |
|---|---|
| Cari halaman di vault atau folder dokumen lain | `rag_engine.py search "<kata kunci>"` lewat Python di `tools/rag-venv`, `index "<folder>"` untuk folder baru |
| Ukur kualitas pencarian RAG | `rag_eval.py` |
| Cek kesehatan vault: berkas kosong, BOM, link putus, halaman yatim, path mati, secret, teks terlarang | `vault_lint.py "<vault>" --secrets-from .env --words Konfigurasi/penjaga_vault_terlarang.txt` |
| Salin aturan ke semua agent, cek terjemahan | `sync_rules.py`, `--check`, `--stamp <cermin>` |
| Muat halaman proyek di awal sesi | `session_context.py` (hook) |
| Tolak data pribadi dan secret di tulisan ke vault, tutup folder yang dilindungi | `vault_guard.py` (hook) |
| Tahan berkas tampilan baru sampai [[Referensi Desain]] dibaca | `penjaga_desain.py` (hook) |
| Tolak clone repo pihak ketiga ke folder kerja | `penjaga_repo.py` (hook) |
| Uji hidup penjaga yang terpasang | `uji_penjaga.py` (perintah lengkap di bawah) |
| Arsipkan transkrip sesi dengan sensor secret | `export_transcript.py` (hook Stop Claude Code, perintah agent lain di bawah) |
| Wajibkan subagent menyebut model, ingatkan saat kembali ke sesi besar sesudah jeda lama | `penjaga_subagent.py` dan `penahan_jeda.py` (hook Claude Code) |
| Cari proses alat yang masih hidup sesudah uji | `cek_proses_sisa.py --sejak 3h` (juga hook Stop Claude Code) |
| Ingatkan agent mencatat log kalau berkas proyek berubah | `cek_jurnal.py` (hook Stop Claude Code) |
| Pindahkan entri bulan lalu dari `log.md` dan `log_id.md` ke `Riwayat/` | `putar_log.py --vault "<vault>"` |
| Cadangkan vault ke repo git privatnya sesudah dipindai bersih | `cadangkan_vault.py --vault "<vault>" --words Konfigurasi/penjaga_vault_terlarang.txt --secrets-from .env` |
| Ubah PDF berstruktur jadi teks | `pdf_parser.py` |
| Oper tugas kode kecil ke agent lain di git worktree | `oper_kerja.py`, skill `oper-kerja` |
| Uji setiap skill dan tool di peta kemampuan | `uji_peta.py` |
| Cek repo workspace bersih dari secret dan data pribadi sebelum push | `cek_bersih.py` |
| Perbarui kit sesudah `git pull` di workspace | klik dua kali `siapkan.cmd` |
| Jalankan tes logika tools | `test_tools.py` lewat Python di `tools/rag-venv` |

Alat yang ada di repo tapi tidak dipasang `pasang.py`: `laporan_harian.py` (tugas terjadwal Windows), `uji_agen.py` (uji perilaku lintas agent), dan `ukur_token.py` (ukur token Claude Code). Pakai kalau dibutuhkan, dan catat di halaman ini.

## Perintah lengkap

Uji hidup penjaga yang terpasang, dijalankan di langkah 1 Kompilasi. Setiap baris `GAGAL` dilaporkan ke {{NAMA}}:

```
{{UJI_PENJAGA}}
```

Arsip transkrip Antigravity dan Hermes, yang tidak punya hook Stop:

```
python tools/export_transcript.py --format antigravity --app-dir "{{HOME_POSIX}}/.gemini/antigravity" --projects-root "{{FOLDER_KERJA_POSIX}}" --skip "{{NAMA_WORKSPACE}}" --out "Riwayat Perckapan" --secrets-from .env
python tools/export_transcript.py --format hermes --state-db "{{HERMES_HOME_POSIX}}/state.db" --projects-root "{{FOLDER_KERJA_POSIX}}" --skip "{{NAMA_WORKSPACE}}" --out "Riwayat Perckapan" --secrets-from .env
```

Pencarian RAG dari folder mana pun:

```
"{{WORKSPACE}}\tools\rag-venv\Scripts\python.exe" "{{WORKSPACE}}\tools\rag_engine.py" search "<kata kunci>"
```
