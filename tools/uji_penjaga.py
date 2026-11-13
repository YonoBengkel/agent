"""Uji hidup penjaga terpasang: setiap hook vault_guard, penjaga_repo, dan penjaga_desain di Claude, Antigravity, dan Hermes
dijalankan persis seperti di konfigurasinya, dengan payload yang wajib ditolak lalu kembarannya yang wajib lolos (sejak 2026-11-13).

  python tools/uji_penjaga.py --claude-settings ~/.claude/settings.json --antigravity-hooks ~/.gemini/config/hooks.json
         --hermes-config D:/Hermes/config.yaml [--hermes-doctor D:/Hermes/bin/hermes.exe]
         [--vault "D:/Obsidian/All Sources/AI Workspace"] [--projects-root D:/CODE]

test_tools.py menguji logika skrip penjaga. Alat ini menguji yang terpasang: baris perintah hook, pembungkus .cmd, Python di
PATH, dan berkas argumennya, karena penjaga yang mati atau salah pasang selama ini tampak sama dengan kepatuhan sempurna.
Penjaga dikenali dari nama skripnya di perintah hook atau di pembungkus .cmd yang dipanggilnya, dan matcher hook harus mencakup
alat yang diuji. Cara menjalankan dan membaca keputusan mengikuti platformnya:
- claude: lewat Git Bash, atau PowerShell kalau Git Bash tidak ada atau hook memilih shell powershell. Ditolak = keluar 2.
- hermes: tanpa shell, dipecah seperti split_command_line Hermes. Ditolak = keluar 2.
- antigravity: tanpa shell, dipecah per spasi (log vault Agent_Dev 053). Ditolak = stdout JSON {"decision": "deny"}, keluar 0.
Kode keluar lain, stdout yang bukan JSON keputusan, dan waktu habis dihitung galat. Riwayat baca untuk penjaga_desain dipalsukan
seperti di tes: transkrip tiruan (Claude, Antigravity) dan state.db tiruan lewat HERMES_HOME (Hermes). Payload hanya diperiksa
penjaga, tidak pernah dijalankan: tidak ada tulisan, clone, atau salinan sungguhan. Berkas tiruan dan log keputusan penjaga
(PENJAGA_LOG) ada di folder sementara yang dihapus sesudahnya. config.yaml Hermes memuat secret, jadi hanya bagian hooks yang
dipotong dan diurai. Keluar 1 kalau ada penjaga yang tidak menolak payload wajib tolak, menolak kembarannya, tidak dicakup
matchernya, atau konfigurasinya tidak terbaca. --hermes-doctor menjalankan `hermes hooks doctor` dan hanya mencetak baris
ringkasannya. Hook yang belum di-allowlist ikut dihitung gagal, karena Hermes melewatinya diam-diam, sedangkan probe di atas
menjalankan perintahnya langsung. Skrip yang berubah sesudah disetujui hanya peringatan: Hermes mencocokkan izin dari event dan
perintahnya saja (shell_hooks.py _entry_matches), jadi hook itu tetap jalan."""
import os
import re
import sys
import json
import uuid
import shlex
import shutil
import sqlite3
import pathlib
import argparse
import tempfile
import subprocess
from types import SimpleNamespace

PENJAGA = ("vault_guard", "penjaga_repo", "penjaga_desain")
NIK = "Uji penjaga: NIK palsu 1234567890123456."  # angka palsu, hanya untuk dikenali penjaga
BIASA = "Uji penjaga: teks biasa."
HTML = "<p>uji penjaga</p>"
RINGKASAN = re.compile(r"Checking \d+ configured|\d+ issue\(s\) found|All shell hooks look healthy|No shell hooks configured")


def potong_hooks(teks):
    """Baris bagian hooks saja: dari `hooks:` di kolom pertama sampai kunci tingkat atas berikutnya."""
    baris, ambil = [], False
    for l in teks.splitlines():
        if re.match(r"[^\s#]", l):
            ambil = re.match(r"hooks\s*:", l) is not None
        if ambil:
            baris.append(l)
    return "\n".join(baris)


def skalar(teks):
    """Nilai YAML satu baris: kutip tunggal, kutip ganda, atau polos tanpa komentar di belakangnya."""
    m = re.match(r"'((?:[^']|'')*)'|\"((?:[^\"\\]|\\.)*)\"", teks)
    if m:
        return m.group(1).replace("''", "'") if m.group(1) is not None else json.loads(f'"{m.group(2)}"')
    teks = re.sub(r"\s+#.*$", "", teks)
    return {"true": True, "false": False}.get(teks, int(teks) if teks.isdigit() else teks)


def urai_hooks(blok):
    """Pengurai cadangan kalau PyYAML tidak ada, cukup untuk bentuk hooks Hermes: nama event, lalu daftar entri `kunci: nilai`."""
    hooks, daftar, entri, tingkat = {}, [], None, None
    for l in blok.splitlines()[1:]:
        m = re.match(r"( *)(- +)?([\w-]+)\s*:\s*(.*)$", l)
        if not m:
            continue
        spasi, butir, kunci, nilai = len(m.group(1)), m.group(2), m.group(3), m.group(4).strip()
        if not butir and (tingkat is None or spasi <= tingkat):
            tingkat, daftar, entri = spasi, hooks.setdefault(kunci, []), None
            continue
        if butir:
            entri = {}
            daftar.append(entri)
        if entri is not None:
            entri[kunci] = skalar(nilai)
    return hooks


def baca_claude(path):
    """Hook perintah di hooks.PreToolUse[] settings.json Claude Code, masing-masing dengan matcher entrinya."""
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    return [dict(h, matcher=e.get("matcher")) for e in (data.get("hooks") or {}).get("PreToolUse") or []
            for h in e.get("hooks") or [] if h.get("type", "command") == "command"]


def baca_antigravity(path):
    """Hook PreToolUse di hooks.json Antigravity: nama di tingkat atas, lalu entri matcher dengan hooks[].command."""
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    return [dict(h, matcher=e.get("matcher")) for grup in data.values() if isinstance(grup, dict)
            for e in grup.get("PreToolUse") or [] for h in e.get("hooks") or []]


def baca_hermes(path):
    """Entri hooks.pre_tool_call di config.yaml Hermes. Berkas ini memuat secret, jadi hanya bagian hooks yang dipotong lalu
    diurai; kunci lain tidak pernah diurai, dicetak, atau disalin."""
    blok = potong_hooks(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    try:
        import yaml
    except ImportError:
        hooks = urai_hooks(blok)
    else:
        hooks = (yaml.safe_load(blok) or {}).get("hooks") or {}
    return [e for e in hooks.get("pre_tool_call") or [] if isinstance(e, dict)]


BACA = {"claude": baca_claude, "antigravity": baca_antigravity, "hermes": baca_hermes}


def cocok(platform, matcher, alat):
    """Apakah matcher hook mencakup alat ini. Claude (dokumentasi hooks): kosong atau * berarti semua, nama polos dipisah | atau
    , berarti daftar persis, selain itu regex tanpa jangkar. Hermes (shell_hooks.py), juga dipakai untuk Antigravity yang
    aturannya belum diketahui: regex utuh, dan regex yang rusak dibandingkan apa adanya."""
    m = (matcher or "").strip()
    if not m or (m == "*" and platform != "hermes"):
        return True
    if platform == "claude" and re.fullmatch(r"[\w\s,|-]+", m):
        return alat in {x.strip() for x in re.split(r"[|,]", m)}
    try:
        return bool(re.search(m, alat) if platform == "claude" else re.fullmatch(m, alat))
    except re.error:
        return m == alat


def teks_perintah(h, folder):
    """Perintah hook ditambah isi pembungkus .cmd atau .bat yang dipanggilnya, supaya penjaga dikenali dari nama skripnya."""
    cmd = str(h.get("command") or "")
    awal = (cmd.split() or [""])[0].strip('"')
    path = os.path.join(folder, os.path.expanduser(awal))
    if awal.lower().endswith((".cmd", ".bat")) and os.path.isfile(path):
        cmd += "\n" + pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    return cmd


def git_bash():
    """Shell hook Claude Code: sh di macOS dan Linux, Git Bash di Windows (CLAUDE_CODE_GIT_BASH_PATH, lalu bin/bash.exe di atas
    git di PATH). bash di PATH Windows sengaja tidak dipakai, karena sering peluncur WSL."""
    if os.name != "nt":
        return shutil.which("sh")
    if os.environ.get("CLAUDE_CODE_GIT_BASH_PATH"):
        return os.environ["CLAUDE_CODE_GIT_BASH_PATH"]
    git = shutil.which("git")
    return next((str(p / "bin" / "bash.exe") for p in pathlib.Path(git).parents if (p / "bin" / "bash.exe").is_file()), None) if git else None


def pecah_hermes(cmd):
    """Cara Hermes memecah perintah hook (split_command_line): di Windows shlex tanpa mode POSIX, lalu satu lapis kutip dilepas."""
    if os.name != "nt":
        return shlex.split(cmd)
    return [t[1:-1] if len(t) > 1 and t[0] == t[-1] and t[0] in "'\"" else t for t in shlex.split(cmd, posix=False)]


def proses(argv, masuk, env, cwd, batas):
    """(kode keluar, stdout, stderr) dari argv dengan masuk di stdin, atau kode None kalau tidak jalan. Lewat batas waktu, pohon
    prosesnya dimatikan supaya tidak ada proses yang tersisa."""
    if not argv:
        return None, "", "perintah kosong"
    try:
        p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env)
    except OSError as e:
        return None, "", f"tidak bisa dijalankan ({type(e).__name__}: {e})"
    try:
        out, err = p.communicate(masuk, timeout=batas)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        p.kill()
        p.communicate()
        return None, "", f"waktu habis sesudah {batas:g} detik"
    return p.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def jalankan(platform, h, data, fx, folder):
    """Jalankan perintah hook dengan payload data seperti platformnya menjalankannya."""
    cmd = str(h.get("command") or "")
    try:
        if platform == "claude" and h.get("args") is not None:  # bentuk exec: perintah dicari di PATH, tanpa shell
            argv = [shutil.which(cmd) or cmd, *map(str, h["args"])]
        elif platform == "claude":
            sh = None if h.get("shell") == "powershell" else git_bash()
            argv = [sh, "-c", cmd] if sh else ["powershell", "-NoProfile", "-Command", cmd]
        else:
            argv = pecah_hermes(os.path.expanduser(cmd)) if platform == "hermes" else cmd.split()
            if argv and platform == "antigravity" and os.path.dirname(argv[0]) and not os.path.isabs(argv[0]):
                argv[0] = os.path.join(folder, argv[0])  # path relatif dinilai dari folder hooks.json
            if argv:
                argv[0] = shutil.which(argv[0]) or argv[0]
    except ValueError as e:
        return None, "", f"perintah tidak bisa dipecah ({e})"
    env = {**os.environ, "HERMES_HOME": fx.hermes, "PENJAGA_LOG": fx.log, "PYTHONDONTWRITEBYTECODE": "1"}
    return proses(argv, json.dumps(data).encode("utf-8"), env, fx.kerja, float(h.get("timeout") or 60))


def keputusan(platform, kode, keluaran):
    """'ditolak', 'diizinkan', atau keterangan galat, dibaca seperti platformnya membaca hasil hook."""
    if kode is None:
        return "tidak jalan"
    if platform != "antigravity":
        return {2: "ditolak", 0: "diizinkan"}.get(kode, f"galat, keluar {kode}")
    if kode != 0:
        return f"galat, keluar {kode}"
    try:
        d = json.loads(keluaran).get("decision")
    except (ValueError, AttributeError):
        return "galat, stdout bukan JSON"
    return {"deny": "ditolak", "allow": "diizinkan"}.get(d, f"galat, decision {d!r}")


def siapkan(t, vault):
    """Riwayat baca tiruan di folder sementara t, berbentuk sama dengan tes PenjagaDesain: transkrip kosong, transkrip yang sudah
    membuka Referensi Desain (format Claude dan Antigravity), dan state.db Hermes dengan sesi belum-baca dan sudah-baca."""
    halaman = f"{vault}/Wiki/system/Referensi Desain.md"
    fx = SimpleNamespace(kerja=os.path.join(t, "kerja"), hermes=os.path.join(t, "hermes"), log=os.path.join(t, "penjaga-log"),
                         kosong=os.path.join(t, "kosong.jsonl"), baca_claude=os.path.join(t, "baca-claude.jsonl"),
                         baca_agy=os.path.join(t, "baca-agy.jsonl"))
    os.makedirs(fx.kerja)
    os.makedirs(fx.hermes)
    pathlib.Path(fx.kosong).write_text("", encoding="utf-8")
    pathlib.Path(fx.baca_claude).write_text(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": halaman}}]}}) + "\n", encoding="utf-8")
    pathlib.Path(fx.baca_agy).write_text(json.dumps({"step_index": 1, "tool_calls": [
        {"name": "read_file", "args": {"Path": halaman}}]}) + "\n", encoding="utf-8")
    db = sqlite3.connect(os.path.join(fx.hermes, "state.db"))
    db.execute("CREATE TABLE sessions (id TEXT, cwd TEXT)")
    db.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, tool_calls TEXT)")
    db.executemany("INSERT INTO sessions VALUES (?, ?)", [("belum-baca", fx.kerja), ("sudah-baca", fx.kerja)])
    db.execute("INSERT INTO messages (session_id, role, tool_calls) VALUES ('sudah-baca', 'assistant', ?)",
               (json.dumps([{"function": {"name": "read_file", "arguments": json.dumps({"path": halaman})}}]),))
    db.commit()
    db.close()
    return fx


def payload(platform, alat, masukan, fx, sudah_baca=False):
    """Payload hook dalam bentuk yang dikirim platform itu (bentuknya dari tes VaultGuard, PenjagaDesain, dan PenjagaRepo)."""
    if platform == "antigravity":
        return {"toolCall": {"name": alat, "args": masukan}, "workspacePaths": [fx.kerja],
                "transcriptPath": fx.baca_agy if sudah_baca else fx.kosong}
    if platform == "hermes":
        return {"hook_event_name": "pre_tool_call", "session_id": "sudah-baca" if sudah_baca else "belum-baca", "cwd": fx.kerja,
                "tool_name": alat, "tool_input": masukan}
    return {"hook_event_name": "PreToolUse", "session_id": "uji-penjaga", "cwd": fx.kerja,
            "transcript_path": fx.baca_claude if sudah_baca else fx.kosong, "tool_name": alat, "tool_input": masukan}


def kasus(platform, vault, root, kerja):
    """(penjaga, alat, masukan wajib tolak, masukan wajib lolos, kembaran lolos memakai riwayat sudah-baca). Nama berkas acak
    supaya belum ada; penjaga_desain hanya menolak berkas tampilan baru."""
    nama = f"uji-penjaga-{uuid.uuid4().hex[:8]}"
    catatan, html, tujuan = f"{vault}/{nama}.md", f"{root}/uji-probe-desain/{nama}.html", f"{root}/uji-probe-repo"
    clone = "git clone https://github.com/orang-lain/contoh.git " + (f'"{tujuan}"' if " " in tujuan else tujuan)
    if platform == "claude":
        return [("vault_guard", "Write", {"file_path": catatan, "content": NIK}, {"file_path": catatan, "content": BIASA}, False),
                ("vault_guard", "Edit", {"file_path": catatan, "old_string": "x", "new_string": NIK},
                 {"file_path": catatan, "old_string": "x", "new_string": BIASA}, False),
                ("penjaga_repo", "Bash", {"command": clone}, {"command": "git status"}, False),
                ("penjaga_repo", "PowerShell", {"command": clone}, {"command": "git status"}, False),
                ("penjaga_desain", "Write", {"file_path": html, "content": HTML}, {"file_path": html, "content": HTML}, True)]
    if platform == "hermes":
        return [("vault_guard", "write_file", {"path": catatan, "content": NIK}, {"path": catatan, "content": BIASA}, False),
                ("vault_guard", "terminal", {"command": f'echo x > "{catatan}"'}, {"command": "ls"}, False),
                ("penjaga_repo", "terminal", {"command": clone}, {"command": "git status"}, False),
                ("penjaga_desain", "write_file", {"path": html, "content": HTML}, {"path": html, "content": HTML}, True)]
    return [("penjaga_repo", "run_command", {"CommandLine": clone, "Cwd": kerja}, {"CommandLine": "git status", "Cwd": kerja}, False),
            ("penjaga_desain", "write_file", {"Path": html}, {"Path": html}, True)]


def uji_satu(platform, h, data, fx, folder):
    """(keputusan, baris pesan pertama) dari satu panggilan hook."""
    kode, out, err = jalankan(platform, h, data, fx, folder)
    pesan = next((l.strip() for l in (err + "\n" + out).splitlines() if l.strip()), "")
    return keputusan(platform, kode, out), pesan[:160]


def uji_platform(platform, entri, fx, vault, root, folder):
    """Baris (platform, penjaga, alat, hasil wajib tolak, hasil wajib lolos, status, catatan) per penjaga dan alat yang diuji."""
    baris, semua = [], kasus(platform, vault, root, fx.kerja)
    for penjaga in PENJAGA:
        terpasang = [h for h in entri if penjaga in teks_perintah(h, folder)]
        daftar = [k for k in semua if k[0] == penjaga]
        if not terpasang or not daftar:
            baris.append((platform, penjaga, "-", "-", "-", "-",
                          "tidak terpasang" if not terpasang else "terpasang, tapi belum ada payload uji untuk platform ini"))
            continue
        for _, alat, tolak, lolos, sudah_baca in daftar:
            kena = [h for h in terpasang if cocok(platform, h.get("matcher"), alat)]
            if not kena:
                baris.append((platform, penjaga, alat, "-", "-", "GAGAL", f"matcher hook tidak mencakup {alat}"))
            for h in kena:
                if platform == "claude" and (h.get("async") or h.get("asyncRewake")):
                    baris.append((platform, penjaga, alat, "-", "-", "GAGAL", "hook async tidak bisa menolak"))
                    continue
                t, pesan_t = uji_satu(platform, h, payload(platform, alat, tolak, fx), fx, folder)
                l, pesan_l = uji_satu(platform, h, payload(platform, alat, lolos, fx, sudah_baca), fx, folder)
                ok = (t, l) == ("ditolak", "diizinkan")
                baris.append((platform, penjaga, alat, t, l, "OK" if ok else "GAGAL",
                              "" if ok else pesan_t if t != "ditolak" else pesan_l))
    return baris


def baca_dokter(out):
    """(baris ringkasan, jumlah hook yang belum di-allowlist) dari keluaran `hermes hooks doctor`."""
    baris = [l.strip() for l in out.splitlines()]
    return [l for l in baris if RINGKASAN.match(l)], sum("will NOT fire at runtime" in l for l in baris)


def dokter(hermes, config, fx):
    """(baris laporan, jumlah hook yang belum di-allowlist) dari `hermes hooks doctor`. Hanya baris ringkasan yang dicetak,
    karena baris lain bisa memuat potongan keluaran hook."""
    env = {**os.environ, "PENJAGA_LOG": fx.log, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    if config:  # doctor membaca config.yaml di HERMES_HOME
        env["HERMES_HOME"] = os.path.dirname(os.path.abspath(os.path.expanduser(config)))
    kode, out, err = proses([os.path.expanduser(hermes), "hooks", "doctor"], b"", env, fx.kerja, 300)
    ringkas, mati = baca_dokter(out)
    if not ringkas:
        return f"hermes doctor: ringkasan tidak ditemukan ({err if kode is None else f'keluar {kode}'})", 0
    mati_teks = f" | {mati} hook belum di-allowlist, Hermes tidak menjalankannya  GAGAL" if mati else ""
    return "hermes doctor: " + " | ".join(ringkas) + mati_teks, mati


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Uji hidup penjaga terpasang di Claude, Antigravity, dan Hermes: perintah hook "
                                            "dijalankan persis seperti di konfigurasi, dengan payload wajib tolak dan kembaran wajib lolos.")
    p.add_argument("--claude-settings", help="settings.json Claude Code, mis. ~/.claude/settings.json")
    p.add_argument("--antigravity-hooks", help="hooks.json Antigravity, mis. ~/.gemini/config/hooks.json")
    p.add_argument("--hermes-config", help="config.yaml Hermes. Berkas ini memuat secret: hanya bagian hooks yang dibaca")
    p.add_argument("--hermes-doctor", metavar="HERMES", help="Path program hermes: ikut jalankan `hermes hooks doctor`, hanya ringkasannya dicetak. "
                                                         "Hook yang belum di-allowlist dihitung gagal")
    p.add_argument("--vault", default="D:/Obsidian/All Sources/AI Workspace", help="Vault memori yang wajib dijaga")
    p.add_argument("--projects-root", default="D:/CODE", help="Folder proyek tepercaya yang wajib dijaga")
    a = p.parse_args()
    konfigurasi = [(n, v) for n, v in (("claude", a.claude_settings), ("antigravity", a.antigravity_hooks),
                                       ("hermes", a.hermes_config)) if v]
    if not konfigurasi:
        p.error("beri minimal satu dari --claude-settings, --antigravity-hooks, atau --hermes-config")
    vault, root = (x.replace("\\", "/").rstrip("/") for x in (a.vault, a.projects_root))
    print(f"Uji penjaga terpasang. Vault: {vault}. Folder proyek: {root}.")
    jumlah = gagal = 0
    with tempfile.TemporaryDirectory(prefix="uji-penjaga-", ignore_cleanup_errors=True) as t:
        fx = siapkan(t, vault)
        for platform, path in konfigurasi:
            path = os.path.abspath(os.path.expanduser(path))
            try:
                entri = BACA[platform](path)
            except Exception as e:  # nama galatnya saja: pesan pengurai YAML bisa mengutip isi berkas
                print(f"{platform:<12} konfigurasi {path} tidak terbaca ({type(e).__name__})  GAGAL")
                jumlah, gagal = jumlah + 1, gagal + 1
                continue
            for pl, penjaga, alat, tolak, lolos, status, catatan in uji_platform(platform, entri, fx, vault, root, os.path.dirname(path)):
                if status == "-":
                    print(f"{pl:<12} {penjaga:<15} {catatan}")
                    continue
                jumlah, gagal = jumlah + 1, gagal + (status == "GAGAL")
                print(f"{pl:<12} {penjaga:<15} {alat:<12} wajib tolak: {tolak:<10} wajib lolos: {lolos:<10} {status}"
                      + (f"  ({catatan})" if catatan else ""))
        if a.hermes_doctor:
            laporan, mati = dokter(a.hermes_doctor, a.hermes_config, fx)
            print(laporan)
            jumlah, gagal = jumlah + 1, gagal + (mati > 0)
    print(f"{jumlah - gagal} dari {jumlah} uji penjaga OK." + (" Baris GAGAL: penjaga mati atau salah pasang." if gagal else ""))
    return 1 if gagal else 0


if __name__ == "__main__":
    sys.exit(main())
