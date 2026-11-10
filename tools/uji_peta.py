"""Uji setiap skill dan tool yang tercantum di peta kemampuan (PETA_SKILLS_TOOLS.md).

Skill: SKILL.md ada, frontmatter punya name dan description, name sama dengan nama folder, path yang dirujuk ada,
skrip Python dan JavaScript lolos cek sintaks, uji bawaan skill (test_*.py) lulus, dan skill lumbung tidak menyebut
alat khusus satu platform. Salinan bawaan Claude dibandingkan, dan skill di lumbung yang belum masuk peta dilaporkan.
Tool: uji asap per tool. Tool di peta yang belum punya uji asap di sini dilaporkan GAGAL, jadi setiap baris baru di
peta menuntut ujinya ditulis lebih dulu.

  python tools/uji_peta.py [--peta PETA] [--vault VAULT] [--berat] [--laporan BERKAS.md]

--berat ikut menjalankan uji yang lama: uji pagar oper-kerja, yang butuh port 20128 kosong dan Hermes terpasang.
Keluar 1 kalau ada yang GAGAL."""
import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

AKAR = pathlib.Path(__file__).resolve().parents[1]
LULUS, PERINGATAN, GAGAL = "LULUS", "PERINGATAN", "GAGAL"
PLATFORM = re.compile(r"mcp__[A-Za-z_-]+__|~/\.claude/")
RELATIF = re.compile(r"`((?:scripts|references|assets|examples|templates|fixtures|lib)/[^`\s]+)`")
ABSOLUT = re.compile(r"`([A-Za-z]:[\\/][^`<>*]+?)`")


def jalan(perintah, timeout=240, cwd=None):
    try:
        r = subprocess.run([str(x) for x in perintah], capture_output=True, timeout=timeout, cwd=str(cwd or AKAR),
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")
    except FileNotFoundError as e:
        return 127, str(e)
    except subprocess.TimeoutExpired:
        return 124, "batas waktu"


def baca_peta(teks):
    """Baris tabel di bagian 1 (skill) dan bagian 2 (tool): nama di sel pertama, path skill di sel ketiga."""
    skill, tool, bagian = [], [], None
    for l in teks.splitlines():
        if l.startswith("## "):
            bagian = "skill" if l.startswith("## 1.") else "tool" if l.startswith("## 2.") else None
            continue
        if not bagian or not l.startswith("| `"):
            continue
        sel = [s.strip() for s in l.strip().strip("|").split("|")]
        nama = re.findall(r"`([^`]+)`", sel[0])
        if not nama:
            continue
        if bagian == "skill":
            path = re.findall(r"`([^`]+)`", sel[2]) if len(sel) > 2 else []
            skill.append((nama[0], path[0] if path else f"{nama[0]}/SKILL.md"))
        else:
            tool.append(nama[0])
    return skill, tool


def frontmatter(teks):
    m = re.match(r"---\r?\n(.*?)\r?\n---", teks, re.S)
    data = {}
    for l in (m.group(1).splitlines() if m else []):
        if re.match(r"^[A-Za-z_-]+:", l):
            k, v = l.split(":", 1)
            data[k.strip()] = v.strip().strip("'\"")
    return data


class Hasil:
    def __init__(self):
        self.status, self.catatan = LULUS, []

    def turun(self, status, pesan):
        if status == GAGAL or (status == PERINGATAN and self.status == LULUS):
            self.status = status
        self.catatan.append(pesan)


def penerjemah(berkas):
    """Uji yang memakai Playwright jalan di venv-nya. Selain itu Python yang menjalankan alat ini."""
    pw = AKAR / "tools" / "playwright-venv" / "Scripts" / "python.exe"
    return pw if pw.exists() and "playwright" in berkas.read_text(encoding="utf-8", errors="replace") else pathlib.Path(sys.executable)


def uji_skill(path, akar_skill, akar_claude):
    h = Hasil()
    f = akar_skill / path
    if not f.exists():
        h.turun(GAGAL, f"{path} tidak ada")
        return h
    teks = f.read_text(encoding="utf-8", errors="replace")
    fm = frontmatter(teks)
    if not fm.get("name") or "description" not in fm:
        h.turun(GAGAL, "frontmatter tanpa name atau description")
    elif fm["name"] != f.parent.name:
        h.turun(PERINGATAN, f"name '{fm['name']}' beda dengan folder '{f.parent.name}'")
    for p in sorted(set(RELATIF.findall(teks))):
        p = p.rstrip(".,):")
        if "<" not in p and "*" not in p and "…" not in p and "..." not in p and not (f.parent / p).exists():
            h.turun(GAGAL, f"rujukan {p} tidak ada")
    for p in sorted(set(ABSOLUT.findall(teks))):
        p = re.split(r" (?:-|<|\[)", p)[0].strip()
        if not os.path.exists(p):
            h.turun(PERINGATAN, f"path {p} tidak ada")
    for s in sorted(f.parent.rglob("*")):
        bagian = s.relative_to(f.parent).parts
        if not s.is_file() or ".git" in bagian or "assets" in bagian:
            continue
        if s.suffix == ".py":
            try:
                compile(s.read_text(encoding="utf-8", errors="replace"), str(s), "exec")
            except SyntaxError as e:
                h.turun(GAGAL, f"sintaks {s.name}: {e.msg}, baris {e.lineno}")
        elif s.suffix in (".js", ".mjs") and shutil.which("node"):
            k, o = jalan(["node", "--check", s])
            if k:
                h.turun(GAGAL, f"sintaks {s.name}: {(o.strip().splitlines() or ['?'])[-1][:80]}")
    for t in sorted(f.parent.rglob("test_*.py")):
        k, o = jalan([penerjemah(t), "-B", t], timeout=600, cwd=t.parent)
        if k:
            h.turun(GAGAL, f"{t.name} gagal: {(o.strip().splitlines() or ['?'])[-1][:80]}")
        else:
            h.catatan.append(f"{t.name} lulus")
    if PLATFORM.search(teks):
        h.turun(PERINGATAN, "menyebut alat atau path khusus satu platform")
    c = akar_claude / f.parent.name / "SKILL.md"
    if c.exists():
        sama = c.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n") == teks.replace("\r\n", "\n")
        h.catatan.append("salinan Claude sama" if sama else "salinan Claude berbeda")
    return h


def uji_tool(nama, vault, berat):
    """Uji asap satu tool. Tool yang belum ada di sini dilaporkan GAGAL."""
    h = Hasil()
    py = pathlib.Path(sys.executable)
    venv = lambda n: AKAR / "tools" / n / "Scripts" / "python.exe"
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t)
        if nama == "rag_engine.py":
            k, o = jalan([venv("rag-venv"), "-B", "tools/rag_engine.py", "search", "Referensi Desain", "--k", "1"], timeout=600)
            ok, pesan = k == 0 and "Referensi Desain" in o, "mencari 'Referensi Desain' di vault"
        elif nama == "vault_lint.py":
            k, o = jalan([py, "-B", "tools/vault_lint.py", vault], timeout=300)
            ok, pesan = k == 0 and "# Lint Vault" in o, "lint vault"
        elif nama == "sync_rules.py":
            k, o = jalan([py, "-B", "tools/sync_rules.py", "--check"])
            ok, pesan = k == 0, "--check, semua salinan aturan sama"
        elif nama == "markitdown":
            (t / "uji.html").write_text("<html><body><h1>Uji MarkItDown</h1></body></html>", encoding="utf-8")
            k, o = jalan([AKAR / "tools" / "markitdown-venv" / "Scripts" / "markitdown.exe", t / "uji.html"])
            ok, pesan = k == 0 and "Uji MarkItDown" in o, "HTML kecil menjadi Markdown"
        elif nama == "pdf_parser.py":
            k, o = jalan([venv("opendataloader-venv"), "-B", "tools/pdf_parser.py", "--help"])
            ok, pesan = k == 0, "hanya --help, belum mengurai PDF"
        elif nama == "design_lint.mjs":
            (t / "uji.html").write_text("<html><head><style>.h{background:linear-gradient(90deg,#7c3aed,#2563eb)}</style></head>"
                                        "<body><section class='h'><h1>Uji</h1></section></body></html>", encoding="utf-8")
            k, o = jalan(["node", AKAR / "tools" / "design-kit" / "design_lint.mjs", t / "uji.html"])
            ok, pesan = "purple-gradient" in o, "menangkap gradien ungu di HTML uji"
        elif nama == "export_transcript.py":
            k, o = jalan([py, "-B", "tools/export_transcript.py", "--help"])
            ok, pesan = k == 0, "hanya --help. Logika sensornya diuji test_tools.py"
        elif nama == "uji_agen.py":
            k, o = jalan([py, "-B", "tools/uji_agen.py", "--help"])
            ok, pesan = k == 0 and "skor" in o, "--help. Penilaiannya diuji test_tools.py, run agent sungguhan tidak dijalankan di sini"
        elif nama == "cek_proses_sisa.py":
            k, o = jalan([py, "-B", "tools/cek_proses_sisa.py", "--sejak", "10m"])
            ok, pesan = k == 0 and "proses alat sejak 10m" in o, "daftar proses sungguhan 10 menit terakhir. Logika hook-nya diuji test_tools.py"
        elif nama == "putar_log.py":
            k, o = jalan([py, "-B", "tools/putar_log.py", "--vault", vault, "--cek"])
            ok, pesan = k in (0, 1) and "entri" in o, "--cek pada vault, tanpa menulis"
        elif nama == "medusa":
            k, o = jalan([AKAR / "tools" / "medusa-venv" / "Scripts" / "medusa.exe", "--version"])
            ok, pesan = k == 0 and "MEDUSA" in o, "hanya --version. Pindaian penuh berat untuk RAM mesin ini"
        elif nama == "oper_kerja.py":
            k, o = jalan([py, "-B", "tools/oper_kerja.py", "--help"])
            ok, pesan = k == 0, "--help. Alurnya diuji test_tools.py"
            if ok and berat:
                k, o = jalan([py, "-B", AKAR / "skills" / "oper-kerja" / "scripts" / "uji_pagar.py"], timeout=900)
                ok, pesan = k == 0, "uji pagar pekerja: " + ((o.strip().splitlines() or ["?"])[-1][:60])
        elif nama == "test_tools.py":
            k, o = jalan([venv("rag-venv"), "-B", "tools/test_tools.py"], timeout=600)
            ok, pesan = k == 0 and re.search(r"(?m)^OK", o) is not None, (re.findall(r"Ran \d+ tests", o) or ["?"])[-1]
        elif nama == "playwright-venv":
            k, o = jalan([venv("playwright-venv"), "-c", "from playwright._repo_version import version; print(version)"])
            ok, pesan = k == 0 and "1.64.1" in o, "versi " + o.strip()[:20]
        elif nama == "axe-core":
            f = AKAR / "tools" / "axe-core" / "axe.min.js"
            ok, pesan = f.exists() and f.stat().st_size > 100_000, f"axe.min.js {f.stat().st_size if f.exists() else 0} byte"
        else:
            h.turun(GAGAL, "belum ada uji asap di tools/uji_peta.py")
            return h
    h.turun(LULUS if ok else GAGAL, pesan)
    return h


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Uji setiap skill dan tool di peta kemampuan.")
    p.add_argument("--peta", default=str(AKAR / "PETA_SKILLS_TOOLS.md"))
    p.add_argument("--vault", default=r"D:\Obsidian\All Sources\AI Workspace")
    p.add_argument("--berat", action="store_true", help="Ikut menjalankan uji yang lama (uji pagar oper-kerja)")
    p.add_argument("--laporan", help="Tulis tabel hasil ke berkas Markdown ini")
    a = p.parse_args()
    skill, tool = baca_peta(pathlib.Path(a.peta).read_text(encoding="utf-8"))
    akar_skill, akar_claude = AKAR / "skills", pathlib.Path.home() / ".claude" / "skills"
    baris = []
    for nama, path in skill:
        h = uji_skill(path, akar_skill, akar_claude)
        baris.append(("skill", nama, h))
    terpeta = {pathlib.Path(path).parts[0] for _, path in skill}
    for d in sorted(akar_skill.iterdir()):
        if (d / "SKILL.md").exists() and d.name not in terpeta:
            h = Hasil()
            h.turun(PERINGATAN, "ada di lumbung, belum masuk peta")
            baris.append(("skill", d.name, h))
    for nama in tool:
        baris.append(("tool", nama, uji_tool(nama, a.vault, a.berat)))
    keluaran = ["| Jenis | Nama | Hasil | Catatan |", "|---|---|---|---|"]
    keluaran += [f"| {j} | `{n}` | {h.status} | {'. '.join(h.catatan) or '-'} |" for j, n, h in baris]
    hitung = {s: sum(1 for *_, h in baris if h.status == s) for s in (LULUS, PERINGATAN, GAGAL)}
    keluaran.append(f"\n{len(baris)} baris: {hitung[LULUS]} lulus, {hitung[PERINGATAN]} peringatan, {hitung[GAGAL]} gagal.")
    teks = "\n".join(keluaran)
    print(teks)
    if a.laporan:
        pathlib.Path(a.laporan).write_text(teks + "\n", encoding="utf-8")
    sys.exit(1 if hitung[GAGAL] else 0)


if __name__ == "__main__":
    main()
