"""Hook Stop Claude Code untuk jurnal (rancangan 2 di log vault 073, dipasang 2026-11-21). Kalau sesi ini mengubah berkas
proyek di bawah --projects-root sesudah tulisan terakhirnya ke folder Log vault, agent ditahan sekali dengan alasan
singkat supaya menulis log sesi (Aturan 4) atau menyebut kenapa tidak perlu. Isi log tetap ditulis agent.

Batas: tidak menahan saat stop_hook_active, tidak menahan dua kali untuk perubahan yang sama (penanda per sesi di folder
sementara), dan melewati proyek yang punya .no-vault. Yang dihitung hanya Edit, Write, MultiEdit, dan NotebookEdit yang
berhasil, karena tulisan lewat shell tidak terbaca dari transkrip. Galat skrip ini tidak pernah menahan agent.

  python tools/cek_jurnal.py --hook --vault <vault> --projects-root D:/CODE"""
import argparse
import json
import os
import sys
import tempfile

ALAT_TULIS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

def di_dalam(path, folder):
    path, folder = (os.path.normcase(os.path.abspath(p)) for p in (path, folder))
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:   # beda drive
        return False

def tulisan(transkrip):
    """[(nomor baris, path)] setiap tulisan berkas yang berhasil, urut sesuai transkrip."""
    pakai, gagal = {}, set()
    with open(transkrip, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if '"tool_use"' not in line and '"tool_result"' not in line:
                continue
            try:
                isi = (json.loads(line).get("message") or {}).get("content")
            except (ValueError, AttributeError):
                continue
            for b in isi if isinstance(isi, list) else []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use" and b.get("name") in ALAT_TULIS:
                    masukan = b.get("input") or {}
                    path = masukan.get("file_path") or masukan.get("notebook_path")
                    if path:
                        pakai[b.get("id")] = (i, path)
                elif b.get("type") == "tool_result" and b.get("is_error"):
                    gagal.add(b.get("tool_use_id"))
    return sorted(v for k, v in pakai.items() if k not in gagal)

def tanpa_vault(path, root):
    """Berkas ini milik proyek yang memilih keluar dari vault (.no-vault di akar foldernya)."""
    bagian = os.path.relpath(path, root).split(os.sep)
    return os.path.exists(os.path.join(root, bagian[0], ".no-vault"))

def periksa(payload, vault, root, state_dir):
    """Keputusan hook sebagai dict untuk dicetak, atau None kalau agent tidak perlu ditahan."""
    if payload.get("stop_hook_active") or not payload.get("transcript_path"):
        return None
    semua = tulisan(payload["transcript_path"])
    log = os.path.join(vault, "Log")
    penanda = os.path.join(state_dir, f"{payload.get('session_id') or 'tanpa-id'}.json")
    try:
        with open(penanda, encoding="utf-8") as f:
            sudah = json.load(f).get("baris", -1)
    except (OSError, ValueError, AttributeError):
        sudah = -1
    batas = max([sudah] + [i for i, p in semua if di_dalam(p, log)])
    berubah = sorted({p for i, p in semua if i > batas and di_dalam(p, root) and not di_dalam(p, vault)
                      and not tanpa_vault(p, root)})
    if not berubah:
        return None
    os.makedirs(state_dir, exist_ok=True)
    with open(penanda, "w", encoding="utf-8") as f:
        json.dump({"baris": max(i for i, _ in semua)}, f)
    contoh = ", ".join(os.path.relpath(p, root) for p in berubah[:3])
    return {"decision": "block", "reason": (
        f"Cek jurnal (Aturan 4): {len(berubah)} berkas proyek berubah sesudah log vault terakhir di sesi ini, misalnya "
        f"{contoh}. Catat ke log sesi di vault, atau sebutkan ke pengguna kenapa tidak perlu. Penahanan ini hanya sekali "
        "untuk perubahan yang sama.")}

def main():
    p = argparse.ArgumentParser(description="Hook Stop: tahan agent sekali kalau berkas proyek berubah tanpa log vault.")
    p.add_argument("--hook", action="store_true", help="Baca JSON hook Stop dari stdin (satu-satunya mode)")
    p.add_argument("--vault", required=True)
    p.add_argument("--projects-root", required=True)
    p.add_argument("--state-dir", default=os.path.join(tempfile.gettempdir(), "cek_jurnal"))
    a = p.parse_args()
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
        keluar = periksa(payload, a.vault, a.projects_root, a.state_dir)
    except Exception as e:   # galat skrip ini tidak boleh menahan agent
        print(f"cek_jurnal gagal: {type(e).__name__}: {e}", file=sys.stderr)
        return
    if keluar:
        print(json.dumps(keluar, ensure_ascii=False))

if __name__ == "__main__":
    main()
