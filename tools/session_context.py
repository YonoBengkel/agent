import os
import re
import sys
import json
import argparse
import datetime
import subprocess

LOW_PRIORITY = ("## Catatan kompilasi", "## Rujukan")   # bagian halaman proyek yang dilepas dulu kalau terlalu panjang
KATA_IZIN = re.compile(r"(?i)\bpakai konteks\b")   # kata izin pengguna untuk mengirim isi vault ke model Hermes (2026-11-11)
CONTRACT_ROW = re.compile(r"^\|\s*\[\[([^\]|]+)(?:\|[^\]]*)?\]\]\s*\|(.*)\|$")   # | [[Proyek]] | berkas | arah |

def compile_reminder(vault):
    """Pengingat Kompilasi yang dipaksa sistem (2026-10-16): hitung log sesi yang berubah sesudah hari kompilasi
    terakhir di Wiki/log.md. Log yang berubah di hari kompilasi itu sendiri tidak dihitung, jadi angkanya batas bawah.
    Sejak 2026-11-10 log.md hanya memuat bulan berjalan, jadi kalau di sana belum ada kompilasi, bulan-bulan
    sebelumnya dicari di Riwayat/log <YYYY-MM>.md (tools/putar_log.py), dari yang terbaru."""
    riwayat = os.path.join(vault, "Riwayat")
    lama = sorted((f for f in (os.listdir(riwayat) if os.path.isdir(riwayat) else []) if re.fullmatch(r"log \d{4}-\d{2}\.md", f)), reverse=True)
    dates = []
    for p in [os.path.join(vault, "Wiki", "log.md")] + [os.path.join(riwayat, f) for f in lama]:
        try:
            with open(p, encoding="utf-8-sig") as f:
                dates = re.findall(r"(?m)^## \[(\d{4}-\d{2}-\d{2})\] compile\b", f.read())
        except OSError:
            continue
        if dates:
            break
    if not dates:
        return ""
    last = max(dates)
    after = datetime.datetime.strptime(last, "%Y-%m-%d").timestamp() + 86400
    n = sum(1 for dp, _, fn in os.walk(os.path.join(vault, "Log")) for f in fn
            if f.endswith(".md") and os.path.getmtime(os.path.join(dp, f)) >= after)
    advice = " Ambang Aturan 12 (≥5) terlewati: tawarkan `kompilasi`." if n >= 5 else ""
    return f"\n\n[Pengingat Kompilasi] {n} log sesi berubah sesudah kompilasi terakhir ({last}).{advice}"

def canary_warning(root=None):
    """Satu baris kalau canary lintas agent sudah basi, karena aturan, hook, versi agent, atau modelnya berubah sesudah run
    terakhir (riset 2026-11-13, M4). Folder proyek bawaannya induk workspace ini (D:/CODE/AI Agent/tools -> D:/CODE)."""
    try:
        import uji_agen
        line = uji_agen.peringatan_basi(root or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    except Exception:
        return ""
    return f"\n\n{line}" if line else ""

def hot_context(hot, root=None):
    """Mode AI Agent: muat hot.md (Aturan 1), plus pengingat Kompilasi dan peringatan canary basi."""
    try:
        with open(hot, encoding="utf-8-sig") as f:
            text = f.read()
    except OSError as e:
        text = f"[hot.md tidak bisa dibaca: {e}. Baca manual sesuai Aturan 1.]"
    return ("Isi hot.md, dimuat otomatis di awal sesi (Aturan 1). Ini cache; detail ada di index.md dan KONTEKS_PROYEK.md.\n\n"
            + text + compile_reminder(os.path.dirname(os.path.abspath(hot))) + canary_warning(root))

def project_name(root, cwd):
    """Folder proyek tingkat pertama di bawah root untuk folder kerja ini, atau None kalau di luar root."""
    try:
        rel = os.path.relpath(os.path.abspath(cwd), os.path.abspath(root))
    except ValueError:   # beda drive di Windows
        return None
    if rel == "." or rel.startswith(".."):
        return None
    return rel.split(os.sep)[0]

def design_line(vault, project):
    """Baris proyek ini dari tabel "Kontrak desain proyek" di Wiki/system/Referensi Desain.md, atau None (2026-11-08).
    Ditaruh paling atas konteks, karena halaman proyek yang panjang terpotong sebelum bagian desainnya."""
    page = os.path.join(vault, "Wiki", "system", "Referensi Desain.md")
    try:
        with open(page, encoding="utf-8-sig") as f:
            text = f.read()
    except OSError:
        return None
    table = next((s for s in re.split(r"(?m)^## ", text) if s.startswith("Kontrak desain proyek")), "")
    for line in table.splitlines():
        m = CONTRACT_ROW.match(line.strip())
        if m and m.group(1).strip() == project:
            cells = [c.strip() for c in m.group(2).split("|") if c.strip()]
            return (f"Kontrak desain proyek ini, dari tabel Kontrak desain proyek di {page}: {'. '.join(cells)}. "
                    "Di setiap keputusan desain, buka halaman itu dulu dan mulai dari referensi proyek ini.")
    return None

def commit_warning(vault, folder, project, page, text):
    """Pelajaran #25 (2026-11-10): satu baris peringatan kalau repo proyek punya komit di hari yang lebih baru daripada
    catatan vault terakhirnya (halaman proyek atau log di folder lognya), dibandingkan per hari seperti
    vault_lint.project_activity. Kosong kalau bukan repo git, git gagal atau lambat, atau tidak ada komit baru."""
    if not os.path.exists(os.path.join(folder, ".git")):
        return ""
    try:
        import vault_lint as vl   # aturan folder log yang sama dengan lint
        m = vl.LOG_FOLDER.search(text)
        logs = [m.group(1)] if m else [f"Log/{project}"]
        noted = max([t for t in (vl.latest_mtime(os.path.join(vault, l), ".md") for l in logs) if t] + [os.path.getmtime(page)])
        day = datetime.date.fromtimestamp(noted)
        r = subprocess.run(["git", "-C", folder, "log", f"--since={day + datetime.timedelta(days=1)} 00:00:00",
                            "--format=%cs %s", "-n", "21"], capture_output=True, timeout=5)
        rows = [l for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()] if r.returncode == 0 else []
    except Exception:
        return ""
    if not rows:
        return ""
    n = "lebih dari 20" if len(rows) > 20 else str(len(rows))
    return (f"[Peringatan komit] Repo ini punya {n} komit sesudah catatan vault terakhirnya ({day}), yang terbaru: "
            f"{rows[0][:120]}. Lihat `git log` sejak tanggal itu, lalu catat status atau keputusan baru di halaman proyek (Pelajaran #25).")

def project_context(root, vault, project):
    """Mode proyek (D:\\CODE\\AGENTS.md): muat halaman proyek dari vault untuk folder kerja sesi ini."""
    folder = os.path.join(os.path.abspath(root), project)
    if os.path.exists(os.path.join(folder, ".no-vault")):
        return f"Proyek `{project}` memakai `.no-vault`: jangan membaca atau menulis catatan vault untuk proyek ini (D:\\CODE\\AGENTS.md)."
    vault = os.path.normpath(vault)
    page = os.path.join(vault, "Wiki", "projects", project + ".md")
    head = f"Konteks proyek `{project}` ({folder}), dimuat otomatis di awal sesi sesuai D:\\CODE\\AGENTS.md."
    design = design_line(vault, project)
    top = f"\n\n{design}" if design else ""
    try:
        with open(page, encoding="utf-8-sig") as f:
            text = f.read()
    except OSError:
        return (f"{head}\nBelum ada halaman proyek di vault ({page}). Bekerja seperti biasa; buat halaman itu di titik "
                f"penting pertama, dan tulis log sesi ke {os.path.join(vault, 'Log', project)}.{top}")
    warning = commit_warning(vault, folder, project, page, text)
    top += f"\n\n{warning}" if warning else ""
    budget = 9200 - len(top)   # batas konteks hook 10.000 karakter, termasuk kepala, baris desain, dan peringatan komit
    if len(text) > budget:
        # Bagian yang paling jarang dibutuhkan di awal sesi dilepas dulu, baru sisanya dipotong (2026-10-16)
        parts = re.split(r"(?m)^(?=## )", text)
        dropped = [p.splitlines()[0][3:].strip() for p in parts if p.startswith(LOW_PRIORITY)]
        if dropped:
            text = "".join(p for p in parts if not p.startswith(LOW_PRIORITY)).rstrip()
            text += f"\n\n[Bagian tidak dimuat agar muat di konteks: {', '.join(dropped)}. Baca di {page}]"
    if len(text) > budget:
        text = text[:budget] + f"\n\n[… dipotong; baca sisanya di {page}]"
    return f"{head} Sumber: {page}. Log sesi ditulis ke folder log yang disebut di halaman ini.{top}\n\n{text}"

def hermes_context(args, payload):
    """Hermes, sejak 2026-11-11 atas persetujuan pengguna: isi vault tidak dikirim otomatis, karena sesi Hermes memakai
    model gratis yang isinya bisa dibaca peninjau manusia (keputusan 31). Giliran pertama hanya mendapat satu kalimat
    pemberitahuan tanpa isi vault. Halaman proyek, atau hot.md di folder yang di-skip (AI Agent), baru dikirim di
    giliran yang pesannya memuat kata izin `pakai konteks`. Folder sesi dibaca dari state.db, karena semua sesi jalan
    di satu gateway dan cwd di payload hanya folder gateway."""
    extra = payload.get("extra") or {}
    pesan = extra.get("user_message")
    teks = pesan if isinstance(pesan, str) else json.dumps(pesan, ensure_ascii=False) if pesan else ""
    izin = KATA_IZIN.search(teks) is not None
    if not izin and not extra.get("is_first_turn"):
        return None
    import vault_guard as g
    # session_cwd hanya melayani pre_tool_call; dipanggil apa adanya dengan nama event itu, supaya penjaga vault tidak berubah
    cwd = g.session_cwd(dict(payload, hook_event_name="pre_tool_call")) or payload.get("cwd") or os.getcwd()
    project = project_name(args.projects_root, cwd)
    if not project:
        return None
    if project not in args.skip and os.path.exists(os.path.join(args.projects_root, project, ".no-vault")):
        return project_context(args.projects_root, args.vault, project)   # hanya larangan .no-vault, tanpa isi vault
    if izin:
        return hot_context(args.hot, args.projects_root) if project in args.skip else project_context(args.projects_root, args.vault, project)
    sumber = "hot.md" if project in args.skip else "halaman proyek"
    return (f"Konteks proyek `{project}` ({sumber}) ada di vault, tapi tidak dikirim otomatis karena sesi ini memakai model "
            "gratis (keputusan 31). Jangan membaca berkas vault sendiri. Kalau tugas ini butuh konteks proyek, minta pengguna "
            "mengetik `pakai konteks` di pesan berikutnya.")

def main():
    parser = argparse.ArgumentParser(description="Hook awal sesi: muat hot.md (mode AI Agent) atau halaman proyek dari vault (mode proyek).")
    parser.add_argument("hot", nargs="?", help="Path ke hot.md (mode AI Agent; di mode proyek dipakai untuk proyek yang di-skip)")
    parser.add_argument("--projects-root", help="Folder induk proyek, mis. D:/CODE (mode proyek; folder kerja dibaca dari stdin hook)")
    parser.add_argument("--vault", help="Path vault memori (mode proyek)")
    parser.add_argument("--skip", action="append", default=[], help="Nama folder proyek yang dilewati, mis. 'AI Agent' (boleh diulang)")
    parser.add_argument("--format", choices=("claude", "hermes", "antigravity"), default="claude",
                        help="claude: SessionStart Claude Code. hermes: pre_llm_call Hermes, isi vault hanya sesudah kata izin "
                             "`pakai konteks` (2026-11-11). "
                             "antigravity: SessionStart Antigravity, konteks lewat injectSteps (2026-11-08)")
    args = parser.parse_args()

    payload = {}
    if args.projects_root or args.format == "hermes":
        try:
            payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))   # bukan pengodean konsol Windows
        except ValueError:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if args.format == "hermes":
        if not (args.projects_root and args.vault):
            parser.error("format hermes butuh --projects-root dan --vault")
        context = hermes_context(args, payload)   # pre_llm_call jalan di setiap giliran
        if context:
            sys.stdout.reconfigure(encoding="utf-8")
            print(json.dumps({"context": context}, ensure_ascii=False))
        return
    if args.projects_root and not args.vault:
        parser.error("--vault wajib di mode proyek")
    if not (args.projects_root or args.hot):
        parser.error("beri path hot.md atau --projects-root")
    try:
        if args.projects_root:
            # Antigravity tidak mengirim cwd, hanya daftar folder workspace
            cwd = payload.get("cwd") or next(iter(payload.get("workspacePaths") or []), None) or os.getcwd()
            project = project_name(args.projects_root, cwd)
            if project and project in args.skip:
                context = hot_context(args.hot, args.projects_root) if args.hot else None   # mis. AI Agent: halamannya hot.md (Aturan 1)
            else:
                context = project_context(args.projects_root, args.vault, project) if project else None
        else:
            context = hot_context(args.hot)
    except Exception as e:
        if args.format != "antigravity":
            raise
        # Hook Antigravity yang gagal ikut menggagalkan langkahnya, jadi konteks yang hilang lebih aman
        print(f"session_context gagal ({type(e).__name__}: {e}), sesi jalan tanpa konteks.", file=sys.stderr)
        context = None
    if args.format == "antigravity":
        # systemMessage harus objek. Keluaran ASCII supaya aman dibaca apa pun pengodean konsol, dan {} kalau tidak ada konteks
        out = {"injectSteps": [{"systemMessage": {"systemMessage": context}}]} if context else {}
        print(json.dumps(out))
    elif context:
        sys.stdout.reconfigure(encoding="utf-8")
        out = ({"context": context} if args.format == "hermes"
               else {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}})
        print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    main()
