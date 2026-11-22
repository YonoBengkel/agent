# Skill di kit dan lisensinya

Enam skill ini disalin `pasang.py` ke folder `skills\` di workspace. Hanya skill yang lisensinya
membolehkan disebarkan yang ikut. Path pribadi di dalamnya sudah diganti `<workspace>` atau
`<HERMES_HOME>`.

| Skill | Asal | Lisensi |
|---|---|---|
| `obsidian-workflow` | buatan pemilik kit | sama dengan repo ini |
| `oper-kerja` | buatan pemilik kit | sama dengan repo ini |
| `webapp-audit` | buatan pemilik kit. Teks lensa di `references/product-lenses.md` diadaptasi dari `apoorvjain25/production-audit`, nama lajur uji dari `shinpr/claude-code-workflows` | MIT untuk teks lensa (pemberitahuannya di akhir `product-lenses.md`) |
| `grill-me` | Matt Pocock | MIT (`LICENSE`) |
| `grilling` | Matt Pocock | MIT (`LICENSE`) |
| `webapp-testing` | `anthropics/skills`, disesuaikan untuk Windows dan Edge | Apache-2.0 (`LICENSE.txt`, perubahan dicatat di `SOURCE.md`) |

Repo ini belum punya berkas LICENSE, jadi tanyakan ke pemiliknya sebelum memakai ulang bagian buatan
pemilik kit di luar kit.

Skill lain di lumbung pemilik kit tidak ikut: sebagian buatan pihak ketiga tanpa lisensi yang
jelas, sebagian memuat aset bermerek dagang, dan sebagian terikat akun pribadi.

`webapp-testing` dan `webapp-audit` butuh venv Playwright (perintahnya di baris pertama
`tools\requirements\playwright-venv.txt`) dan memakai Microsoft Edge yang sudah terpasang.
`webapp-audit` juga butuh `tools\axe-core\axe.min.js` dari paket npm `axe-core` (MPL-2.0),
yang tidak ikut kit.
