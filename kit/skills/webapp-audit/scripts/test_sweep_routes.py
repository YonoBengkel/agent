"""Tes kecil sweep_routes.py: cacat yang sudah diketahui harus tertangkap, halaman bersih harus lolos (Aturan 6, anak tangga 7).
Jalankan: "<workspace>/tools/playwright-venv/Scripts/python.exe" "<workspace>/skills/webapp-audit/scripts/test_sweep_routes.py"
"""
import functools
import http.server
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sweep_routes as s

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class Sweep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=FIXTURES))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        entries = s.sweep(cls.base, ["/cacat.html", "/bersih.html"], widths=[360], themes=["light", "dark"], forbid=["error"])
        cls.v = {(e["route"], e["theme"]): e for e in entries}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_defects_found(self):
        e = self.v[("/cacat.html", "light")]
        self.assertNotIn("error", e)
        self.assertGreater(e["overflow_px"], 100)
        self.assertTrue(any("lebar" in x for x in e["sticking_out"]), e["sticking_out"])
        self.assertFalse(any("gulir" in x for x in e["sticking_out"]))   # di dalam wadah gulir: bukan luberan halaman
        self.assertTrue(any('"Tutup" 20x20' in x for x in e["small_target_samples"]), e["small_target_samples"])
        ids = {v["id"] for v in e["axe_violations"]}
        self.assertTrue({"color-contrast", "button-name"} <= ids, ids)
        self.assertTrue(e["banned_words"] and e["banned_words"][0].startswith("error"), e["banned_words"])
        self.assertTrue(any("galat uji" in c for c in e["console_errors"]), e["console_errors"])
        self.assertTrue(any(h.startswith("404 GET") and "/api/data" in h for h in e["http_errors"]), e["http_errors"])

    def test_clean_page_passes(self):
        for theme in ("light", "dark"):
            e = self.v[("/bersih.html", theme)]
            with self.subTest(theme=theme):
                self.assertNotIn("error", e)
                self.assertEqual(e["overflow_px"], 0)
                self.assertEqual(e["small_targets"], 0, e["small_target_samples"])
                self.assertEqual(e["axe_violations"], [])
                self.assertEqual(e["banned_words"], [])
                self.assertEqual(e["console_errors"] + e["page_errors"] + e["failed_requests"] + e["http_errors"], [])

    def test_blocked_backend(self):
        e = s.sweep(self.base, ["/cacat.html"], widths=[360], themes=["light"], block_url="**/api/**")[0]
        self.assertEqual(e["blocked_requests"], 1)
        self.assertFalse(any("/api/data" in x for x in e["failed_requests"] + e["http_errors"]))
        self.assertFalse(any("ERR_INTERNET_DISCONNECTED" in x for x in e["console_errors"]))


if __name__ == "__main__":
    unittest.main()
