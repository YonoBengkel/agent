import os
import re
import sys
import json
import argparse
import datetime

LOW_PRIORITY = ("## Catatan kompilasi", "## Rujukan")   # bagian halaman proyek yang dilepas dulu kalau terlalu panjang

def compile_reminder(vault):
    """Pengingat Kompilasi yang dipaksa sistem (2026-10-16): hitung log sesi yang berubah sesudah hari kompilasi
    terakhir di Wiki/log.md. Log yang berubah di hari kompilasi itu sendiri tidak dihitung, jadi angkanya batas bawah."""
    try:
        with open(os.path.join(vault, "Wiki", "log.md"), encoding="utf-8-sig") as f:
            dates = re.findall(r"(?m)^## \[(\d{4}-\d{2}-\d{2})\] compile\b", f.read())
    except OSError:
        return ""
    if not dates:
        return ""
    last = max(dates)
    after = datetime.datetime.strptime(last, "%Y-%m-%d").timestamp() + 86400
    n = sum(1 for dp, _, fn in os.walk(os.path.join(vault, "Log")) for f in fn
            if f.endswith(".md") and os.path.getmtime(os.path.join(dp, f)) >= after)
    advice = " Ambang Aturan 12 (≥5) terlewati: tawarkan `kompilasi`." if n >= 5 else ""
    return f"\n\n[Pengingat Kompilasi] {n} log sesi berubah sesudah kompilasi terakhir ({last}).{advice}"

def hot_context(hot):
    """Mode AI Agent: muat hot.md (Aturan 1), plus pengingat Kompilasi."""
    try:
        with open(hot, encoding="utf-8-sig") as f:
            text = f.read()
    except OSError as e:
        text = f"[hot.md tidak bisa dibaca: {e}. Baca manual sesuai Aturan 1.]"
    return ("Isi hot.md, dimuat otomatis di awal sesi (Aturan 1). Ini cache; detail ada di index.md dan KONTEKS_PROYEK.md.\n\n"
            + text + compile_reminder(os.path.dirname(os.path.abspath(hot))))

def project_context(root, vault, skip):
    """Mode proyek (D:\\CODE\\AGENTS.md): muat halaman proyek dari vault untuk folder kerja sesi ini."""
    try:
        cwd = json.load(sys.stdin).get("cwd") or os.getcwd()
    except ValueError:
        cwd = os.getcwd()
    try:
        rel = os.path.relpath(os.path.abspath(cwd), os.path.abspath(root))
    except ValueError:   # beda drive di Windows
        return None
    if rel == "." or rel.startswith(".."):
        return None
    project = rel.split(os.sep)[0]
    if project in skip:
        return None
    folder = os.path.join(os.path.abspath(root), project)
    if os.path.exists(os.path.join(folder, ".no-vault")):
        return f"Proyek `{project}` memakai `.no-vault`: jangan membaca atau menulis catatan vault untuk proyek ini (D:\\CODE\\AGENTS.md)."
    vault = os.path.normpath(vault)
    page = os.path.join(vault, "Wiki", "projects", project + ".md")
    head = f"Konteks proyek `{project}` ({folder}), dimuat otomatis di awal sesi sesuai D:\\CODE\\AGENTS.md."
    try:
        with open(page, encoding="utf-8-sig") as f:
            text = f.read()
    except OSError:
        return (f"{head}\nBelum ada halaman proyek di vault ({page}). Bekerja seperti biasa; buat halaman itu di titik "
                f"penting pertama, dan tulis log sesi ke {os.path.join(vault, 'Log', project)}.")
    if len(text) > 9200:   # batas konteks hook 10.000 karakter, termasuk kepala di bawah
        # Bagian yang paling jarang dibutuhkan di awal sesi dilepas dulu, baru sisanya dipotong (2026-10-16)
        parts = re.split(r"(?m)^(?=## )", text)
        dropped = [p.splitlines()[0][3:].strip() for p in parts if p.startswith(LOW_PRIORITY)]
        if dropped:
            text = "".join(p for p in parts if not p.startswith(LOW_PRIORITY)).rstrip()
            text += f"\n\n[Bagian tidak dimuat agar muat di konteks: {', '.join(dropped)}. Baca di {page}]"
    if len(text) > 9200:
        text = text[:9200] + f"\n\n[… dipotong; baca sisanya di {page}]"
    return f"{head} Sumber: {page}. Log sesi ditulis ke folder log yang disebut di halaman ini.\n\n{text}"

def main():
    parser = argparse.ArgumentParser(description="Hook SessionStart: muat hot.md (mode AI Agent) atau halaman proyek dari vault (mode proyek).")
    parser.add_argument("hot", nargs="?", help="Path ke hot.md (mode AI Agent)")
    parser.add_argument("--projects-root", help="Folder induk proyek, mis. D:/CODE (mode proyek; folder kerja dibaca dari stdin hook)")
    parser.add_argument("--vault", help="Path vault memori (mode proyek)")
    parser.add_argument("--skip", action="append", default=[], help="Nama folder proyek yang dilewati, mis. 'AI Agent' (boleh diulang)")
    args = parser.parse_args()

    if args.projects_root:
        if not args.vault:
            parser.error("--vault wajib di mode proyek")
        context = project_context(args.projects_root, args.vault, set(args.skip))
    elif args.hot:
        context = hot_context(args.hot)
    else:
        parser.error("beri path hot.md atau --projects-root")
    if context:
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}, ensure_ascii=False))

if __name__ == "__main__":
    main()
