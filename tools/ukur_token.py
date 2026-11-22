"""Alat ukur anggaran token mingguan (log vault 078: Q11 dan Q20, dibuat 2026-11-22). Menggabungkan dua skrip sekali
pakai sesi Con-Fore, `tulis_cache.py` dan `beban_awal.py`. Hanya membaca angka usage, nama alat, nama skill, dan ukuran
bagian prompt dari transkrip Claude Code, ditambah daftar connector dari data aplikasi desktop. Isi percakapan tidak
pernah dicetak.

  python tools/ukur_token.py laporan [--hari 7] [--sampai YYYY-MM-DD] [--simpan <folder>] [--jatuh-tempo]
  python tools/ukur_token.py rincian [--berkas <transkrip.jsonl>] [--entrypoint cli]
  python tools/ukur_token.py baris [--folder <folder>]

`laporan` mencetak empat angka anggaran Q20, yaitu beban awal sesi baru, kembali ke sesi besar setelah jeda lebih lama
dari umur cache, porsi bobot subagent dari agent Opus beralat lengkap, serta connector dan skill yang menyala tapi 30
hari tidak dipakai. Ditambah umur cache (TTL), porsi output, dan daftar yang menganggur. --simpan menulis
laporan-token-<tanggal>.md dan .json ke folder itu. Dengan --jatuh-tempo, laporan hanya ditulis kalau laporan terakhir
sudah 7 hari atau lebih (pertama 2026-11-29); mode ini dipanggil laporan harian terjadwal. `rincian` memecah beban awal
satu sesi per bagian (prompt sistem, definisi alat, berkas aturan, daftar skill, dan seterusnya). `baris` mencetak satu
baris ringkasan laporan minggu ini untuk hook awal sesi.

Bobot memakai tarif API dari skill claude-api (dicek 2026-11-22) hanya sebagai pembanding, karena akunnya langganan."""
import argparse
import datetime as dt
import glob
import json
import os
import re
import statistics as st
import sys
from collections import Counter, defaultdict

HOME = os.path.expanduser("~")
MULAI = dt.date(2026, 11, 29)   # laporan mingguan pertama (Q20)
SASARAN = {"beban_awal": 65_000, "kembali_jeda": 0, "porsi_opus_lengkap": 0.20, "menganggur": 0}
# $/juta token: input, tulis cache 5 menit, tulis cache 1 jam, baca cache, output. Dari skill claude-api (dicek
# 2026-11-22). Baca cache Opus 5 dan Haiku 5.5 tidak disebut di sana, jadi diisi 0,1 kali input (unverified).
TARIF = {"claude-opus-5-5": (4, 5, 8, 0.20, 20), "claude-opus-5": (5, 6.25, 10, 0.50, 25),
         "claude-sonnet-5-5": (2, 2.5, 4, 0.10, 10), "claude-sonnet-5": (2, 2.5, 4, 0.20, 10),
         "claude-haiku-5-5": (0.10, 0.125, 0.20, 0.01, 0.50)}
BAWAAN_SEMPIT = {"statusline-setup", "claude-code-guide", "web-fetch"}   # agent bawaan yang alatnya sudah sempit
BESAR, PADAT, BESAR_SEKALI = 50_000, 130_000, 200_000   # ambang dari tulis_cache.py, dan sesi besar aturan inti 2
CMD = re.compile(r"<command-name>/?([^<]+)</command-name>")
# Penanda awal bagian di teks panggilan pertama, untuk `rincian`. Teksnya mengikuti versi Claude Code 2.1.330 dan bisa
# bergeser; bagian yang tidak dikenali masuk "lainnya".
PENANDA = [("Berkas aturan (CLAUDE.md, AGENTS.md, memori)", "Codebase and user instructions are shown below"),
           ("Konteks pengguna (email, status git)", "As you answer the user's questions, you can use the following context"),
           ("Atribusi komit", "Attribution for git commits"),
           ("Konteks hook awal sesi", "SessionStart hook additional context"),
           ("Lingkungan", "# Environment"),
           ("Daftar alat tertunda (connector dan lainnya)", "The following deferred tools are now available"),
           ("Daftar server MCP perlu masuk", "The following MCP servers require authentication"),
           ("Daftar server MCP sedang tersambung", "The following MCP servers are still connecting"),
           ("Daftar agent", "Available agent types for the Agent tool"),
           ("Instruksi server MCP", "# MCP Server Instructions"),
           ("Daftar skill", "The following skills are available for use with the Skill tool")]


def waktu(ts):
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def tarif(model):
    m = model or ""
    return next((TARIF[k] for k in sorted(TARIF, key=len, reverse=True) if m.startswith(k)), TARIF["claude-opus-5-5"])


def biaya(c, bagian=None):
    """Bobot satu panggilan dalam dolar tarif API. bagian: 'input', 'tulis', 'baca', atau 'output' saja."""
    i, w5, w1, r, o = tarif(c["model"])
    nilai = {"input": c["it"] * i, "tulis": c["w5"] * w5 + c["w1"] * w1, "baca": c["cr"] * r, "output": c["ot"] * o}
    return (nilai[bagian] if bagian else sum(nilai.values())) / 1e6


def ukuran_prompt(u):
    return sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))


def teks(content):
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                yield c.get("text") or ""


def panggilan(t, m, u):
    det = u.get("cache_creation") or {}
    cc = u.get("cache_creation_input_tokens") or 0
    w1 = det.get("ephemeral_1h_input_tokens") or 0
    w5 = det.get("ephemeral_5m_input_tokens") or (0 if w1 else cc)   # tanpa rincian TTL: anggap 5 menit
    return dict(t=t, model=m.get("model") or "?", it=u.get("input_tokens") or 0, cc=cc,
                cr=u.get("cache_read_input_tokens") or 0, ot=u.get("output_tokens") or 0, w1=w1, w5=w5)


def pindai(path, utama, sejak, pesan, alat):
    """Satu transkrip: panggilan baru (unik per id pesan) sejak `sejak`, pemakaian alat, skill, dan perintah garis
    miring, serta panggilan pertama berkas (untuk beban awal). `pesan` dan `alat` dibagi antarberkas, supaya salinan
    sesi yang sama di dua folder proyek tidak terhitung dua kali."""
    calls, pakai, pertama, awal_dilihat = [], [], None, False
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"assistant"' not in line and "<command-name>" not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if utama and e.get("isSidechain"):
                continue
            t = waktu(e.get("timestamp"))
            if t is None:
                continue
            m = e.get("message") or {}
            if e.get("type") == "user":
                if utama and t >= sejak:
                    pakai += [(t, "/" + n.strip()) for s in teks(m.get("content")) for n in CMD.findall(s)]
                continue
            if e.get("type") != "assistant":
                continue
            u, mid = m.get("usage"), m.get("id")
            if u and mid and m.get("model") != "<synthetic>" and ukuran_prompt(u):   # sintetis atau tanpa angka: bukan panggilan API
                if not awal_dilihat:   # beban awal hanya dari pesan pertama berkas, dan hanya kalau bukan salinan sesi lain (fork)
                    awal_dilihat = True
                    if mid not in pesan:
                        pertama = (t, ukuran_prompt(u), e.get("entrypoint") or "?", m.get("model") or "?")
                if mid in pesan:   # satu pesan ditulis beberapa baris (satu per blok konten): ambil output terbesar
                    pesan[mid]["ot"] = max(pesan[mid]["ot"], u.get("output_tokens") or 0)
                elif t >= sejak:
                    pesan[mid] = panggilan(t, m, u)
                    calls.append(pesan[mid])
            for b in m.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use" and t >= sejak and b.get("id") not in alat:
                    alat.add(b.get("id"))
                    pakai.append((t, b.get("name") or "?"))
                    if b.get("name") == "Skill":
                        pakai.append((t, "skill:" + str((b.get("input") or {}).get("skill"))))
    calls.sort(key=lambda c: c["t"])
    return calls, pakai, pertama


def kumpulkan(projects, sejak):
    """Transkrip sesi utama dan subagent yang berubah sejak `sejak`, beserta jenis agent tiap subagent."""
    pesan, alat, utama, sub = {}, set(), [], []
    batas = sejak.timestamp()
    for path in glob.glob(os.path.join(projects, "*", "*.jsonl")):
        if os.path.getmtime(path) >= batas:
            calls, pakai, pertama = pindai(path, True, sejak, pesan, alat)
            utama.append(dict(path=path, proyek=os.path.basename(os.path.dirname(path)), calls=calls, pakai=pakai,
                              pertama=pertama))
    for path in glob.glob(os.path.join(projects, "*", "*", "subagents", "*.jsonl")):
        if os.path.getmtime(path) >= batas:
            calls, pakai, _ = pindai(path, False, sejak, pesan, alat)
            try:
                with open(path[:-len(".jsonl")] + ".meta.json", encoding="utf-8") as f:
                    jenis = json.load(f).get("agentType") or "?"
            except (OSError, ValueError, AttributeError):
                jenis = "?"
            sub.append(dict(path=path, jenis=jenis, calls=calls, pakai=pakai))
    return utama, sub


def agent_sempit(agents_dir):
    """Agent khusus yang definisinya membatasi alat (punya baris `tools:`), ditambah agent bawaan beralat sempit."""
    nama = set(BAWAAN_SEMPIT)
    for p in glob.glob(os.path.join(agents_dir, "*.md")):
        try:
            with open(p, encoding="utf-8") as f:
                kepala = f.read(3000)
        except OSError:
            continue
        m = re.search(r"(?m)^name:\s*(\S+)", kepala)
        if m and re.search(r"(?m)^tools:\s*\S", kepala):
            nama.add(m.group(1))
    return nama


def connector(app_data=None):
    """{uuid: (nama, menyala)} connector claude.ai di aplikasi desktop, atau None kalau datanya tidak ada. Daftarnya
    dari berkas sesi terbaru; bawaan untuk sesi baru dari mcp-user-tool-toggles.json, yang menyimpan alat yang
    dimatikan per akun (dicek 2026-11-22: berkas lokal di laptop, bukan di akun)."""
    folders = [app_data] if app_data else sorted(glob.glob(os.path.join(HOME, "AppData", "Local", "Claude-Data", "claude_*")))
    for d in folders:
        sesi = glob.glob(os.path.join(d, "claude-code-sessions", "*", "*", "local_*.json"))
        if not sesi:
            continue
        terbaru = max(sesi, key=os.path.getmtime)
        akun = os.path.basename(os.path.dirname(os.path.dirname(terbaru)))
        try:
            with open(terbaru, encoding="utf-8") as f:
                servers = json.load(f).get("remoteMcpServersConfig") or []
        except (OSError, ValueError):
            continue
        try:
            with open(os.path.join(d, "mcp-user-tool-toggles.json"), encoding="utf-8") as f:
                mati = Counter(x.split(":")[0] for x in (json.load(f).get("owners") or {}).get(akun) or [])
        except (OSError, ValueError, AttributeError):
            mati = Counter()
        return {s["uuid"]: (s.get("name") or s["uuid"], mati[s["uuid"]] < len(s.get("tools") or []))
                for s in servers if isinstance(s, dict) and s.get("uuid")}
    return None


def daftar_skill(paths):
    """({nama skill: punya deskripsi}, transkrip asalnya, jumlah karakter) dari daftar skill awal sesi (lampiran
    skill_listing pertama di berkas) yang paling baru di 30 transkrip utama terakhir. Sesi yang hidup berhari-hari
    membawa daftar lama dari memorinya, juga di kiriman ulang sesudah ringkas yang ikut bertanda isInitial (dicek
    2026-11-22: sesudah skillOverrides diubah, sesi lama tetap mengirim daftar lama). Nama skill unggahan akun juga
    pernah berganti dari `anthropic-skills:<nama>` (2026-11-16) menjadi `<nama>:<nama>` (sejak 2026-11-17)."""
    terbaik = (None, {}, None, 0)
    for path in sorted(paths, key=os.path.getmtime, reverse=True)[:30]:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if '"skill_listing"' not in line:
                        continue
                    try:   # baris terakhir transkrip yang sedang ditulis bisa terpotong
                        e = json.loads(line)
                        a = e.get("attachment") or {}
                    except (ValueError, AttributeError):
                        continue
                    t = waktu(e.get("timestamp"))
                    if a.get("type") != "skill_listing" or a.get("isInitial") is False or t is None:
                        continue
                    if terbaik[0] is None or t > terbaik[0]:
                        hasil = {}
                        for b in (a.get("content") or "").splitlines():
                            if b.startswith("- "):
                                nama, _, desk = b[2:].partition(": ")
                                hasil[nama.strip()] = bool(desk.strip())
                        if hasil:
                            terbaik = (t, hasil, path, len(a.get("content") or ""))
                    break   # daftar berikutnya di berkas ini bukan daftar awal sesi
        except OSError:
            continue
    return terbaik[1], terbaik[2], terbaik[3]


def dipakai(nama, terpakai):
    return nama in terpakai or nama.split(":")[-1] in terpakai


def median(xs):
    return st.median(xs) if xs else None


def kembali_setelah_jeda(calls, sejak, sampai):
    """Panggilan besar sesudah jeda lebih lama dari umur cache sesi itu (1 jam kalau tulisannya kebanyakan TTL 1 jam,
    selain itu 5 menit). Besar = prompt minimal 50 ribu dan minimal separuhnya tulis cache, seperti tulis_cache.py."""
    ttl = 3600 if sum(c["w1"] for c in calls) >= sum(c["w5"] for c in calls) else 300
    hasil = []
    for prev, c in zip(calls, calls[1:]):
        p = c["it"] + c["cc"] + c["cr"]
        if sejak <= c["t"] < sampai and (c["t"] - prev["t"]).total_seconds() > ttl and p >= BESAR and c["cc"] >= 0.5 * p:
            hasil.append(dict(prompt=p, tulis=c["cc"], jeda_jam=(c["t"] - prev["t"]).total_seconds() / 3600))
    return hasil


def analisis(projects, agents_dir, app_data, sampai, hari=7, hari_idle=30):
    sejak = sampai - dt.timedelta(days=hari)
    sejak_idle = sampai - dt.timedelta(days=hari_idle)
    utama, sub = kumpulkan(projects, min(sejak, sejak_idle))
    dalam = lambda c: sejak <= c["t"] < sampai

    awal = [(u["pertama"][1], u["pertama"][2]) for u in utama if u["pertama"] and sejak <= u["pertama"][0] < sampai]
    per_ep = defaultdict(list)
    for n, ep in awal:
        per_ep[ep].append(n)

    kejadian = [k for u in utama for k in kembali_setelah_jeda(u["calls"], sejak, sampai)]

    c_utama = [c for u in utama for c in u["calls"] if dalam(c)]
    sempit = agent_sempit(agents_dir)
    per_jenis, sub_total, opus_lengkap = defaultdict(float), 0.0, 0.0
    c_sub = []
    for s in sub:
        for c in s["calls"]:
            if dalam(c):
                b = biaya(c)
                c_sub.append(c)
                sub_total += b
                lengkap = s["jenis"] not in sempit
                per_jenis[f"{s['jenis']} ({c['model'].replace('claude-', '')})"] += b
                if c["model"].startswith("claude-opus") and lengkap:
                    opus_lengkap += b
    bagian = {k: sum(biaya(c, k) for c in c_utama) for k in ("baca", "tulis", "output", "input")}
    total = sum(bagian.values()) + sub_total
    output_semua = bagian["output"] + sum(biaya(c, "output") for c in c_sub)

    terpakai, alat30, skill30 = set(), Counter(), Counter()
    for item in utama + sub:
        for t, nama in item["pakai"]:
            if t < sejak_idle or t >= sampai:
                continue
            if nama.startswith("skill:") or nama.startswith("/"):
                skill30[nama.split(":", 1)[1] if nama.startswith("skill:") else nama[1:]] += 1
            elif nama.startswith("mcp__"):
                alat30[nama.split("__")[1]] += 1
    for nama in list(skill30):
        terpakai.update({nama, nama.split(":")[-1]})
    kon = connector(app_data)
    kon_idle = sorted(nm for uid, (nm, nyala) in (kon or {}).items() if nyala and not (alat30[uid] or alat30[nm]))
    skills, asal, panjang = daftar_skill([u["path"] for u in utama if u["calls"]])   # tanpa sesi yang tak pernah memanggil API (galat login)
    skill_idle = sorted(n for n, desk in skills.items() if desk and not dipakai(n, terpakai))
    nama_saja_idle = sorted(n for n, desk in skills.items() if not desk and not dipakai(n, terpakai))

    w = lambda cs, k: sum(c[k] for c in cs)
    return {
        "dibuat": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "sejak": sejak.date().isoformat(), "sampai": sampai.date().isoformat(), "hari": hari,
        "beban_awal": {"median": median([n for n, _ in awal]), "n": len(awal),
                       "per_entrypoint": {ep: {"median": median(v), "n": len(v)} for ep, v in sorted(per_ep.items())}},
        "kembali_jeda": {"n": len(kejadian), "n_200rb": sum(k["prompt"] >= BESAR_SEKALI for k in kejadian),
                         "tulis": sum(k["tulis"] for k in kejadian),
                         "median_prompt": median([k["prompt"] for k in kejadian]),
                         "tulis_terhindar_bila_padat": sum(max(0, k["prompt"] - PADAT) for k in kejadian)},
        "porsi_opus_lengkap": opus_lengkap / sub_total if sub_total else None,
        "menganggur": {"connector": kon_idle, "skill": skill_idle, "n": len(kon_idle) + len(skill_idle),
                       "skill_nama_saja": nama_saja_idle, "connector_terbaca": kon is not None,
                       "skill_dari": asal, "skill_entri": len(skills), "skill_karakter": panjang, "hari": hari_idle},
        "ttl": {"utama_1jam": w(c_utama, "w1"), "utama_5menit": w(c_utama, "w5"),
                "sub_1jam": w(c_sub, "w1"), "sub_5menit": w(c_sub, "w5")},
        "porsi_output": output_semua / total if total else None,
        "bobot": {"total_usd_api": round(total, 2), "utama": {k: v / total if total else None for k, v in bagian.items()},
                  "subagent": sub_total / total if total else None,
                  "subagent_per_jenis": {k: v / sub_total for k, v in sorted(per_jenis.items(), key=lambda kv: -kv[1])} if sub_total else {}},
        "jumlah": {"sesi_utama": sum(1 for u in utama if any(dalam(c) for c in u["calls"])), "panggilan_utama": len(c_utama),
                   "panggilan_subagent": len(c_sub)},
    }


def ribu(n):
    return "-" if n is None else f"{n / 1000:,.0f} ribu".replace(",", ".")


def juta(n):
    return f"{n / 1e6:,.1f} juta".replace(".", ",") if n else "0"


def persen(x):
    return "-" if x is None else f"{100 * x:.0f}%"


def markdown(r):
    b, k, m = r["beban_awal"], r["kembali_jeda"], r["menganggur"]
    eps = ", ".join(f"{ep} {ribu(v['median'])} (n={v['n']})" for ep, v in b["per_entrypoint"].items()) or "-"
    baris = [
        f"# Laporan anggaran token {r['sejak']} sampai {r['sampai']}", "",
        f"Dibuat {r['dibuat']} oleh `tools/ukur_token.py` (log vault 078, Q11 dan Q20). Bobot memakai tarif API sebagai "
        "pembanding, karena akunnya langganan.", "",
        "## Empat angka anggaran (Q20)", "",
        "| Angka | Minggu ini | Sasaran |", "|---|---|---|",
        f"| Beban awal sesi baru (median panggilan pertama) | {ribu(b['median'])} dari {b['n']} sesi | sekitar 65 ribu |",
        f"| Kembali ke sesi besar setelah jeda lebih lama dari umur cache | {k['n']} kali ({k['n_200rb']} di atas 200 ribu), "
        f"tulis {juta(k['tulis'])} token | mendekati 0 |",
        f"| Porsi bobot subagent dari agent Opus beralat lengkap | {persen(r['porsi_opus_lengkap'])} | di bawah 20% |",
        f"| Connector dan skill menyala tapi {m['hari']} hari tidak dipakai | {len(m['connector'])} connector, "
        f"{len(m['skill'])} skill | 0 |", "",
        "## Rincian", "",
        f"- Beban awal per entrypoint: {eps}.",
        f"- Kembali setelah jeda: median prompt {ribu(k['median_prompt'])}; tulis yang terhindar bila sesi dipadatkan ke "
        f"130 ribu sebelum jeda: {juta(k['tulis_terhindar_bila_padat'])} token.",
        f"- Umur cache: sesi utama menulis {juta(r['ttl']['utama_1jam'])} token dengan TTL 1 jam dan "
        f"{juta(r['ttl']['utama_5menit'])} dengan TTL 5 menit; subagent {juta(r['ttl']['sub_1jam'])} dan "
        f"{juta(r['ttl']['sub_5menit'])}.",
        f"- Porsi output: {persen(r['porsi_output'])} dari bobot total.",
        "- Bobot sesi utama: " + ", ".join(f"{n} {persen(v)}" for n, v in r["bobot"]["utama"].items())
        + f"; subagent {persen(r['bobot']['subagent'])}. Total setara US${r['bobot']['total_usd_api']} tarif API.",
        "- Subagent per jenis: " + (", ".join(f"{n} {persen(v)}" for n, v in list(r["bobot"]["subagent_per_jenis"].items())[:8]) or "-") + ".",
        f"- Jumlah: {r['jumlah']['sesi_utama']} sesi utama, {r['jumlah']['panggilan_utama']} panggilan utama, "
        f"{r['jumlah']['panggilan_subagent']} panggilan subagent.", "",
        f"## Menganggur {m['hari']} hari", "",
        "- Connector: " + (", ".join(m["connector"]) if m["connector"] else
                           "tidak ada" if m["connector_terbaca"] else "data aplikasi desktop tidak terbaca") + ".",
        "- Skill dengan deskripsi: " + (", ".join(m["skill"]) or "tidak ada") + ".",
        f"- Skill nama saja (murah, sekadar info): {len(m['skill_nama_saja'])}.",
        f"- Daftar skill awal sesi ({m.get('skill_entri', '?')} entri, {ribu(m.get('skill_karakter', 0))} karakter) "
        f"diambil dari `{m['skill_dari']}`.",
    ]
    return "\n".join(baris) + "\n"


def laporan_terakhir(folder):
    files = sorted(glob.glob(os.path.join(folder, "laporan-token-????-??-??.json")))
    return files[-1] if files else None


def baris(folder, hari_ini=None):
    """Satu baris untuk hook awal sesi: ringkasan laporan 7 hari terakhir, peringatan basi, atau ''. Tidak melempar."""
    hari_ini = hari_ini or dt.date.today()
    try:
        path = laporan_terakhir(folder)
        tanggal = dt.date.fromisoformat(os.path.basename(path)[14:24]) if path else None
        if tanggal is None or (hari_ini - tanggal).days > 9:
            if hari_ini >= MULAI + dt.timedelta(days=2):
                return (f"[Anggaran token] Laporan mingguan terakhir {tanggal or 'belum ada'}. Cek tugas laporan harian, "
                        "atau jalankan `python tools/ukur_token.py laporan --simpan \"Riwayat Perckapan\"`.")
            return ""
        if (hari_ini - tanggal).days > 7:
            return ""
        with open(path, encoding="utf-8") as f:
            r = json.load(f)
        b, k, m = r["beban_awal"], r["kembali_jeda"], r["menganggur"]
        return (f"[Anggaran token {tanggal}] beban awal {ribu(b['median'])} (sasaran 65 ribu), kembali setelah jeda "
                f"{k['n']} kali (sasaran 0), Opus beralat lengkap {persen(r['porsi_opus_lengkap'])} bobot subagent "
                f"(sasaran di bawah 20%), menganggur {m['n']} (sasaran 0). Rincian di {path[:-5]}.md.")
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def rincian(path):
    """Pecah panggilan pertama satu sesi per bagian (karakter), lalu ubah ke perkiraan token dengan rasio total dari
    usage-nya. Butuh entri api-request-shape dan api-request-blob (Claude Code 2.1.3xx); transkrip lama hanya memberi total."""
    shape = req = usage = None
    blobs, ep = {}, "?"
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            t = e.get("type")
            if t == "api-request-shape" and shape is None:
                shape = e.get("shape") or {}
            elif t == "api-request" and req is None:
                req = e
            elif t == "api-request-blob":
                blobs[e.get("hash")] = e.get("message") or {}
            elif t == "assistant" and not e.get("isSidechain") and (e.get("message") or {}).get("usage"):
                usage, ep = e["message"]["usage"], e.get("entrypoint") or "?"
                break
    if not usage:
        return None
    total_token = ukuran_prompt(usage)
    if not (shape and req):
        return {"berkas": path, "entrypoint": ep, "token": total_token, "bagian": [], "alat_terbesar": []}
    bagian = Counter()
    bagian["Prompt sistem"] = sum(len(json.dumps(b, ensure_ascii=False)) for b in shape.get("system") or [])
    alat = sorted(((t.get("name") or "?", len(json.dumps(t, ensure_ascii=False))) for t in shape.get("tools") or []),
                  key=lambda x: -x[1])
    bagian[f"Definisi alat ({len(alat)} alat dimuat penuh)"] = sum(n for _, n in alat)
    for h in req.get("tail") or []:
        for p in (blobs.get(h) or {}).get("content") or []:
            s = p.get("text") if isinstance(p, dict) and p.get("type") == "text" else json.dumps(p, ensure_ascii=False)
            posisi = sorted((s.find(tanda), nama) for nama, tanda in PENANDA if s.find(tanda) != -1)
            if not posisi or posisi[0][0] > 200:
                posisi.insert(0, (0, "Pesan pertama dan lainnya"))
            for (awal, nama), (akhir, _) in zip(posisi, posisi[1:] + [(len(s), "")]):
                bagian[nama] += akhir - awal
    total_kar = sum(bagian.values()) or 1
    rasio = total_token / total_kar
    return {"berkas": path, "entrypoint": ep, "token": total_token, "karakter": total_kar,
            "bagian": [(n, k, round(k * rasio)) for n, k in bagian.most_common()],
            "alat_terbesar": [(n, k, round(k * rasio)) for n, k in alat[:8]]}


def cetak_rincian(r):
    if not r:
        print("Tidak ada panggilan dengan usage di transkrip itu.")
        return
    print(f"Beban awal {r['token']:,} token ({r['entrypoint']}), dari {r['berkas']}".replace(",", "."))
    if not r["bagian"]:
        print("Transkrip ini tidak menyimpan bentuk permintaan, jadi hanya totalnya yang terbaca.")
        return
    print(f"Perkiraan per bagian (rasio {r['token'] / r['karakter']:.2f} token per karakter, rata untuk semua bagian):")
    for n, k, tok in r["bagian"]:
        print(f"  {n:48s} {k:>8,} kar  ~{tok:>7,} token  {100 * tok / r['token']:4.1f}%".replace(",", "."))
    print("Alat terbesar: " + ", ".join(f"{n} ~{tok:,}".replace(",", ".") for n, _, tok in r["alat_terbesar"]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Alat ukur anggaran token mingguan (Q11 dan Q20 di log vault 078).")
    p.add_argument("--projects", default=os.path.join(HOME, ".claude", "projects"), help="Folder transkrip Claude Code")
    p.add_argument("--agents", default=os.path.join(HOME, ".claude", "agents"), help="Folder definisi agent khusus")
    p.add_argument("--app-data", help="Folder data aplikasi desktop (bawaan: dicari di ~/AppData/Local/Claude-Data)")
    sub = p.add_subparsers(dest="perintah", required=True)
    lp = sub.add_parser("laporan", help="Empat angka anggaran Q20 dan rinciannya")
    lp.add_argument("--hari", type=int, default=7)
    lp.add_argument("--sampai", help="Tanggal akhir jendela (YYYY-MM-DD, eksklusif). Bawaan: sekarang")
    lp.add_argument("--simpan", help="Folder untuk laporan-token-<tanggal>.md dan .json")
    lp.add_argument("--jatuh-tempo", action="store_true", help="Lewati kalau laporan terakhir belum 7 hari atau sebelum 2026-11-29")
    lp.add_argument("--json", action="store_true", help="Cetak JSON, bukan Markdown")
    rp = sub.add_parser("rincian", help="Pecah beban awal satu sesi per bagian")
    rp.add_argument("--berkas", help="Transkrip sesi (.jsonl). Bawaan: sesi utama terbaru")
    rp.add_argument("--entrypoint", help="Ambil sesi terbaru dengan entrypoint ini, mis. cli atau claude-desktop")
    bp = sub.add_parser("baris", help="Satu baris ringkasan untuk hook awal sesi")
    bp.add_argument("--folder", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Riwayat Perckapan"))
    a = p.parse_args()

    if a.perintah == "baris":
        print(baris(a.folder))
        return
    if a.perintah == "rincian":
        path = a.berkas
        if not path:
            calon = sorted(glob.glob(os.path.join(a.projects, "*", "*.jsonl")), key=os.path.getmtime, reverse=True)
            for c in calon[:200]:
                if not a.entrypoint:
                    path = c
                    break
                with open(c, encoding="utf-8", errors="replace") as f:
                    if any(f'"entrypoint":"{a.entrypoint}"' in l.replace(" ", "") for l, _ in zip(f, range(400))):
                        path = c
                        break
        if not path:
            sys.exit("Tidak ada transkrip yang cocok.")
        cetak_rincian(rincian(path))
        return
    hari_ini = dt.date.today()
    if a.jatuh_tempo:
        terakhir = laporan_terakhir(a.simpan or ".")
        tgl = dt.date.fromisoformat(os.path.basename(terakhir)[14:24]) if terakhir else None
        if hari_ini < MULAI or (tgl and (hari_ini - tgl).days < 7):
            print(f"Belum jatuh tempo (laporan terakhir {tgl or 'belum ada'}, pertama {MULAI}).")
            return
    sampai = (dt.datetime.combine(dt.date.fromisoformat(a.sampai), dt.time(), dt.datetime.now().astimezone().tzinfo)
              if a.sampai else dt.datetime.now().astimezone())
    r = analisis(a.projects, a.agents, a.app_data, sampai, a.hari)
    md = markdown(r)
    if a.simpan:
        os.makedirs(a.simpan, exist_ok=True)
        dasar = os.path.join(a.simpan, f"laporan-token-{hari_ini.isoformat()}")
        with open(dasar + ".json", "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
        with open(dasar + ".md", "w", encoding="utf-8") as f:
            f.write(md)
    print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else md)


if __name__ == "__main__":
    main()
