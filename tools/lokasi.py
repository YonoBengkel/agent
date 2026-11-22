"""Lokasi bawaan workspace: vault memori dan folder kerja, supaya tidak ada tool yang menanam path satu mesin.

Vault dicari berurutan: variabel lingkungan AGENT_VAULT, kunci "vault" di Konfigurasi/rule_sync.json (ditulis pasang.py),
lalu induk folder cadangan aturan di registry yang sama (backup.dir selalu <vault>/Cadangan Aturan). Folder kerja bawaannya
induk folder workspace ini (<folder kerja>/<workspace>/tools -> <folder kerja>), sama dengan session_context.py."""
import os
import json

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(WORKSPACE, "Konfigurasi", "rule_sync.json")


def vault(registry=REGISTRY):
    """Path vault memori, atau None kalau belum diketahui (belum dipasang dan AGENT_VAULT kosong)."""
    if os.environ.get("AGENT_VAULT"):
        return os.environ["AGENT_VAULT"]
    try:
        with open(registry, encoding="utf-8") as f:
            reg = json.load(f)
    except (OSError, ValueError):
        return None
    if reg.get("vault"):
        return reg["vault"]
    cadangan = (reg.get("backup") or {}).get("dir")
    return os.path.dirname(cadangan.rstrip("/\\")) if cadangan else None


def folder_kerja():
    """Folder induk semua proyek: induk folder workspace."""
    return os.path.dirname(WORKSPACE)
