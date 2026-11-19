# Perawatan Peta Skills dan Tools

> Catatan perawatan untuk `PETA_SKILLS_TOOLS.md`: cara tiap operator mengakses skill dan tool, serta cara menambah atau mengubah baris peta. Tidak perlu dibaca saat memilih skill. Dipindah dari peta utama pada 2026-11-19 atas permintaan Ilham, supaya peta yang dibaca agent lebih ringan.

## Matriks status akses lintas operator

| Operator | Cara Mengakses Skills | Cara Mengakses Tools CLI |
|---|---|---|
| **Claude Code** | - Native di `~/.claude/skills/`<br>- Lewat peta (JIT): baca `SKILL.md` dari `D:\CODE\AI Agent\skills\` | Lewat tool terminal (`Bash`) |
| **Antigravity IDE** | - Native di `.agents/skills/` dan `~/.gemini/config/skills/`<br>- Lewat peta (JIT): baca `SKILL.md` dari `D:\CODE\AI Agent\skills\` | Lewat tool terminal (`run_command`) |
| **Zed Editor** | - Native di `.agents/skills/` dan `~/.agents/skills/`<br>- Lewat peta (JIT): baca `SKILL.md` dari `D:\CODE\AI Agent\skills\` (via tool baca berkas `read_file`; jika di luar proyek, otomatis fallback via terminal `Get-Content` sesuai izin umum Ilham) | Lewat tool terminal (`terminal` bawaan Zed) |
| **OpenCode** | - Native di konfigurasi `opencode.json` atau `.agents/skills/`<br>- Lewat peta (JIT): baca `SKILL.md` dari `D:\CODE\AI Agent\skills\` | Lewat tool terminal (`bash`) |
| **Hermes Agent** | - Native: skill bawaan Hermes di `D:\Hermes\skills\`<br>- Lewat peta (JIT): baca `SKILL.md` dari `D:\CODE\AI Agent\skills\` dengan tool berkas Hermes. Lumbung sengaja tidak dipasang sebagai `skills.external_dirs`, karena Hermes tidak melindungi folder itu dari penambalan skill | Lewat tool terminal (`terminal`) |

## Menambah atau mengubah skill dan tool

Setiap baris di `PETA_SKILLS_TOOLS.md` diuji oleh `python tools\uji_peta.py` (sejak 2026-11-08). Baris baru masuk ke sini hanya sesudah ujinya lulus.

1. **Skill baru:** `SKILL.md` dengan frontmatter `name` yang sama dengan nama folder, dan `description`. Path yang dirujuk harus ada, skrip harus lolos cek sintaks, dan skrip yang punya logika diberi `test_*.py`. Tulis netral platform, tanpa nama alat satu platform.
2. **Tool baru:** tambahkan uji asapnya di fungsi `uji_tool` di `tools\uji_peta.py`. Tanpa itu, baris tool baru dilaporkan GAGAL.
3. **Jalankan** `python tools\uji_peta.py` sampai tidak ada GAGAL. Opsi `--berat` ikut menjalankan uji pagar oper-kerja.
4. **Uji rute** untuk skill yang mirip dengan skill lain: minta agent memilih skill dari peta untuk satu tugas contoh, dan pastikan pilihannya tepat.
5. **Komit:** skill dari folder `skills\` ke `agent-skills`, tool lewat repo `YonoBengkel/agent`.
6. **Sub-peta:** kelompok skill yang hanya dipakai untuk satu jenis tugas cukup satu baris di peta utama, dengan path ke sub-peta, contohnya `animate/animate.md` (keputusan Ilham 2026-11-19). Sub-peta memakai tabel bagian `## 1.` yang sama, dan `uji_peta.py` ikut membaca dan menguji skill di dalamnya.
