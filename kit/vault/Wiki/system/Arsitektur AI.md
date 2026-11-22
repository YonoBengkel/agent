# Arsitektur AI

> Susunan ekosistem agent di mesin ini: aturan, memori, tools, skill, dan penjaga, serta bagaimana bagian-bagiannya saling terhubung.

Terkait dengan: [[Obsidian Workflow]], [[Tools CLI]], [[LLM Wiki Pattern]]

## Lapisan

| Lapisan | Isi | Tempat |
|---|---|---|
| Aturan | protokol folder kerja dan aturan lengkap workspace, satu sumber dengan salinan per platform | `AGENTS.md` di folder kerja dan workspace, salinan ditulis `sync_rules.py` |
| Memori | vault [[Obsidian]] ini: `hot.md`, `index.md`, `KONTEKS_PROYEK.md`, wiki, dan log sesi | `{{VAULT}}` |
| Tools | skrip CLI Python, dipanggil agent mana pun lewat terminal | `tools/` di workspace, daftar di [[Tools CLI]] |
| Skill | `SKILL.md` yang dimuat sesuai kebutuhan lewat peta kemampuan | `skills/` di workspace |
| Penjaga | hook sebelum alat jalan: vault, folder yang dilindungi, referensi desain, repo pihak ketiga | konfigurasi tiap platform, ditulis `pasang.py` |

## Prinsip

1. **Netral-vendor.** Aturan di `AGENTS.md`, memori di vault, tools sebagai CLI, dan skill sebagai `SKILL.md`, supaya pengetahuan tidak hilang saat berganti agent. Pola memorinya mengikuti [[LLM Wiki Pattern]].
2. **Dipaksa sistem lebih kuat dari instruksi.** Aturan yang penting diubah menjadi cek (hook, lint, tes), lalu diuji di sesi nyata. Hasil uji penjaga dicek dengan `uji_penjaga.py`.
3. **Tool mati secara default** (Aturan 7). Model RAG hanya dimuat saat indexing atau pencarian.

## Platform yang dipasang

Dicatat `pasang.py` di [[001 Pemasangan Kit]]. Setiap platform yang dipakai sebaiknya punya halaman di `Wiki/entities/` yang mencatat apa yang dimatikan, alasannya, dan cara menyalakannya lagi (Aturan 7).
