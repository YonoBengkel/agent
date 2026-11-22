"""Hook PreToolUse Claude Code untuk alat Agent (aturan inti 3; Q3 dan Q19 di log vault 078, dipasang 2026-11-22).
Pemanggilan subagent tanpa `model` eksplisit ditolak, supaya subagent tidak diam-diam mewarisi Opus dengan alat
lengkap. Pada 2026-11-15 sampai 2026-11-22, agent seperti itu memegang 83% bobot subagent (log 079). Lolos tanpa
keluaran: pemanggilan yang menyebut `model`, fork (selalu memakai model sesi), dan agent khusus yang definisinya di
~/.claude/agents menyebut `model:` (pencari, peneliti, peninjau).

  python tools/penjaga_subagent.py [--agents <folder definisi agent>]

Penolakan berisi saran model dan agent beralat sempit, jadi model cukup mengulang pemanggilan dengan `model`. Galat apa
pun berarti lolos tanpa keluaran."""
import argparse
import glob
import json
import os
import re
import sys

ALASAN = ("Penjaga subagent (aturan inti 3, log vault 079): sebutkan `model` di pemanggilan Agent. Pakai \"haiku\" "
          "untuk lookup sederhana, \"sonnet\" untuk riset, pencarian, dan sebagian besar kerja, dan \"opus\" hanya kalau "
          "tugasnya memang butuh. Untuk pencarian berkas lokal pakai `pencari` (pengganti Explore), riset web `peneliti`, "
          "dan tinjauan `peninjau`. Ulangi pemanggilan dengan `model` yang dipilih.")


def punya_model(agents_dir, jenis):
    """True kalau definisi agent khusus `jenis` menyebut baris `model:` di frontmatter-nya."""
    for p in glob.glob(os.path.join(agents_dir, "*.md")):
        try:
            with open(p, encoding="utf-8") as f:
                kepala = f.read(3000)
        except OSError:
            continue
        m = re.search(r"(?m)^name:\s*(\S+)", kepala)
        if m and m.group(1) == jenis:
            return re.search(r"(?m)^model:\s*\S", kepala) is not None
    return False


def putuskan(payload, agents_dir):
    if payload.get("tool_name") not in ("Agent", "Task"):
        return None
    masukan = payload.get("tool_input") or {}
    jenis = masukan.get("subagent_type") or "general-purpose"
    if masukan.get("model") or jenis == "fork" or punya_model(agents_dir, jenis):
        return None
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": ALASAN}}


def main():
    p = argparse.ArgumentParser(description="Hook PreToolUse Agent: tolak subagent tanpa model eksplisit (aturan inti 3).")
    p.add_argument("--agents", default=os.path.join(os.path.expanduser("~"), ".claude", "agents"))
    a = p.parse_args()
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        out = putuskan(payload, a.agents) if isinstance(payload, dict) else None
    except Exception:
        return
    if out:
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
