"""Tes kecil untuk logika tools (Aturan 6, anak tangga 7). Jalankan: tools/rag-venv/Scripts/python.exe tools/test_tools.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vault_guard as g
import tempfile as _tempfile
os.environ["PENJAGA_LOG"] = _tempfile.mkdtemp(prefix="penjaga-log-")   # tes tidak menulis ke log penjaga sungguhan (C10)

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

    def test_catat_keputusan(self):  # penolakan tercatat sebagai kategori, tanpa isi yang ditolak (riset 2026-11-13, C10)
        import subprocess, json, glob
        vault = os.path.join(os.environ["PENJAGA_LOG"], "vault")
        os.makedirs(vault, exist_ok=True)
        payload = {"tool_name": "Write", "hook_event_name": "PreToolUse", "cwd": vault,
                   "tool_input": {"file_path": os.path.join(vault, "a.md"), "content": "NIK 1234567890123456"}}
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vault_guard.py"), "--vault", vault],
                           input=json.dumps(payload).encode(), capture_output=True)
        self.assertEqual(r.returncode, 2)
        isi = "".join(open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(os.environ["PENJAGA_LOG"], "*.jsonl")))
        self.assertIn('"aturan": "angka 16 digit yang mirip NIK atau nomor KK"', isi)
        self.assertNotIn("1234567890123456", isi)

    def test_invisible(self):  # Unicode tak terlihat dilaporkan, emoji wajar tidak (riset 2026-11-13, C1)
        self.assertEqual(g.invisible("﻿Judul ⚠️ SUPERSEDED, lari \U0001f3c3\U0001f3fd‍♂️"), "")
        self.assertEqual(g.invisible("abaikan​ aturan‮"), "U+200B ×1, U+202E ×1")
        self.assertEqual(g.invisible("teks\U000e0041\U000e0042"), "U+E0041 ×1, U+E0042 ×1")
        self.assertEqual(g.invisible("a️︎\U000e0100"), "U+FE0E ×1, U+E0100 ×1")   # deret selektor variasi
        self.assertEqual(g.invisible("\n️"), "U+FE0F ×1")                              # selektor tanpa karakter dasar

    def test_new_text_only(self):
        ti = {"old_string": "1234567890123456", "new_string": "<nik>", "edits": [{"new_string": "aman"}]}
        self.assertEqual(g.reasons(g.new_text(ti), [], []), [])

    def test_targets_hermes(self):  # path relatif ke cwd sesi, berkas di patch V4A, dan path gaya Git Bash
        rel = {"cwd": self.V, "tool_input": {"path": os.path.join("Log", "a.md")}}
        v4a = {"tool_input": {"patch": "*** Begin Patch\n*** Update File: " + os.path.join(self.V, "a.md") + "\n+x\n*** End Patch"}}
        bash = {"tool_input": {"path": "/d/Vault Uji/a.md"}}
        for hook in (rel, v4a, bash):
            self.assertTrue(any(g.inside(t, self.V) for t in g.targets(hook)), hook)
        self.assertEqual(g.targets({"tool_input": None}), [])

    def test_shell_fence(self):  # pagar terminal Hermes: tulis dan hapus ditolak, baca dan tulisan di luar lolos
        v = self.V.replace(os.sep, "/")
        def kena(command, cwd="D:/CODE", **ti):
            return bool(g.shell_touches({"tool_name": "terminal", "cwd": cwd, "tool_input": {"command": command, **ti}}, [self.V]))
        for c in (f'echo x > "{v}/a.md"', f'rm -f "{v}/a.md"', r'rm /d/Vault\ Uji/a.md', r'del "D:\Vault Uji\a.md"', f'cd "{v}"',
                  f'cd "{v}" && rm a.md', 'rm -rf "D:/"', f'ls "{v}" | xargs rm', f'V="{v}"; rm "$V/a.md"', f'sed -i s/a/b/ "{v}/a.md"',
                  f'find "{v}" -delete', f'''bash -c "rm '{v}/a.md'"''', f'Remove-Item "{v}/a.md"'):
            self.assertTrue(kena(c), c)
        for c in (f'ls "{v}" 2>/dev/null', f'cat "{v}/a.md" 2>&1', f'grep -r "a > b" "{v}" > /tmp/o', f'echo "rm {v}/a.md"',
                  'echo x > /tmp/o', 'rm -f D:/CODE/a.txt', f'rm "{v}2/a.md"', f'''bash -c "cat '{v}/a.md'"''', ''):
            self.assertFalse(kena(c), c)
        self.assertTrue(kena("rm a.md", cwd=v))
        self.assertTrue(kena("ls", workdir=v))
        self.assertEqual(g.shell_touches({"tool_name": "terminal", "tool_input": None}, [self.V]), [])
        kode = {"tool_name": "execute_code", "tool_input": {"code": f"open('{v}/a.md', 'w')"}}
        self.assertTrue(g.shell_touches(kode, [self.V]))
        self.assertFalse(g.shell_touches({"tool_name": "execute_code", "tool_input": {"code": "print(1)"}}, [self.V]))

    def test_protect_closes_reads(self):  # vault pribadi di Hermes: baca dan tulis ditolak, termasuk lewat folder induknya
        p = "D:/Vault Pribadi"
        def kena(tool, cwd="D:/CODE", **ti):
            return bool(g.opened({"tool_name": tool, "cwd": cwd, "tool_input": ti}, [p]))
        for c in (f'cat "{p}/a.md"', f'ls "{p}"', f'grep -r x "{p}"', r'type "D:\Vault Pribadi\a.md"', r'cat /d/Vault\ Pribadi/a.md',
                  r'cat /mnt/d/Vault\ Pribadi/a.md', f'git -C "{p}" log', f'''bash -c "cat '{p}/a.md'"''',
                  f'''python -c "print(open('{p}/a.md').read())"''', f'cat "{p}"/*.md', 'grep -r x "D:/"', 'find / -name a.md',
                  'ls D:/Vault*/', '''bash -c "grep -r x 'D:/'"''', f'Get-Content -Path "{p}/a.md"'):
            self.assertTrue(kena("terminal", command=c), c)
        for c in ('cat "D:/CODE/a.txt"', 'ls', 'grep -r x "D:/CODE"', f'cat "{p}2/a.md"', 'dir /d /b', 'cmd /d /c dir', 'echo halo', ''):
            self.assertFalse(kena("terminal", command=c), c)
        self.assertTrue(kena("terminal", command="ls", cwd=p))
        for tool, ti in (("read_file", {"path": f"{p}/a.md"}), ("read_file", {"path": "a.md", "cwd": p}), ("search_files", {"pattern": "x", "path": "D:/"}),
                         ("search_files", {"pattern": "x", "cwd": p}), ("search_files", {"pattern": f"{p}/**", "target": "files"}),
                         ("browser_navigate", {"url": "file:///D:/Vault%20Pribadi/a.html"}), ("vision_analyze", {"image_url": f"{p}/a.png", "question": "apa"}),
                         ("web_extract", {"urls": [f"file:///{p}/a.html"]}), ("execute_code", {"code": f"open('{p}/a.md').read()"}),
                         ("execute_code", {"code": "import os; list(os.walk('D:/'))"}), ("execute_code", {"code": f'open(r"{p}/a.md")'}),
                         ("execute_code", {"code": 'list(os.walk(r"D:/"))'}), ("write_file", {"path": f"{p}/a.md", "content": "x"})):
            self.assertTrue(kena(tool, **ti), (tool, ti))
        for tool, ti in (("read_file", {"path": "D:/CODE/a.md"}), ("search_files", {"pattern": "x"}), ("search_files", {"pattern": "x", "path": "D:/CODE"}),
                         ("web_extract", {"urls": ["https://example.com/a"]}), ("execute_code", {"code": "print(1)"}),
                         ("write_file", {"path": "D:/CODE/a.md", "content": f"lihat {p}"})):
            self.assertFalse(kena(tool, **ti), (tool, ti))
        self.assertEqual(g.opened({"tool_name": "terminal", "tool_input": None}, [p]), [])
        self.assertEqual(g.opened({"tool_name": "Read", "tool_input": {"file_path": f"{p}/a.md"}}, []), [])  # Claude tanpa --protect

    def test_worker_refusal(self):  # pekerja oper_kerja: hanya alat berkas, dan hanya di folder sesinya
        akar = os.path.join("D:" + os.sep, "Oper", "1", "kerja")
        def tolak(tool, folder=akar, **ti):
            return g.worker_refusal({"tool_name": tool, "cwd": "D:/gateway", "tool_input": ti}, folder)
        for tool, ti in (("read_file", {"path": "a.md"}), ("read_file", {"path": f"{akar}/sub/a.md"}), ("search_files", {"pattern": "x"}),
                         ("write_file", {"path": "a.md", "content": "x"}),
                         ("patch", {"mode": "patch", "patch": "*** Begin Patch\n*** Update File: a.py\n*** End Patch"})):
            self.assertIsNone(tolak(tool, **ti), (tool, ti))
        for tool, ti in (("read_file", {"path": "D:/CODE/a.md"}), ("read_file", {"path": "../a.md"}), ("read_file", {"path": "~/.ssh/id_rsa"}),
                         ("read_file", {"path": "/d/CODE/a.md"}), ("read_file", {"path": "sub/../../a.md"}), ("search_files", {"pattern": "x", "path": "D:/"}),
                         ("write_file", {"path": "D:/CODE/a.md", "content": "x"}), ("patch", {"path": "../a.py", "old_string": "a", "new_string": "b"}),
                         ("patch", {"patch": "*** Add File: ../a.py"}), ("patch", {"patch": "*** Delete File: ../a.py"}),
                         ("patch", {"patch": "*** Move File: a.py -> ../../b.py"}), ("patch", {"patch": "*** Update File: a.py\n*** Move to: ../b.py"}),
                         ("patch", {"patch": "***Add   File:../a.py"}), ("patch", {"patch": "*** Move File: a.py->../b.py"}),
                         ("read_file", {"path": "D:a.md"}), ("read_file", {"path": "C:a.md"}), ("search_files", {"pattern": "x", "path": "a.py, D:/CODE"}),
                         ("search_files", {"pattern": "x", "path": "a.py D:/CODE"}),
                         ("read_file", {"path": ".env"}), ("read_file", {"path": "sub/kunci.PEM"}), ("write_file", {"path": ".env.lokal", "content": "x"}),
                         ("terminal", {"command": "dir"}), ("execute_code", {"code": "print(1)"}), ("web_extract", {"urls": ["https://example.com"]})):
            self.assertTrue(tolak(tool, **ti), (tool, ti))
        self.assertTrue(tolak("read_file", folder=None, path="a.md"))  # folder sesi tidak ketemu: tolak, jangan lolos
        import tempfile
        with tempfile.TemporaryDirectory() as t:  # path pencarian yang ada boleh, walau memuat spasi
            os.mkdir(os.path.join(t, "sub folder"))
            self.assertIsNone(g.worker_refusal({"tool_name": "search_files", "tool_input": {"pattern": "x", "path": "sub folder"}}, t))

    def test_worker_main(self):  # hook sungguhan dengan state.db tiruan, seperti yang dijalankan gateway
        import json, sqlite3, subprocess, tempfile
        skrip = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vault_guard.py")
        with tempfile.TemporaryDirectory() as t:
            tugas, kerja, vault = os.path.join(t, "oper", "1"), os.path.join(t, "oper", "1", "kerja"), os.path.join(t, "Vault")
            os.makedirs(kerja)
            os.makedirs(vault)
            open(os.path.join(tugas, "tugas.md"), "w").close()
            db = sqlite3.connect(os.path.join(t, "state.db"))
            db.execute("CREATE TABLE sessions (id TEXT, cwd TEXT)")
            db.executemany("INSERT INTO sessions VALUES (?, ?)", [("pekerja", kerja), ("biasa", vault)])
            db.commit()
            db.close()
            def kode(sesi, tool, *opsi, **ti):
                masuk = json.dumps({"hook_event_name": "pre_tool_call", "session_id": sesi, "cwd": t, "tool_name": tool, "tool_input": ti})
                return subprocess.run([sys.executable, "-B", skrip, "--vault", vault, *opsi], input=masuk.encode("utf-8"), capture_output=True,
                                      env={**os.environ, "HERMES_HOME": t}).returncode
            self.assertEqual(kode("pekerja", "read_file", "--worker", path="a.py"), 0)
            self.assertTrue(os.path.exists(os.path.join(tugas, "pagar-aktif")))
            self.assertEqual(kode("pekerja", "read_file", "--worker", path=os.path.join(t, "rahasia.md")), 2)
            self.assertEqual(kode("pekerja", "terminal", "--worker", command="dir"), 2)
            self.assertEqual(kode("hilang", "read_file", "--worker", path="a.py"), 2)
            self.assertEqual(kode("biasa", "read_file", path=os.path.join(t, "lain.md")), 0)  # sesi biasa tidak terkunci
            # path relatif dinilai dari folder sesi, bukan folder gateway. Nomor palsu ini tidak boleh lolos ke vault
            self.assertEqual(kode("biasa", "write_file", path="a.md", content="NIK 1234567890123456"), 2)

    def test_session_cwd(self):  # payload Hermes membawa folder gateway, folder sesi yang benar ada di state.db
        import sqlite3, tempfile
        with tempfile.TemporaryDirectory() as home:
            db = sqlite3.connect(os.path.join(home, "state.db"))
            db.execute("CREATE TABLE sessions (id TEXT, cwd TEXT)")
            db.execute("INSERT INTO sessions VALUES ('s1', 'D:/Kerja')")
            db.commit()
            db.close()
            asli = os.environ.get("HERMES_HOME")
            os.environ["HERMES_HOME"] = home
            try:
                kait = {"hook_event_name": "pre_tool_call", "session_id": "s1"}
                self.assertEqual(g.session_cwd(kait), "D:/Kerja")
                self.assertIsNone(g.session_cwd({**kait, "session_id": "lain"}))
                self.assertIsNone(g.session_cwd({**kait, "hook_event_name": "PreToolUse"}))  # Claude Code: payload-nya sudah benar
            finally:
                os.environ.pop("HERMES_HOME") if asli is None else os.environ.__setitem__("HERMES_HOME", asli)
        self.assertEqual(g.targets({"cwd": "D:/Kerja", "tool_input": {"path": "a.md"}}), [os.path.join("D:/Kerja", "a.md")])

class OperKerja(unittest.TestCase):
    def setUp(self):
        import oper_kerja
        self.o = oper_kerja

    def test_baca_hasil_agen(self):
        h = self.o.baca_hermes(['{"type":"text","text":"a"}', "bukan json", '{"type":"result","text":" selesai ","tokens":9,"exit_code":0}'])
        self.assertEqual((h["teks"], h["token"], h["kode"]), ("selesai", 9, 0))
        o = self.o.baca_opencode(['{"type":"text","part":{"text":"satu"}}', '{"type":"step_finish","part":{"tokens":{"input":2,"output":3,"cache":{"read":4}}}}',
                                  '{"type":"step_finish","part":{"tokens":{"input":1,"output":1}}}', '{"type":"error","error":{"name":"FreeUsageLimitError"}}'])
        self.assertEqual(o["teks"], "satu")
        self.assertEqual(o["token"], {"input": 3, "output": 4, "cache": 4})
        self.assertEqual(o["kode"], 1)

    def test_izin_ketat(self):  # pekerja OpenCode tidak boleh dapat shell, web, atau folder di luar worktree
        i = self.o.izin_opencode()
        self.assertEqual((i["*"], i["external_directory"]), ("deny", "deny"))
        self.assertFalse({"bash", "webfetch", "websearch", "task"} & set(i))
        self.assertEqual(i["read"]["*.env"], "deny")
        perintah, env, _ = self.o.perintah_opencode("D:/x", None)
        self.assertNotIn("--auto", perintah)
        self.assertEqual(env["OPENCODE_DISABLE_CLAUDE_CODE"], "1")
        perintah, env, _ = self.o.perintah_hermes("D:/oper/1/kerja", None, "D:/q.txt")
        self.assertEqual(perintah[perintah.index("-t") + 1], "file")
        self.assertEqual(perintah[perintah.index("-p") + 1], self.o.PROFIL_HERMES)
        self.assertNotIn("HERMES_WRITE_SAFE_ROOT", env)  # lewat klien, nilai ini bisa ikut mengunci sesi biasa di gateway yang sama

    def test_pagar_harus_terbukti(self):  # Hermes selesai tanpa jejak hook: hasilnya tidak dipakai
        import json, pathlib, sys, tempfile
        keluaran = json.dumps({"type": "result", "text": "selesai", "tokens": {}, "exit_code": 0})
        tiruan = lambda kerja, model, berkas: ([sys.executable, "-c", f"print({keluaran!r})"], None, self.o.baca_hermes)
        lama = self.o.perintah_hermes, self.o.penjaga_hermes_aktif, self.o.urllib.request.urlopen
        self.o.perintah_hermes, self.o.penjaga_hermes_aktif, self.o.urllib.request.urlopen = tiruan, lambda home: True, lambda *a, **k: None
        def pulihkan():
            self.o.perintah_hermes, self.o.penjaga_hermes_aktif, self.o.urllib.request.urlopen = lama
        self.addCleanup(pulihkan)
        with tempfile.TemporaryDirectory() as t:
            folder = pathlib.Path(t)
            self.assertEqual(self.o.jalankan_agen("hermes", t, folder, "tugas", None, 30)["kode_keluar"], "pagar tidak terbukti")
            (folder / "pagar-aktif").touch()
            self.assertEqual(self.o.jalankan_agen("hermes", t, folder, "tugas", None, 30)["kode_keluar"], 0)

    def test_di_luar_izin(self):
        self.assertEqual(self.o.di_luar_izin(["a.py", "t/b.py"], ["a.py"]), ["t/b.py"])
        self.assertEqual(self.o.di_luar_izin(["a.py"], []), [])

    def test_penjaga_hermes(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as h:
            self.assertFalse(self.o.penjaga_hermes_aktif(h))
            perintah = 'python "x/vault_guard.py" --vault "v" --worker'
            with open(os.path.join(h, "config.yaml"), "w", encoding="utf-8") as f:
                f.write("command: '" + perintah + "'\n")
            with open(os.path.join(h, "shell-hooks-allowlist.json"), "w", encoding="utf-8") as f:
                json.dump({"approvals": [{"event": "pre_tool_call", "command": perintah + " --lama"}]}, f)
            self.assertFalse(self.o.penjaga_hermes_aktif(h))  # perintah di config berubah sesudah disetujui
            with open(os.path.join(h, "shell-hooks-allowlist.json"), "w", encoding="utf-8") as f:
                json.dump({"approvals": [{"event": "pre_tool_call", "command": perintah}]}, f)
            self.assertTrue(self.o.penjaga_hermes_aktif(h))

    def test_alur(self):  # repo sungguhan dengan agent tiruan: folder utama tidak tersentuh sampai diterapkan
        import argparse, contextlib, io, json, pathlib, subprocess, tempfile
        def git(*a):
            subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
        def tiruan(agen, kerja, folder, kueri, model, batas):
            (kerja / "baru.txt").write_text("halo", encoding="utf-8")
            return {"agen": agen, "kode_keluar": 0, "teks": "selesai", "detik": 0}
        asli, self.o.jalankan_agen = self.o.jalankan_agen, tiruan
        self.addCleanup(setattr, self.o, "jalankan_agen", asli)
        with tempfile.TemporaryDirectory() as t:
            repo, akar = pathlib.Path(t, "repo"), pathlib.Path(t, "oper")
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            git("config", "user.name", "uji")
            git("config", "user.email", "uji@contoh.test")
            (repo / "a.txt").write_text("a", encoding="utf-8")
            git("add", "-A")
            git("commit", "-qm", "awal")
            tugas = pathlib.Path(t, "tugas.md")
            tugas.write_text("Tambah berkas.", encoding="utf-8")
            a = argparse.Namespace(repo=str(repo), tugas=str(tugas), agen="opencode", model=None, cek="git status --short", boleh=["a.txt"],
                                   batas=9, akar=str(akar), secrets_from=[])
            keluar = io.StringIO()
            with contextlib.redirect_stdout(keluar):
                self.o.jalan(a)
            h = json.loads(keluar.getvalue())
            self.assertEqual((h["status"], h["berkas"], h["di_luar_izin"], h["folder_utama_berubah"]), ("selesai", ["baru.txt"], ["baru.txt"], False))
            self.assertNotIn("cek", h)  # kode buatan pekerja tidak jalan sebelum patch-nya dibaca
            self.assertFalse((repo / "baru.txt").exists())
            b = argparse.Namespace(id=h["id"], akar=str(akar), tanpa_uji=False)
            keluar = io.StringIO()
            with contextlib.redirect_stdout(keluar):
                self.o.cek(b)
            self.assertEqual(json.loads(keluar.getvalue())["cek"]["kode_keluar"], 0)
            berkas_git = pathlib.Path(h["folder"], "kerja", ".git")  # pekerja mengganti .git: git tidak boleh dijalankan di sana
            asli_git = berkas_git.read_text(encoding="utf-8")
            def timpa(isi):  # berkas ini tersembunyi di Windows, dan mode w ditolak untuk berkas tersembunyi
                with open(berkas_git, "r+", encoding="utf-8") as f:
                    f.write(isi)
                    f.truncate()
            timpa("gitdir: palsu\n")
            with self.assertRaises(SystemExit):
                self.o.cek(b)
            timpa(asli_git)
            with contextlib.redirect_stdout(io.StringIO()):
                self.o.terapkan(b)
                self.o.buang(b)
            self.assertTrue((repo / "baru.txt").exists())
            self.assertFalse(pathlib.Path(h["folder"], "kerja").exists())
            self.assertTrue(pathlib.Path(h["folder"], "perubahan.patch").exists())
            tugas.write_text("NIK 1234567890123456", encoding="utf-8")  # isi palsu: tugas terkirim ke penyedia model gratis
            with self.assertRaises(SystemExit):
                self.o.jalan(a)
            tugas.write_text("Tambah berkas.", encoding="utf-8")
            (repo / ".no-vault").write_text("", encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.o.jalan(a)

class UjiPeta(unittest.TestCase):
    def test_spesifikasi_skill(self):  # batas spesifikasi Agent Skills jadi peringatan (riset 2026-11-13, C7)
        import tempfile, pathlib, uji_peta as u
        self.assertEqual(u.frontmatter("---\nname: a\ndescription: >\n  baris satu\n  baris dua\nlicense: MIT\n---\n")["description"],
                         "baris satu baris dua")
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "contoh-skill" / "SKILL.md"
            f.parent.mkdir()
            f.write_text("---\nname: contoh-skill\ndescription: " + "x" * 1030 + "\n---\nIsi.\n", encoding="utf-8")
            h = u.uji_skill(pathlib.Path("contoh-skill") / "SKILL.md", pathlib.Path(d), pathlib.Path(d) / "tidak-ada")
            self.assertEqual(h.status, u.PERINGATAN)
            self.assertTrue(any("1030 karakter" in c for c in h.catatan))

    def test_baca_peta(self):  # baris skill dan tool dibaca dari tabel bagian 1 dan 2, bagian lain diabaikan
        import uji_peta
        peta = """## 1. Peta Skills
| Nama Skill | Kapan | Path Berkas | Operator |
|---|---|---|---|
| `contoh` | uji | `contoh/SKILL.md` | Universal |
## 2. Peta Tools CLI
| Nama Tool | Fungsi | Perintah |
|---|---|---|
| `alat.py` | uji | `python alat.py` |
## 3. Matriks
| `bukan` | x | y |
"""
        self.assertEqual(uji_peta.baca_peta(peta), ([("contoh", "contoh/SKILL.md")], ["alat.py"]))
        self.assertEqual(uji_peta.frontmatter("---\nname: contoh\ndescription: >\n  uji\n---\n# isi")["name"], "contoh")
        self.assertEqual(uji_peta.uji_tool("alat-baru.py", ".", False).status, uji_peta.GAGAL)  # tool tanpa uji asap ditolak

class SessionContext(unittest.TestCase):
    def test_project_name(self):
        import session_context as s
        root = os.path.join("D:" + os.sep, "CODE")
        self.assertEqual(s.project_name(root, os.path.join(root, "Con-Fore", "web")), "Con-Fore")
        self.assertIsNone(s.project_name(root, root))
        self.assertIsNone(s.project_name(root, os.path.join("D:" + os.sep, "KULIAH")))

    def test_design_line(self):  # baris kontrak desain ditaruh paling atas, jadi tidak ikut terpotong (2026-11-08)
        import json, subprocess, tempfile
        import session_context as s
        with tempfile.TemporaryDirectory() as t:
            vault, root = os.path.join(t, "Vault"), os.path.join(t, "CODE")
            for d in (os.path.join(vault, "Wiki", "system"), os.path.join(vault, "Wiki", "projects"), os.path.join(root, "Toko")):
                os.makedirs(d)
            with open(os.path.join(vault, "Wiki", "system", "Referensi Desain.md"), "w", encoding="utf-8") as f:
                f.write("# RD\n\n## Kontrak desain proyek\n\n| Proyek | Berkas | Arah |\n|---|---|---|\n"
                        "| [[Toko]] | `DESIGN.md` | Hangat |\n\n## Lain\n\n| [[Lain]] | x | y |\n")
            with open(os.path.join(vault, "Wiki", "projects", "Toko.md"), "w", encoding="utf-8") as f:
                f.write("# Toko\n" + "isi panjang\n" * 2000)
            ctx = s.project_context(root, vault, "Toko")
            self.assertLess(len(ctx), 10000)
            self.assertLess(ctx.index("Hangat"), ctx.index("isi panjang"))
            self.assertIsNone(s.design_line(vault, "Lain"))  # baris di luar tabel kontrak tidak dibaca
            skrip = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_context.py")
            def agy(folder):
                masuk = json.dumps({"workspacePaths": [folder]}).encode("utf-8")
                r = subprocess.run([sys.executable, "-B", skrip, "--format", "antigravity", "--projects-root", root, "--vault", vault],
                                   input=masuk, capture_output=True)
                return json.loads(r.stdout)
            self.assertIn("Hangat", agy(os.path.join(root, "Toko"))["injectSteps"][0]["systemMessage"]["systemMessage"])
            self.assertEqual(agy(t), {})  # di luar folder proyek: tanpa konteks, tapi tetap JSON

    def test_hermes_kata_izin(self):  # isi vault ke model Hermes hanya sesudah `pakai konteks` (2026-11-11)
        import json, sqlite3, subprocess, tempfile
        with tempfile.TemporaryDirectory() as t:
            vault, root, home = os.path.join(t, "Vault"), os.path.join(t, "CODE"), os.path.join(t, "Hermes")
            for d in (os.path.join(vault, "Wiki", "projects"), os.path.join(root, "Toko"), os.path.join(root, "Rahasia"), home):
                os.makedirs(d)
            with open(os.path.join(vault, "Wiki", "projects", "Toko.md"), "w", encoding="utf-8") as f:
                f.write("# Toko\n\nisi halaman proyek toko\n")
            open(os.path.join(root, "Rahasia", ".no-vault"), "w").close()
            db = sqlite3.connect(os.path.join(home, "state.db"))
            db.execute("CREATE TABLE sessions (id TEXT, cwd TEXT)")
            db.executemany("INSERT INTO sessions VALUES (?, ?)", [("s1", os.path.join(root, "Toko")), ("s2", os.path.join(root, "Rahasia"))])
            db.commit()
            db.close()
            skrip = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_context.py")
            def hermes(sesi, pesan, pertama):
                masuk = json.dumps({"hook_event_name": "pre_llm_call", "session_id": sesi, "cwd": home,
                                    "extra": {"user_message": pesan, "is_first_turn": pertama}}).encode("utf-8")
                r = subprocess.run([sys.executable, "-B", skrip, "--format", "hermes", "--projects-root", root, "--vault", vault],
                                   input=masuk, capture_output=True, env=dict(os.environ, HERMES_HOME=home))
                return json.loads(r.stdout)["context"] if r.stdout.strip() else None
            awal = hermes("s1", "tolong cek kode toko", True)
            self.assertIn("pakai konteks", awal)
            self.assertNotIn("isi halaman proyek toko", awal)   # giliran pertama tanpa izin: tanpa isi vault
            self.assertIsNone(hermes("s1", "lanjut", False))
            self.assertIn("isi halaman proyek toko", hermes("s1", "oke, Pakai konteks ya", False))
            self.assertIn(".no-vault", hermes("s2", "halo", True))   # proyek .no-vault: hanya larangannya

    def test_commit_warning(self):  # komit yang lebih baru dari catatan vault diberi satu baris peringatan (2026-11-10)
        import subprocess, tempfile, time
        import session_context as s
        with tempfile.TemporaryDirectory() as t:
            vault, repo = os.path.join(t, "Vault"), os.path.join(t, "CODE", "Toko")
            os.makedirs(os.path.join(vault, "Wiki", "projects"))
            os.makedirs(repo)
            page = os.path.join(vault, "Wiki", "projects", "Toko.md")
            with open(page, "w", encoding="utf-8") as f:
                f.write("# Toko\n\nisi\n")
            self.assertEqual(s.commit_warning(vault, repo, "Toko", page, "isi"), "")   # belum repo git
            git = ["git", "-C", repo, "-c", "user.name=uji", "-c", "user.email=uji@contoh.test"]
            subprocess.run(git[:3] + ["init", "-q"], check=True)
            with open(os.path.join(repo, "a.txt"), "w") as f:
                f.write("a")
            subprocess.run(git + ["add", "a.txt"], check=True)
            subprocess.run(git + ["commit", "-q", "-m", "fitur keranjang"], check=True)
            lama = time.time() - 3 * 86400
            os.utime(page, (lama, lama))
            w = s.commit_warning(vault, repo, "Toko", page, "isi")
            self.assertIn("1 komit", w)
            self.assertIn("fitur keranjang", w)
            log = os.path.join(vault, "Log", "Toko")
            os.makedirs(log)
            with open(os.path.join(log, "001 sesi.md"), "w", encoding="utf-8") as f:
                f.write("# sesi\n")
            self.assertEqual(s.commit_warning(vault, repo, "Toko", page, "isi"), "")   # log hari ini menghitung sebagai catatan

class PenjagaDesain(unittest.TestCase):
    def test_wajib_referensi(self):
        import tempfile
        import penjaga_desain as d
        with tempfile.TemporaryDirectory() as root:
            for p in ("Toko", "Rahasia"):
                os.makedirs(os.path.join(root, p))
            open(os.path.join(root, "Rahasia", ".no-vault"), "w").close()
            open(os.path.join(root, "Toko", "index.html"), "w").close()
            self.assertEqual(d.wajib_referensi(os.path.join(root, "Toko", "promo.html"), root), ("Toko", "berkas tampilan baru"))
            self.assertIsNone(d.wajib_referensi(os.path.join(root, "Toko", "index.html"), root))  # mengubah berkas lama boleh
            self.assertEqual(d.wajib_referensi(os.path.join(root, "Toko", "DESIGN.md"), root), ("Toko", "DESIGN.md"))
            self.assertIsNone(d.wajib_referensi(os.path.join(root, "Toko", "app.py"), root))
            self.assertIsNone(d.wajib_referensi(os.path.join(root, "Rahasia", "promo.html"), root))  # proyek .no-vault
            self.assertIsNone(d.wajib_referensi(os.path.join(root, "lepas.html"), root))  # bukan milik proyek mana pun

    def test_hook(self):  # dua format sungguhan: riwayat baca dari state.db tiruan (Hermes) dan transkrip tiruan (Antigravity)
        import json, sqlite3, subprocess, tempfile
        skrip = os.path.join(os.path.dirname(os.path.abspath(__file__)), "penjaga_desain.py")
        with tempfile.TemporaryDirectory() as t:
            root, vault, toko = os.path.join(t, "CODE"), os.path.join(t, "Vault"), os.path.join(t, "CODE", "Toko")
            os.makedirs(toko)
            db = sqlite3.connect(os.path.join(t, "state.db"))
            db.execute("CREATE TABLE sessions (id TEXT, cwd TEXT)")
            db.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, tool_calls TEXT)")
            db.execute("INSERT INTO sessions VALUES ('s1', ?)", (toko,))
            db.commit()
            transkrip = os.path.join(t, "transcript_full.jsonl")
            open(transkrip, "w").close()
            def jalan(fmt, payload):
                r = subprocess.run([sys.executable, "-B", skrip, "--format", fmt, "--projects-root", root, "--vault", vault],
                                   input=payload.encode("utf-8"), capture_output=True, env={**os.environ, "HERMES_HOME": t})
                return r.returncode, r.stdout.decode("utf-8")
            hermes = json.dumps({"hook_event_name": "pre_tool_call", "session_id": "s1", "cwd": t, "tool_name": "write_file",
                                 "tool_input": {"path": "promo.html", "content": "<p>promo</p>"}})
            agy = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": os.path.join(toko, "promo.html")}},
                              "workspacePaths": [toko], "transcriptPath": transkrip})
            self.assertEqual(jalan("hermes", hermes)[0], 2)  # path relatif dinilai dari folder sesi di state.db
            self.assertEqual(json.loads(jalan("antigravity", agy)[1])["decision"], "deny")
            lampiran = os.path.join(vault, "Wiki", "system", "Lampiran Referensi Desain.md")  # bukan halaman utama
            db.execute("INSERT INTO messages (session_id, role, tool_calls) VALUES ('s1', 'assistant', ?)",
                       (json.dumps([{"function": {"name": "read_file", "arguments": json.dumps({"path": lampiran})}}]),))
            db.commit()
            with open(transkrip, "w", encoding="utf-8") as f:
                f.write(json.dumps({"step_index": 1, "tool_calls": [{"name": "read_file", "args": {"Path": lampiran}}]}) + "\n")
            self.assertEqual(jalan("hermes", hermes)[0], 2)
            self.assertEqual(json.loads(jalan("antigravity", agy)[1])["decision"], "deny")
            baca = os.path.join(vault, "Wiki", "system", "Referensi Desain.md")
            db.execute("INSERT INTO messages (session_id, role, tool_calls) VALUES ('s1', 'assistant', ?)",
                       (json.dumps([{"function": {"name": "read_file", "arguments": json.dumps({"path": baca})}}]),))
            db.commit()
            db.close()
            with open(transkrip, "w", encoding="utf-8") as f:
                f.write(json.dumps({"step_index": 1, "tool_calls": [{"name": "read_file", "args": {"Path": baca}}]}) + "\n")
            self.assertEqual(jalan("hermes", hermes)[0], 0)
            self.assertEqual(json.loads(jalan("antigravity", agy)[1])["decision"], "allow")
            design = os.path.join(toko, "DESIGN.md")
            open(design, "w").close()
            hermes_md = lambda teks: json.dumps({"hook_event_name": "pre_tool_call", "session_id": "s1", "cwd": t, "tool_name": "patch",
                                                 "tool_input": {"path": "DESIGN.md", "old_string": "[[Lama]]", "new_string": teks}})
            agy_md = lambda teks: json.dumps({"toolCall": {"name": "edit_file", "args": {"Path": design, "Target": "[[Lama]]",
                                                                                          "Replacement": teks}},
                                              "workspacePaths": [toko], "transcriptPath": transkrip})
            self.assertEqual(jalan("hermes", hermes_md("- [[Design Kit]]"))[0], 2)  # nama halaman vault tidak boleh masuk DESIGN.md
            self.assertEqual(jalan("hermes", hermes_md("- majoo (majoo.id)"))[0], 0)  # teks lama yang dihapus tidak ikut dinilai
            self.assertEqual(json.loads(jalan("antigravity", agy_md("- [[Design Kit]]"))[1])["decision"], "deny")
            self.assertEqual(json.loads(jalan("antigravity", agy_md("- majoo (majoo.id)"))[1])["decision"], "allow")
            self.assertEqual(json.loads(jalan("antigravity", "bukan json")[1])["decision"], "allow")  # gagal memeriksa berarti lolos
            self.assertEqual(jalan("hermes", "bukan json")[0], 0)

    def test_hook_claude(self):  # format claude: riwayat baca dari transkrip Claude (blok tool_use Read)
        import json, subprocess, tempfile
        skrip = os.path.join(os.path.dirname(os.path.abspath(__file__)), "penjaga_desain.py")
        with tempfile.TemporaryDirectory() as t:
            root, vault, toko = os.path.join(t, "CODE"), os.path.join(t, "Vault"), os.path.join(t, "CODE", "Toko")
            os.makedirs(toko)
            transkrip = os.path.join(t, "sesi.jsonl")
            def baris(path):
                return json.dumps({"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": path}}]}}) + "\n"
            def jalan(tool, **ti):
                masuk = json.dumps({"hook_event_name": "PreToolUse", "cwd": toko, "transcript_path": transkrip,
                                    "tool_name": tool, "tool_input": ti})
                return subprocess.run([sys.executable, "-B", skrip, "--format", "claude", "--projects-root", root, "--vault", vault],
                                      input=masuk.encode("utf-8"), capture_output=True).returncode
            with open(transkrip, "w", encoding="utf-8") as f:
                f.write(baris(os.path.join(vault, "Wiki", "system", "Lampiran Referensi Desain.md")))
            self.assertEqual(jalan("Write", file_path=os.path.join(toko, "promo.html"), content="<p>x</p>"), 2)
            with open(transkrip, "a", encoding="utf-8") as f:
                f.write(baris(os.path.join(vault, "Wiki", "system", "Referensi Desain.md")))
            self.assertEqual(jalan("Write", file_path="promo.html", content="<p>x</p>"), 0)  # path relatif dari cwd
            self.assertEqual(jalan("Edit", file_path=os.path.join(toko, "DESIGN.md"), old_string="a", new_string="- [[Design Kit]]"), 2)
            self.assertEqual(jalan("MultiEdit", file_path=os.path.join(toko, "DESIGN.md"),
                                   edits=[{"old_string": "a", "new_string": "- majoo (majoo.id)"}]), 0)

class EksporAgenLain(unittest.TestCase):
    def test_antigravity_dan_hermes(self):  # arsip transkrip agent selain Claude (2026-11-10)
        import json, sqlite3, subprocess, tempfile, pathlib
        skrip = os.path.join(os.path.dirname(os.path.abspath(__file__)), "export_transcript.py")
        with tempfile.TemporaryDirectory() as t:
            root, out, app, cli = os.path.join(t, "CODE"), os.path.join(t, "arsip"), os.path.join(t, "agy"), os.path.join(t, "agy-cli")
            toko, rahasia = os.path.join(root, "Toko"), os.path.join(root, "Rahasia")
            for d in (toko, rahasia, app, cli):
                os.makedirs(d)
            open(os.path.join(rahasia, ".no-vault"), "w").close()
            # App mencatat c1, c2, c3; CLI mencatat c1 yang sama dengan transkrip lebih panjang, yang harus dipilih.
            for folder, isi in ((app, (("c1", toko), ("c2", rahasia), ("c3", os.path.join(t, "KULIAH")))), (cli, (("c1", toko),))):
                db = sqlite3.connect(os.path.join(folder, "conversation_summaries.db"))
                db.execute("CREATE TABLE conversation_summaries (conversation_id TEXT, title TEXT, workspace_uris TEXT, nesting_depth INTEGER)")
                for cid, ws in isi:
                    db.execute("INSERT INTO conversation_summaries VALUES (?, ?, ?, 0)", (cid, "Judul " + cid, json.dumps([pathlib.Path(ws).as_uri()])))
                    logs = os.path.join(folder, "brain", cid, ".system_generated", "logs")
                    os.makedirs(logs)
                    with open(os.path.join(logs, "transcript_full.jsonl"), "w", encoding="utf-8") as f:
                        f.write(json.dumps({"type": "USER_INPUT", "created_at": "2026-11-10T01:00:00Z",
                                            "content": "<USER_REQUEST>halo API_KEY=rahasia123</USER_REQUEST><ADDITIONAL_METADATA>jam</ADDITIONAL_METADATA>"}) + "\n")
                        f.write(json.dumps({"type": "PLANNER_RESPONSE", "content": "jawab", "tool_calls": [{"name": "read_file", "args": {"Path": "a"}}]}) + "\n")
                        if folder == cli:
                            f.write(json.dumps({"type": "PLANNER_RESPONSE", "content": "lanjutan dari CLI"}) + "\n")
                db.commit()
                db.close()
            sdb = os.path.join(t, "state.db")
            db = sqlite3.connect(sdb)
            db.execute("CREATE TABLE sessions (id TEXT, title TEXT, cwd TEXT, started_at REAL, parent_session_id TEXT)")
            db.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, tool_calls TEXT)")
            db.execute("INSERT INTO sessions VALUES ('h1', 'Sesi', ?, 1794200000, NULL)", (toko,))
            db.execute("INSERT INTO messages (session_id, role, content) VALUES ('h1', 'user', 'tugas')")
            db.commit()
            db.close()
            def jalan(*a):
                return subprocess.run([sys.executable, "-B", skrip, "--out", out, "--projects-root", root, *a], capture_output=True, text=True).returncode
            self.assertEqual(jalan("--format", "antigravity", "--app-dir", app, "--app-dir", cli), 0)
            self.assertEqual(jalan("--format", "hermes", "--state-db", sdb), 0)
            self.assertEqual(sorted(os.listdir(out)), ["Toko"])  # .no-vault dan folder di luar root dilewati
            berkas = os.listdir(os.path.join(out, "Toko"))
            self.assertEqual(len(berkas), 2)
            isi = open(os.path.join(out, "Toko", next(b for b in berkas if "Antigravity" in b)), encoding="utf-8").read()
            self.assertNotIn("rahasia123", isi)
            self.assertNotIn("ADDITIONAL_METADATA", isi)
            self.assertIn("lanjutan dari CLI", isi)   # transkrip terlengkap yang dipakai, satu berkas per percakapan

class UjiAgen(unittest.TestCase):  # canary lintas agent dengan skor N dari M (2026-11-10)
    def test_baca_agy_dan_nilai(self):
        import json, uji_agen as u
        def langkah(nama, par, state="DONE", galat=""):
            info = {"parameters": par, **({"error": {"message": galat}} if galat else {})}
            return json.dumps({"step_update": {"step_type": "tool", "state": state, "tool_name": nama, "tool_info": info}})
        vault = "D:/Vault Uji"
        teks = "\n".join([
            langkah("view_file", {"AbsolutePath": "D:\\Vault Uji\\Wiki\\system\\Lampiran Referensi Desain.md"}),  # lampiran tidak dihitung
            langkah("write_to_file", {"TargetFile": "D:\\CODE\\uji-agen-a\\promo.html"}, "ERROR", "denied by pre-tool hook"),
            langkah("view_file", {"AbsolutePath": "D:\\Vault Uji\\Wiki\\system\\Referensi Desain.md"}),
            langkah("write_to_file", {"TargetFile": "D:\\CODE\\uji-agen-a\\promo.html"}),
            "bukan json",
            json.dumps({"event": "result", "result": {"usage": {"total_tokens": 1234}, "response": "selesai"}})])
        alat, ringkas = u.baca_agy(teks)
        self.assertEqual([n for n, _ in alat], ["view_file", "write_to_file (ditolak)", "view_file", "write_to_file"])
        self.assertEqual(ringkas["token"], 1234)
        n = u.nilai(alat, "agy", vault, u.DESIGN)
        self.assertTrue(n["ref_dibaca"] and n["promo_dibuat"])
        self.assertFalse(n["desain_sebelum_ref"])   # tulisan yang ditolak penjaga tidak dihitung sebagai keputusan
        self.assertEqual((n["ditolak_penjaga"], n["akses_vault"]), (1, 2))
        self.assertFalse(n["design_md_catat_ref"])   # templat bawaan belum mencatat apa pun
        self.assertTrue(u.catat_ref(u.DESIGN.replace("- Belum ada.", "- Situs contoh, https://contoh.test")))
        cepat = u.nilai([("write_to_file", "D:/CODE/uji-agen-a/promo.html"), ("view_file", vault + "/Wiki/system/Referensi Desain.md")], "agy", vault, "")
        self.assertTrue(cepat["desain_sebelum_ref"])

    def test_sah_dan_skor(self):
        import uji_agen as u
        self.assertFalse(u.sah([("run_command (galat)", "dir")], False))
        self.assertFalse(u.sah([], False))
        self.assertFalse(u.sah([("read_file", "a"), ("run_command (galat)", "dir vault")], False))   # berhenti di perintah yang ditolak
        self.assertTrue(u.sah([("write_to_file", "promo.html"), ("run_command (galat)", "dir")], True))   # tugas sudah selesai
        self.assertTrue(u.sah([("view_file", "a"), ("write_to_file", "b")], False))
        dasar = {"agen": "agy", "promo_dibuat": True, "ref_dibaca": True, "desain_sebelum_ref": False, "design_md_catat_ref": False, "akses_vault": 0}
        rows = [{**dasar, "repo": "a", "sah": True}, {**dasar, "repo": "a", "sah": True, "desain_sebelum_ref": True},
                {**dasar, "repo": "a", "sah": False}, {**dasar, "repo": "b", "sah": True, "akses_vault": 2}]
        hasil = u.skor(rows)
        self.assertIn("agy repo a: 2 run sah, 1 tidak sah", hasil)
        self.assertIn("  tidak sah: 1 masalah infrastruktur, 0 batas lingkungan uji", hasil)   # run tanpa alat sama sekali
        self.assertIn("  Referensi Desain dibaca sebelum keputusan desain: 1 dari 2 (Wilson 95%: 9% sampai 91%)", hasil)
        self.assertIn("  vault tidak disentuh (.no-vault): 0 dari 1 (Wilson 95%: 0% sampai 79%)", hasil)
        self.assertIn("  (kurang dari 5 run sah: belum cukup untuk klaim sebelum dan sesudah)", hasil)
        tiga = u.skor([{**dasar, "repo": "b", "sah": True}] * 3)   # 3 dari 3 masih cocok dengan keandalan 44% (riset C2)
        self.assertIn("  vault tidak disentuh (.no-vault): 3 dari 3 (Wilson 95%: 44% sampai 100%, pass^3 1.00)", tiga)

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
            put(os.path.join(root, "K", "tugas.ipynb"))                   # mata kuliah: sudah punya Log/Kuliah/K
            put(os.path.join(vault, "Log", "Kuliah", "K", "diskusi.md"))
            put(os.path.join(root, "R", ".no-vault"))                     # keluar dari vault
            put(os.path.join(root, "P", "node_modules", "y.js"))          # dilewati
            stale, unpaged = vault_lint.project_activity(vault, root, {"P": (page, open(page, encoding="utf-8").read())})
            self.assertEqual([s[0] for s in stale], ["P"])
            self.assertEqual([u[0] for u in unpaged], ["Q"])
            _, unpaged = vault_lint.project_activity(vault, root, {"P": (page, "")}, mentioned={"Q"})   # Q dirujuk dari log
            self.assertEqual(unpaged, [])

class ProjectDocs(unittest.TestCase):
    def test_stale_docs(self):
        import time, tempfile, vault_lint
        with tempfile.TemporaryDirectory() as d:
            month = time.time() - 30 * 86400
            def put(path, mtime=None):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w", encoding="utf-8").write("x")
                if mtime:
                    os.utime(path, (mtime, mtime))
            put(os.path.join(d, "A", "ARCHITECTURE.md"), month)   # kode hari ini, dokumen sebulan lalu
            put(os.path.join(d, "A", "app.py"))
            put(os.path.join(d, "A", "SCHEMA.md"))                # baru diperbarui
            put(os.path.join(d, "B", "ARCHITECTURE.md"), month)   # yang berubah hanya catatan .md
            put(os.path.join(d, "B", "app.py"), month)
            put(os.path.join(d, "B", "notes.md"))
            put(os.path.join(d, "C", "ARCHITECTURE.md"), month)   # keluar dari vault
            put(os.path.join(d, "C", "app.py"))
            put(os.path.join(d, "C", ".no-vault"))
            self.assertEqual([(n, doc) for n, doc, _, _ in vault_lint.stale_docs(d)], [("A", "ARCHITECTURE.md")])

class RuleBackup(unittest.TestCase):
    def test_sensor(self):  # konfigurasi terpasang dicadangkan ke vault tanpa nilai rahasia (2026-11-10)
        import sync_rules
        hasil = sync_rules.sensor(b'  api_key: sk-abc\n  key_env: NAMA\n"base_keymap": "VSCode",\n"OPENAI_API_KEY": "x"\n').decode()
        self.assertNotIn("sk-abc", hasil)
        self.assertNotIn('"x"', hasil)
        self.assertIn("key_env: NAMA", hasil)
        self.assertIn('"base_keymap": "VSCode"', hasil)

    def test_backup_and_check(self):
        import tempfile, sync_rules
        with tempfile.TemporaryDirectory() as d:
            src, mirror, conf = (os.path.join(d, n) for n in ("AGENTS.md", "AGENTS_id.md", "Konfigurasi"))
            os.makedirs(os.path.join(d, "Konfigurasi"))
            for p, t in ((src, "aturan"), (mirror, "cermin"), (os.path.join(conf, "rule_sync.json"), "{}"), (os.path.join(conf, "rahasia.txt"), "x")):
                open(p, "w", encoding="utf-8").write(t)
            out = os.path.join(d, "Cadangan Aturan")
            reg = {"syncs": [{"source": src}], "translations": [{"source": src, "mirror": mirror}],
                   "backup": {"dir": out, "folders": [conf], "exclude": ["rahasia.txt"]}}
            self.assertEqual(sync_rules.backup(reg, False), 0)
            self.assertTrue(os.path.exists(sync_rules.backup_path(out, src)))
            self.assertFalse(os.path.exists(sync_rules.backup_path(out, os.path.join(conf, "rahasia.txt"))))
            self.assertTrue(os.path.exists(os.path.join(out, ".no-vault")))
            self.assertEqual(sync_rules.backup(reg, True), 0)        # sudah sama
            open(src, "w", encoding="utf-8").write("aturan baru")
            self.assertEqual(sync_rules.backup(reg, True), 1)        # cadangan basi terdeteksi
            old = os.path.getmtime(src) - 86400
            os.utime(src, (old, old))                                 # skrip ganti nama yang mempertahankan tanggal lama
            self.assertEqual(sync_rules.backup(reg, False), 0)       # sumber berubah: salinan tetap diperbarui
            dst = sync_rules.backup_path(out, src)
            self.assertEqual(open(dst, encoding="utf-8").read(), "aturan baru")
            open(dst, "w", encoding="utf-8").write("disunting di Obsidian")
            open(src, "w", encoding="utf-8").write("aturan lebih baru")
            self.assertEqual(sync_rules.backup(reg, False), 1)       # salinan yang disunting dari luar tidak ditimpa
            self.assertEqual(open(dst, encoding="utf-8").read(), "disunting di Obsidian")

    def test_invisible_source_not_copied(self):  # sumber beracun tidak disalin ke salinan agent (riset 2026-11-13, C1)
        import tempfile, subprocess, json
        with tempfile.TemporaryDirectory() as d:
            src, copy, reg = (os.path.join(d, n) for n in ("AGENTS.md", "CLAUDE.md", "reg.json"))
            blok = "<!-- sync:begin inti -->\n{}\n<!-- sync:end -->\n"
            open(src, "w", encoding="utf-8").write(blok.format("aturan​ baru"))
            open(copy, "w", encoding="utf-8").write(blok.format("aturan lama"))
            json.dump({"syncs": [{"name": "inti", "source": src, "copies": [{"path": copy}]}]}, open(reg, "w", encoding="utf-8"))
            r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync_rules.py"),
                                "--registry", reg], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 1)
            self.assertIn("U+200B", r.stdout)
            self.assertIn("aturan lama", open(copy, encoding="utf-8").read())

    def test_batas_ukuran(self):  # batas lunak hanya peringatan, batas keras dihitung masalah (riset 2026-11-13, C7)
        import sync_rules
        self.assertEqual(sync_rules.cek_ukuran("x/CLAUDE.md", "baris\n" * 250), 0)
        self.assertEqual(sync_rules.cek_ukuran("x/GEMINI.md", "a" * 25 * 1024), 1)
        self.assertEqual(sync_rules.cek_ukuran("x/GEMINI.md", "a" * 1024), 0)
        self.assertEqual(sync_rules.cek_ukuran("x/SOUL.md", "a" * 99999), 0)   # tanpa batas yang diketahui

    def test_dot_folder_renamed(self):
        import sync_rules
        self.assertIn("dot-claude", sync_rules.backup_path("B", os.path.join("C:" + os.sep, "Users", "x", ".claude", "CLAUDE.md")))

class LogNumbering(unittest.TestCase):
    def test_missing_and_duplicate(self):
        import vault_lint
        log = os.path.join("D:" + os.sep, "V", "Log")
        paths = [os.path.join(log, "A", n) for n in ("001 satu.md", "002 dua.md", "tanpa nomor.md", "002 kembar.md")]
        paths += [os.path.join(log, "B", "002 lain folder.md"), os.path.join("D:" + os.sep, "V", "Wiki", "bebas.md")]
        missing, dup = vault_lint.log_numbering(paths, log)
        self.assertEqual([os.path.basename(p) for p in missing], ["tanpa nomor.md"])
        self.assertEqual([os.path.basename(p) for p in dup], ["002 kembar.md"])

class CekProsesSisa(unittest.TestCase):  # proses alat sisa uji dilaporkan hook Stop, sekali per proses (2026-11-10)
    def test_jenis(self):
        import cek_proses_sisa as c
        self.assertEqual(c.jenis(r"node D:\x\node_modules\vite\bin\vite.js --port 5173"), "vite")
        self.assertEqual(c.jenis("python -m http.server 8000"), "http.server")
        self.assertEqual(c.jenis(r'"C:\bin\agy.exe" -p tugas'), "agy")
        self.assertEqual(c.jenis(r"node D:\x\node_modules\next\dist\bin\next dev"), "next")
        self.assertIsNone(c.jenis(r'"C:\Program Files\Antigravity\Antigravity.exe" --type=renderer'))
        self.assertIsNone(c.jenis("notepad.exe catatan.txt"))
        # hook ekspor transkrip yang jalan bersamaan, dengan argumen ke folder 9router (salah tangkap 2026-11-10)
        self.assertIsNone(c.jenis(r'bash.exe -c "python \"D:/w/tools/export_transcript.py\" --secrets-from \"D:/w/9router/docker-compose.yml\""'))
        self.assertIsNone(c.jenis(r'python D:\w\tools\vault_lint.py v --secrets-from "D:\w\9router\docker-compose.yml"'))
        self.assertEqual(c.jenis(r'docker compose -f "D:\w\9router\docker-compose.yml" up'), "docker")
        self.assertEqual(c.jenis(r"node D:\w\9router\server.js"), "9router")
        # nilai argumen mirip rahasia disensor sebelum dicetak (2026-11-11)
        s = c.sensor(r"agy.exe --hub --csrf_token=abc123 --api-key def456 --mode=x API_TOKEN=\"g h\"")
        self.assertNotIn("abc123", s)
        self.assertNotIn("def456", s)
        self.assertNotIn("g h", s)
        self.assertIn("--mode=x", s)

    # Tabel proses tiruan: aplikasi (1) -> sesi ini (10) -> bash (11) -> hook (12); sesi lain (20) -> next dev (21)
    T = 1000.0
    PROSES = [
        {"i": 1, "o": 0, "n": "claude.exe", "t": 100, "c": "app"},
        {"i": 10, "o": 1, "n": "claude.exe", "t": 200, "c": "cli sesi"},
        {"i": 11, "o": 10, "n": "bash.exe", "t": 1100, "c": "bash"},
        {"i": 12, "o": 11, "n": "python.exe", "t": 1200, "c": "python cek_proses_sisa.py --hook"},
        {"i": 13, "o": 10, "n": "node.exe", "t": 1300, "c": r"node D:\w\node_modules\vite\bin\vite.js"},
        {"i": 14, "o": 99, "n": "node.exe", "t": 1400, "c": "node next dev"},          # induk 99 sudah mati
        {"i": 20, "o": 1, "n": "claude.exe", "t": 300, "c": "cli sesi lain"},
        {"i": 21, "o": 20, "n": "node.exe", "t": 1500, "c": "node next dev"},          # milik sesi lain
        {"i": 22, "o": 10, "n": "python.exe", "t": 900, "c": "python -m http.server"},  # lebih tua dari awal sesi
        {"i": 23, "o": 24, "n": "python.exe", "t": 1600, "c": "python -m uvicorn app:x"},
        {"i": 24, "o": 10, "n": "cmd.exe", "t": 1700, "c": "cmd"},                     # PID induk dipakai ulang sesudahnya
    ]

    def test_cari_asal(self):
        import cek_proses_sisa as c
        h = {x["pid"]: x for x in c.cari(self.PROSES, [{"p": 5173, "i": 13}], self.T, 12)}
        self.assertEqual(sorted(h), [13, 14, 21, 23])
        self.assertEqual((h[13]["asal"], h[13]["port"]), ("sesi ini", [5173]))
        self.assertEqual(h[14]["asal"], "yatim")
        self.assertEqual(h[21]["asal"], "lain")
        self.assertEqual(h[23]["asal"], "yatim")

    def test_hook_sekali(self):
        import tempfile
        import cek_proses_sisa as c
        with tempfile.TemporaryDirectory() as t:
            tr = os.path.join(t, "sesi.jsonl")
            with open(tr, "w") as f:
                f.write("{}\n")
            ambil = lambda sejak: self.PROSES
            dengar = lambda: [{"p": 5173, "i": 13}]
            payload = {"transcript_path": tr, "session_id": "uji"}
            asli = c.cari
            c.cari = lambda p, d, sejak, diri: asli(p, d, self.T, diri)   # waktu transkrip diganti T tabel tiruan
            try:
                out = c.hook(payload, os.path.join(t, "state"), ambil, dengar, diri=12)
                self.assertEqual(out["decision"], "block")
                self.assertIn("vite PID 13 port 5173", out["reason"])
                self.assertNotIn("PID 21", out["reason"])   # proses sesi lain tidak dilaporkan
                self.assertIsNone(c.hook(payload, os.path.join(t, "state"), ambil, dengar, diri=12))   # tidak diulang
                lagi = c.hook(dict(payload, session_id="uji2", stop_hook_active=True), os.path.join(t, "state"), ambil, dengar, diri=12)
                self.assertIn("systemMessage", lagi)   # sudah dilanjutkan hook Stop: hanya pesan ke pengguna
            finally:
                c.cari = asli

class LessonIndex(unittest.TestCase):  # pelajaran baru wajib masuk Indeks per area (2026-11-10)
    def test_unindexed(self):
        import vault_lint
        page = ("# Pelajaran\n\n## Indeks per area\n\n- **Vault:** #1 a, #3 c\n\n## Daftar\n\n| # | Area |\n|---|---|\n"
                "| 1 | x |\n| 2 | y |\n| 3 | z |\n| 13 | w |\n")
        self.assertEqual(vault_lint.lessons_unindexed(page), ["#2", "#13"])   # #1 dan #3 tidak dihitung menyebut #13
        self.assertEqual(vault_lint.lessons_unindexed("# P\n\n## Daftar\n\n| 1 | x |\n"), ["halaman belum punya bagian Indeks per area"])

class PenjagaRepo(unittest.TestCase):  # repo pihak ketiga tidak boleh di-clone ke folder proyek tepercaya (2026-11-12)
    D = "D:" + os.sep
    ROOT, LUAR, PROYEK = os.path.join(D, "CODE"), os.path.join(D, "Repo Luar"), os.path.join(D, "CODE", "proyek")

    def args(self):
        import types
        return types.SimpleNamespace(projects_root=self.ROOT, repo_luar=self.LUAR, own_owner=["PemilikSaya"])

    def test_periksa(self):
        import penjaga_repo as r
        tolak = lambda cmd, base=self.PROYEK: r.periksa(cmd, base, self.args())
        self.assertIn("Repo Luar", tolak("git clone https://github.com/teman/alat.git"))
        self.assertIsNone(tolak("git clone https://github.com/PemilikSaya/agent"))                  # repo sendiri
        self.assertIsNone(tolak(r'git clone D:\Kiriman\alat.git "D:\Repo Luar\alat"'))              # tujuan benar
        self.assertIsNotNone(tolak("cd /d/CODE/proyek && git clone file:///d/Kiriman/alat.git", os.path.join(self.D, "x")))
        self.assertIsNotNone(tolak("git clone /d/Kiriman/alat.git /d/CODE/proyek-tmp"))
        self.assertIsNotNone(tolak('cp -a "D:/Repo Luar/alat/." D:/CODE/proyek/'))                # salinan dari repo luar
        self.assertIsNotNone(tolak(r'Copy-Item -Recurse "D:\Repo Luar\alat" D:\CODE\proyek'))
        self.assertIsNone(tolak("git clone https://github.com/teman/alat.git", os.path.join(self.D, "lain")))
        self.assertIsNotNone(tolak(r"git -C D:\CODE\proyek clone https://github.com/teman/x"))
        self.assertIsNotNone(tolak('bash -c "git clone https://gitlab.com/teman/x /d/CODE/y"'))
        self.assertIsNotNone(tolak("gh repo clone teman/alat"))
        self.assertIsNone(tolak("gh repo clone PemilikSaya/alat"))
        self.assertIsNotNone(tolak(r"git clone --depth 1 -b main https://github.com/teman/alat.git D:\CODE\x"))
        self.assertIsNone(tolak("git status && git log -1"))
        self.assertIsNone(tolak(r"git clone D:\CODE\proyek-a D:\CODE\proyek-b"))                 # salinan lokal milik sendiri

    def test_hook(self):  # format sungguhan: claude keluar 2, antigravity menjawab JSON dan keluar 0
        import json, subprocess
        skrip = os.path.join(os.path.dirname(os.path.abspath(__file__)), "penjaga_repo.py")
        opsi = ["--projects-root", self.ROOT, "--repo-luar", self.LUAR, "--own-owner", "PemilikSaya"]
        claude = {"tool_name": "Bash", "cwd": self.PROYEK, "tool_input": {"command": "git clone https://github.com/teman/alat"}}
        r = subprocess.run([sys.executable, "-B", skrip, "--format", "claude", *opsi], input=json.dumps(claude).encode(), capture_output=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("Repo Luar", r.stderr.decode("utf-8"))
        agy = {"toolCall": {"name": "run_command", "args": {"CommandLine": "git clone https://github.com/teman/alat"}},
               "workspacePaths": [self.PROYEK]}
        r = subprocess.run([sys.executable, "-B", skrip, "--format", "antigravity", *opsi], input=json.dumps(agy).encode(), capture_output=True)
        self.assertEqual((r.returncode, json.loads(r.stdout)["decision"]), (0, "deny"))
        lain = {"tool_name": "Read", "tool_input": {"file_path": "x"}}
        r = subprocess.run([sys.executable, "-B", skrip, "--format", "claude", *opsi], input=json.dumps(lain).encode(), capture_output=True)
        self.assertEqual(r.returncode, 0)

class CadangkanVault(unittest.TestCase):  # vault dipindai dulu sebelum dikirim ke repo git privatnya (2026-11-11)
    def test_pindai_lalu_commit(self):
        import subprocess, tempfile
        import cadangkan_vault as c
        with tempfile.TemporaryDirectory() as v:
            os.makedirs(os.path.join(v, ".obsidian"))
            with open(os.path.join(v, ".obsidian", "graph.json"), "w") as f:
                f.write('{"scale": 1.0542789475922718}')   # angka pengaturan grafik, bukan nomor identitas
            a = os.path.join(v, "a.json")
            with open(a, "w", encoding="utf-8") as f:
                f.write('{"kunci": "rahasia-uji-123456"}')   # cadangan konfigurasi: bukan .md, tetap dipindai
            self.assertEqual([r for r, _ in c.pindai(v, [], {"rahasia-uji-123456"})], ["a.json"])
            with open(a, "w", encoding="utf-8") as f:
                f.write('{"kunci": "<disensor>"}')
            self.assertEqual(c.pindai(v, [], {"rahasia-uji-123456"}), [])
            subprocess.run(["git", "-C", v, "init", "-q"], check=True)
            skrip = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cadangkan_vault.py")
            identitas = {k: "uji" for k in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME")}
            identitas.update({k: "uji@contoh.test" for k in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL")})
            r = subprocess.run([sys.executable, "-B", skrip, "--vault", v], capture_output=True, env=dict(os.environ, **identitas))
            self.assertIn("Belum ada remote", r.stdout.decode("utf-8"))
            log = subprocess.run(["git", "-C", v, "log", "--oneline"], capture_output=True).stdout.decode("utf-8")
            self.assertIn("cadangan vault", log)

class PutarLog(unittest.TestCase):  # log wiki diputar per bulan (2026-11-10)
    def test_putar_dan_ulang(self):
        import tempfile
        import putar_log
        with tempfile.TemporaryDirectory() as v:
            os.makedirs(os.path.join(v, "Wiki"))
            log = os.path.join(v, "Wiki", "log.md")
            with open(log, "w", encoding="utf-8", newline="") as f:
                f.write("# Wiki Log\n\n> kepala\n\nEarlier, by `tools/putar_log.py`: [[log 2026-01]].\n\n---\n\n## [2026-09-30] ingest | A\nisi a\n\n"
                        "## [2026-10-02] compile | B\nisi b\n\n## [2026-11-01] lint | C\nisi c\n")
            self.assertEqual(putar_log.putar(v, "log", "2026-11", tulis=False), {"2026-09": 1, "2026-10": 1})
            self.assertIn("isi a", open(log, encoding="utf-8").read())   # --cek tidak menulis
            putar_log.putar(v, "log", "2026-11")
            putar_log.putar(v, "log", "2026-11")   # jalan kedua tidak menggandakan apa pun
            sisa = open(log, encoding="utf-8").read()
            self.assertTrue(sisa.startswith("# Wiki Log\n\n> kepala"))
            self.assertIn("`tools/putar_log.py`: [[log 2026-09]], [[log 2026-10]].\n", sisa)   # daftar riwayat di kepala ikut segar
            self.assertNotIn("isi b", sisa)
            self.assertIn("## [2026-11-01] lint | C", sisa)
            okt = open(os.path.join(v, "Riwayat", "log 2026-10.md"), encoding="utf-8").read()
            self.assertEqual(okt.count("## [2026-10-02] compile | B"), 1)
            self.assertIn("[[log]]", okt)
            self.assertTrue(os.path.exists(os.path.join(v, "Riwayat", "log 2026-09.md")))

class UjiPenjaga(unittest.TestCase):  # penjaga terpasang diuji hidup lewat perintah hook-nya sendiri (2026-11-13)
    def test_baca_konfigurasi(self):  # Claude, Antigravity, dan bagian hooks Hermes saja: secret di luarnya tidak ikut terbaca
        import json, tempfile, uji_penjaga as u
        with tempfile.TemporaryDirectory() as t:
            claude, agy, hermes = (os.path.join(t, n) for n in ("settings.json", "hooks.json", "config.yaml"))
            with open(claude, "w", encoding="utf-8") as f:
                json.dump({"hooks": {"PreToolUse": [{"matcher": "Write|Edit", "hooks": [{"type": "command", "command": "python vault_guard.py"}]}],
                                     "Stop": [{"hooks": [{"type": "command", "command": "python lain.py"}]}]}}, f)
            with open(agy, "w", encoding="utf-8") as f:
                json.dump({"konteks": {"SessionStart": [{"type": "command", "command": "konteks.cmd"}]},
                           "repo": {"PreToolUse": [{"matcher": "run_command", "hooks": [{"type": "command", "command": "jaga.cmd"}]}]}}, f)
            with open(os.path.join(t, "jaga.cmd"), "w", encoding="utf-8") as f:
                f.write('@echo off\npython "D:\\x y\\penjaga_repo.py" --format antigravity\n')
            with open(hermes, "w", encoding="utf-8") as f:
                f.write("model:\n  api_key: rahasia-uji-111\nhooks:\n  pre_tool_call:\n    - matcher: \"terminal\"\n"
                        "      command: 'python \"D:/x y/penjaga_repo.py\" --format hermes'  # komentar\n      timeout: 20\n"
                        "  pre_llm_call:\n  - command: 'python konteks.py'\ngateway:\n  token: rahasia-uji-222\n")
            self.assertEqual([(h["matcher"], h["command"]) for h in u.baca_claude(claude)], [("Write|Edit", "python vault_guard.py")])
            self.assertEqual([h["command"] for h in u.baca_antigravity(agy)], ["jaga.cmd"])
            self.assertIn("penjaga_repo", u.teks_perintah({"command": "jaga.cmd"}, t))   # dikenali dari isi pembungkusnya
            harapan = [{"matcher": "terminal", "command": 'python "D:/x y/penjaga_repo.py" --format hermes', "timeout": 20}]
            blok = u.potong_hooks(open(hermes, encoding="utf-8").read())
            self.assertNotIn("rahasia-uji", blok)
            self.assertEqual(u.baca_hermes(hermes), harapan)
            self.assertEqual(u.urai_hooks(blok)["pre_tool_call"], harapan)   # pengurai cadangan tanpa PyYAML
        self.assertTrue(u.cocok("claude", "Bash|PowerShell", "PowerShell"))
        self.assertFalse(u.cocok("claude", "Write|Edit", "MultiEdit"))
        self.assertTrue(u.cocok("claude", "Edit.*", "NotebookEdit"))   # Claude: regex tanpa jangkar
        self.assertFalse(u.cocok("hermes", "write", "write_file"))     # Hermes: regex utuh

    def test_keputusan(self):  # dibaca seperti platformnya: kode 2 (Claude, Hermes) atau JSON decision (Antigravity)
        import uji_penjaga as u
        self.assertEqual(u.keputusan("claude", 2, ""), "ditolak")
        self.assertEqual(u.keputusan("hermes", 0, ""), "diizinkan")
        self.assertEqual(u.keputusan("hermes", 1, ""), "galat, keluar 1")   # penjaga yang mogok bukan penolakan
        self.assertEqual(u.keputusan("antigravity", 0, '{"decision": "deny", "reason": "x"}\n'), "ditolak")
        self.assertEqual(u.keputusan("antigravity", 0, '{"decision": "allow"}'), "diizinkan")
        self.assertEqual(u.keputusan("antigravity", 2, ""), "galat, keluar 2")   # Antigravity tidak membaca kode 2
        self.assertEqual(u.keputusan("antigravity", 0, "bukan json"), "galat, stdout bukan JSON")
        self.assertEqual(u.keputusan("claude", None, ""), "tidak jalan")
        dokter = ("Checking 2 configured shell hook(s)...\n\n  [pre_tool_call] python a.py\n"
                  "      ✗ not allowlisted — hook will NOT fire at runtime (run with --accept-hooks once)\n"
                  "      ℹ skipped JSON smoke test — not allowlisted yet.\n\n  [pre_tool_call] python b.py\n"
                  "      ✓ allowlisted (approved x)\n      ⚠ script modified since approval (was a, now b)\n\n"
                  "2 issue(s) found.  Fix before relying on these hooks.\n")
        self.assertEqual(u.baca_dokter(dokter), (["Checking 2 configured shell hook(s)...",
                                                  "2 issue(s) found.  Fix before relying on these hooks."], 1))   # drift bukan kematian

    def test_penjaga_tiruan(self):  # penjaga `python -c` tiruan: yang hidup OK, yang mati atau tak tercakup matcher GAGAL
        import tempfile, uji_penjaga as u
        py = sys.executable.replace("\\", "/")
        hidup = f'"{py}" -c "import sys; sys.exit(2 if \'git clone\' in sys.stdin.read() else 0)" penjaga_repo'
        mati = f'"{py}" -c "import sys; sys.stdin.read()" penjaga_repo'
        with tempfile.TemporaryDirectory() as t:
            fx = u.siapkan(t, "D:/Vault Uji")
            def status(platform, command, matcher):
                baris = u.uji_platform(platform, [{"matcher": matcher, "command": command, "timeout": 60}], fx, "D:/Vault Uji", "D:/CODE", t)
                return [b[5] for b in baris if b[1] == "penjaga_repo"]
            self.assertEqual(status("hermes", hidup, "terminal"), ["OK"])                # tanpa shell, dipecah seperti Hermes
            self.assertEqual(status("claude", hidup, "Bash|PowerShell"), ["OK", "OK"])   # lewat Git Bash
            self.assertEqual(status("hermes", mati, "terminal"), ["GAGAL"])              # tidak pernah menolak
            self.assertEqual(status("hermes", hidup, "write_file"), ["GAGAL"])           # matcher tidak mencakup terminal

if __name__ == "__main__":
    unittest.main()
