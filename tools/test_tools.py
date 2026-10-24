"""Tes kecil untuk logika tools (Aturan 6, anak tangga 7). Jalankan: tools/rag-venv/Scripts/python.exe tools/test_tools.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vault_guard as g

class PairedTest(unittest.TestCase):
    def setUp(self):
        import rag_eval  # butuh chromadb dari rag-venv
        self.t = rag_eval.paired_test

    def test_identical_is_one(self):
        self.assertEqual(self.t([0.5, 1, 0], [0.5, 1, 0]), 1.0)

    def test_exact(self):  # tiga selisih +1: hanya semua-plus dan semua-minus yang mencapai |3|, jadi 2/8
        self.assertAlmostEqual(self.t([1, 1, 1, 0.5], [0, 0, 0, 0.5]), 0.25)

    def test_monte_carlo(self):  # 20 selisih searah: p eksaknya 2/2^20
        self.assertLess(self.t([1] * 20, [0] * 20, rounds=20000), 0.001)

class VaultGuard(unittest.TestCase):
    V = os.path.join("D:" + os.sep, "Vault Uji")

    def test_inside(self):
        self.assertTrue(g.inside(os.path.join(self.V, "Log", "a.md"), self.V))
        self.assertFalse(g.inside(self.V + "2" + os.sep + "a.md", self.V))
        self.assertFalse(g.inside(os.path.join("C:" + os.sep, "a.md"), self.V))

    def test_reasons(self):
        self.assertEqual(g.reasons("Catatan biasa, 1460 chunk, 2026-10-21.", [], []), [])
        self.assertEqual(g.reasons("API_KEY=<kunci> dan TOKEN: [DISENSOR]", [], []), [])
        self.assertTrue(g.reasons("NIK 1234567890123456 di sini", [], []))
        self.assertEqual(g.reasons("NRP 1234567890 boleh sejak 2026-10-21", [], []), [])
        self.assertTrue(g.reasons("JWT_SECRET=abcd1234efgh", [], []))
        self.assertTrue(g.reasons("nilainya s3cr3t-panjang", [], ["s3cr3t-panjang"]))
        self.assertTrue(g.reasons("Ditulis oleh Nama Uji Lengkap", ["nama uji lengkap"], []))

    def test_new_text_only(self):
        ti = {"old_string": "1234567890123456", "new_string": "<nik>", "edits": [{"new_string": "aman"}]}
        self.assertEqual(g.reasons(g.new_text(ti), [], []), [])

class ProjectActivity(unittest.TestCase):
    def test_stale_and_unpaged(self):
        import time, tempfile, vault_lint
        with tempfile.TemporaryDirectory() as d:
            vault, root, old = os.path.join(d, "vault"), os.path.join(d, "code"), time.time() - 3 * 86400
            def put(path, text="x", mtime=None):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w", encoding="utf-8").write(text)
                if mtime:
                    os.utime(path, (mtime, mtime))
            page = os.path.join(vault, "Wiki", "projects", "P.md")
            put(page, "**Folder log di vault:** `Log/P/`", old)
            put(os.path.join(vault, "Log", "P", "a.md"), mtime=old)
            put(os.path.join(root, "P", "main.py"))                       # berubah hari ini, log 3 hari lalu
            put(os.path.join(root, "Q", "x.py"))                          # aktif tanpa halaman
            put(os.path.join(root, "R", ".no-vault"))                     # keluar dari vault
            put(os.path.join(root, "P", "node_modules", "y.js"))          # dilewati
            stale, unpaged = vault_lint.project_activity(vault, root, {"P": (page, open(page, encoding="utf-8").read())})
            self.assertEqual([s[0] for s in stale], ["P"])
            self.assertEqual([u[0] for u in unpaged], ["Q"])

if __name__ == "__main__":
    unittest.main()
