"""Cek proses sisa uji (Pelajaran #71, sejak 2026-11-10).

Mendaftar proses alat yang sering tertinggal sesudah uji (server dev Next dan Vite, uvicorn, Hermes, 9Router, agy,
Docker, http.server, browser Playwright) yang dibuat sesudah waktu tertentu, beserta port yang didengarnya, dan
asalnya: `sesi ini` (keturunan proses sesi agent), `yatim` (induknya sudah mati, misalnya karena menghentikan tugas
latar di Windows hanya mematikan shell-nya), atau `lain` (sesi lain atau terminal pengguna).

Dua cara pakai:
- Hook Stop Claude Code (`--hook`): waktu mulainya adalah waktu dibuatnya transkrip sesi, dan proses `lain`
  dilewati. Tiap proses dilaporkan sekali per sesi sebagai `decision: block`, jadi agent memeriksanya sebelum
  berhenti. Kalau giliran ini sudah dilanjutkan oleh hook Stop (`stop_hook_active`), peringatannya hanya tampil
  ke pengguna supaya tidak berulang.
- Manual (`--sejak 3h` atau `--sejak 2026-11-10T14:00`): cetak daftarnya, untuk agent tanpa hook Stop.

Data proses diambil langsung dari Windows API lewat ctypes (pustaka standar, puluhan milidetik). psutil dan
PowerShell sudah dicoba dan terlalu lambat untuk setiap akhir giliran: psutil menghitung ulang PID induk per proses
(7 detik untuk 350 proses), PowerShell sekitar 2 detik. Port dengar dibaca dari `netstat -ano` hanya kalau ada
temuan. Hanya untuk Windows. Selalu keluar 0: ini peringatan, bukan penjaga."""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time

POLA = [
    ("next", re.compile(r"next(\.cmd|\.js)?\W+(dev|start)\b|next[\\/]dist[\\/]bin[\\/]next", re.I)),
    ("vite", re.compile(r"\bvite(\.cmd|\.js)?\b", re.I)),
    ("uvicorn", re.compile(r"\buvicorn\b", re.I)),
    ("hermes", re.compile(r"\bhermes\b", re.I)),
    ("9router", re.compile(r"9router(?![\\/]+docker-compose\.ya?ml)", re.I)),   # bukan argumen --secrets-from milik hook
    ("agy", re.compile(r"(^|[\\/\s\"])agy(\.exe)?(\"|\s|$)", re.I)),
    ("docker", re.compile(r"docker desktop\.exe|com\.docker\.backend|\bdocker(\.exe)?\"?\s+(compose|run|start)\b", re.I)),
    ("http.server", re.compile(r"-m\s+http\.server\b|\bhttp-server\b", re.I)),
    ("playwright", re.compile(r"ms-playwright|playwright_\w*profile|--remote-debugging-pipe", re.I)),
]
SESI = ("claude.exe", "claude")   # CLI sesi di aplikasi desktop Claude: leluhur terdekat bernama ini
# Hook dan alat perawatan workspace ini berumur pendek dan bisa jalan bersamaan dengan hook Stop ini, misalnya
# ekspor transkrip yang argumennya menyebut folder 9router (salah tangkap pertama, 2026-11-10)
ABAIKAN = re.compile(r"tools[\\/]+(export_transcript|cek_proses_sisa|vault_guard|session_context|penjaga_desain|vault_lint|sync_rules)\.py", re.I)

def jenis(cmd):
    """Nama alat dari POLA yang cocok dengan baris perintah, atau None. Hook workspace ini sendiri dilewati."""
    if ABAIKAN.search(cmd or ""):
        return None
    return next((nama for nama, pola in POLA if pola.search(cmd or "")), None)

def ambil(sejak):
    """Daftar proses dari Windows API: dict i (PID), o (PID induk), n (nama berkas), t (waktu dibuat, epoch, 0 kalau
    prosesnya tidak bisa dibuka), c (baris perintah, hanya untuk yang dibuat sesudah `sejak`)."""
    import ctypes
    from ctypes import wintypes
    k32, nt = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("ntdll")

    class Entri(ctypes.Structure):   # PROCESSENTRY32W
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("pid", wintypes.DWORD),
                    ("heap", ctypes.c_size_t), ("mod", wintypes.DWORD), ("threads", wintypes.DWORD),
                    ("ppid", wintypes.DWORD), ("prio", ctypes.c_long), ("flags", wintypes.DWORD), ("exe", ctypes.c_wchar * 260)]

    class Teks(ctypes.Structure):    # UNICODE_STRING di awal hasil ProcessCommandLineInformation
        _fields_ = [("len", wintypes.USHORT), ("maks", wintypes.USHORT), ("buf", ctypes.c_void_p)]

    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entri)]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    nt.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]

    def perintah(h):
        n = wintypes.ULONG(0)
        nt.NtQueryInformationProcess(h, 60, None, 0, ctypes.byref(n))   # 60: ProcessCommandLineInformation, minta ukuran dulu
        if not n.value:
            return None
        buf = ctypes.create_string_buffer(n.value)
        if nt.NtQueryInformationProcess(h, 60, buf, n.value, ctypes.byref(n)) != 0:
            return None
        t = Teks.from_buffer(buf)
        return ctypes.wstring_at(t.buf, t.len // 2) if t.buf else None

    snap = k32.CreateToolhelp32Snapshot(2, 0)   # TH32CS_SNAPPROCESS
    if not snap or snap == wintypes.HANDLE(-1).value:
        return []
    proses, e = [], Entri()
    e.dwSize = ctypes.sizeof(Entri)
    ada = k32.Process32FirstW(snap, ctypes.byref(e))
    while ada:
        proses.append({"i": e.pid, "o": e.ppid, "n": e.exe, "t": 0, "c": None})
        ada = k32.Process32NextW(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    for d in proses:
        h = k32.OpenProcess(0x1000, False, d["i"])   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            continue
        try:
            ft = [wintypes.FILETIME() for _ in range(4)]
            if k32.GetProcessTimes(h, *[ctypes.byref(f) for f in ft]):
                d["t"] = ((ft[0].dwHighDateTime << 32 | ft[0].dwLowDateTime) - 116444736000000000) / 1e7
            if d["t"] >= sejak:
                d["c"] = perintah(h)
        finally:
            k32.CloseHandle(h)
    return proses

def ambil_port():
    """Port TCP yang didengar per PID, dari `netstat -ano`. Baris dengar dikenali dari alamat tujuannya yang kosong
    (0.0.0.0:0 atau [::]:0), jadi tidak bergantung pada bahasa Windows."""
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return []
    dengar = []
    for l in r.stdout.decode("ascii", "replace").splitlines():
        b = l.split()
        if len(b) >= 5 and b[0].upper() == "TCP" and b[2] in ("0.0.0.0:0", "[::]:0") and b[-1].isdigit():
            dengar.append({"p": int(b[1].rsplit(":", 1)[1]), "i": int(b[-1])})
    return dengar

def cari(proses, dengar, sejak, diri):
    """Proses alat yang dibuat sesudah `sejak`, dengan asalnya relatif ke proses sesi: leluhur terdekat `diri`
    (proses pemeriksa ini) yang bernama claude.exe. Induk yang dibuat sesudah anaknya berarti PID-nya dipakai ulang."""
    tabel = {d["i"]: d for d in proses}
    def induk(d):
        o = tabel.get(d["o"])
        return o if o and o["i"] != d["i"] and o["t"] <= d["t"] else None
    def leluhur(d):
        lihat = set()
        while (d := induk(d)) and d["i"] not in lihat:
            lihat.add(d["i"])
            yield d
    awal = tabel.get(diri)
    rantai = [awal] + list(leluhur(awal)) if awal else []
    sesi = next((a["i"] for a in rantai[1:] if (a["n"] or "").lower() in SESI), None)
    lewati = {a["i"] for a in rantai}
    hasil = []
    for d in proses:
        alat = jenis(d.get("c"))
        if d["t"] < sejak or d["i"] in lewati or not alat:
            continue
        if sesi and any(a["i"] == sesi for a in leluhur(d)):
            dari = "sesi ini"
        else:
            dari = "yatim" if induk(d) is None else "lain"
        hasil.append({"pid": d["i"], "alat": alat, "dibuat": d["t"], "asal": dari, "port": [], "cmd": d["c"]})
    return isi_port(hasil, dengar)

def isi_port(hasil, dengar):
    for h in hasil:
        h["port"] = sorted({x["p"] for x in dengar if x["i"] == h["pid"]})
    return hasil

def baris(h):
    port = f" port {','.join(map(str, h['port']))}" if h["port"] else ""
    jam = time.strftime("%H:%M", time.localtime(h["dibuat"]))
    return f"{h['alat']} PID {h['pid']}{port} sejak {jam} ({h['asal']}): {h['cmd'][:100]}"

def hook(payload, state_dir, ambil_data=ambil, ambil_dengar=ambil_port, diri=None):
    """Hook Stop Claude Code. Kembalikan dict keluaran hook, atau None kalau tidak ada yang perlu dilaporkan."""
    try:
        st = os.stat(payload.get("transcript_path") or "")
    except OSError:
        return None
    mulai = getattr(st, "st_birthtime", st.st_ctime)   # Windows: waktu berkas transkrip dibuat, yaitu awal sesi
    temuan = [h for h in cari(ambil_data(mulai), [], mulai, diri or os.getpid()) if h["asal"] != "lain"]
    path = os.path.join(state_dir, re.sub(r"[^\w-]", "_", str(payload.get("session_id") or "tanpa-sesi")) + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            sudah = set(json.load(f))
    except (OSError, ValueError):
        sudah = set()
    kunci = lambda h: f"{h['pid']}-{int(h['dibuat'])}"   # PID bisa dipakai ulang, waktu dibuatnya tidak
    baru = [h for h in temuan if kunci(h) not in sudah]
    if not baru:
        return None
    isi_port(baru, ambil_dengar())   # netstat hanya dijalankan kalau ada yang dilaporkan
    os.makedirs(state_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(sudah | {kunci(h) for h in baru}), f)
    daftar = "; ".join(baris(h) for h in baru[:8]) + (f"; dan {len(baru) - 8} lagi" if len(baru) > 8 else "")
    if payload.get("stop_hook_active"):
        return {"systemMessage": f"Proses alat masih hidup sesudah giliran ini (Pelajaran #71): {daftar}"}
    return {"decision": "block", "reason": (
        f"Cek proses sisa (Pelajaran #71): {daftar}. Matikan yang dinyalakan sesi ini lewat PID-nya, pastikan sudah mati, "
        "lalu laporkan ke pengguna. Yang sengaja dibiarkan hidup (misalnya atas permintaan pengguna) cukup disebutkan. "
        "Proses yatim bisa saja milik sesi lain, jadi periksa dulu sebelum mematikannya. Peringatan untuk proses yang sama tidak diulang.")}

def sejak_dari(teks):
    m = re.fullmatch(r"(\d+)([mhd])", teks)
    if m:
        return time.time() - int(m.group(1)) * {"m": 60, "h": 3600, "d": 86400}[m.group(2)]
    return datetime.datetime.fromisoformat(teks).timestamp()

def main():
    p = argparse.ArgumentParser(description="Daftar proses alat sisa uji (server dev, uvicorn, Hermes, 9Router, agy, Docker, Playwright) beserta port dan asalnya.")
    p.add_argument("--hook", action="store_true", help="Mode hook Stop Claude Code: baca JSON hook dari stdin")
    p.add_argument("--sejak", default="12h", help="Mode manual: proses yang dibuat sejak 90m, 3h, 2d, atau waktu ISO (bawaan 12h)")
    p.add_argument("--state-dir", default=os.path.join(tempfile.gettempdir(), "cek_proses_sisa"),
                   help="Folder catatan proses yang sudah dilaporkan per sesi (bawaan: folder temp sistem)")
    a = p.parse_args()
    if a.hook:
        try:
            payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")   # -sig: pipa PowerShell menambah BOM
            out = hook(payload if isinstance(payload, dict) else {}, a.state_dir)
        except Exception as e:   # peringatan, bukan penjaga: galat tidak boleh menahan sesi
            print(f"cek_proses_sisa gagal: {type(e).__name__}: {e}", file=sys.stderr)
            out = None
        if out:
            sys.stdout.reconfigure(encoding="utf-8")
            print(json.dumps(out, ensure_ascii=False))
        return
    sejak = sejak_dari(a.sejak)
    temuan = cari(ambil(sejak), [], sejak, os.getpid())
    isi_port(temuan, ambil_port() if temuan else [])
    sys.stdout.reconfigure(encoding="utf-8")
    for h in temuan:
        print(baris(h))
    print(f"{len(temuan)} proses alat sejak {a.sejak}." if temuan else f"Tidak ada proses alat sejak {a.sejak}.")

if __name__ == "__main__":
    main()
