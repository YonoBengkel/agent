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

class SessionContext(unittest.TestCase):
    def test_project_name(self):
        import session_context as s
        root = os.path.join("D:" + os.sep, "CODE")
        self.assertEqual(s.project_name(root, os.path.join(root, "Con-Fore", "web")), "Con-Fore")
        self.assertIsNone(s.project_name(root, root))
        self.assertIsNone(s.project_name(root, os.path.join("D:" + os.sep, "KULIAH")))

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

if __name__ == "__main__":
    unittest.main()
