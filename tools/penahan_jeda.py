"""Hook UserPromptSubmit Claude Code (Q2 di log vault 078, dipasang 2026-11-22): memperingatkan, atau menahan sekali,
saat pengguna kembali ke sesi besar setelah jeda yang lebih lama dari umur cache. Pesan pertama sesudah jeda seperti
itu menulis ulang seluruh konteks ke cache. Pada 2026-11-13 sampai 2026-11-22, kejadian ini memegang 55% tulis cache
sesi utama (log 078). Fitur bawaan idleCompaction mestinya mencegahnya, tetapi hanya terlihat jalan sekali dari 73 jeda
yang memenuhi syarat (log 079).

  python tools/penahan_jeda.py [--ambang 200000] [--tahan] [--state <berkas.json>]

Bawaannya hanya memperingatkan lewat systemMessage dan additionalContext. Dengan --tahan, pesan pertama sesudah jeda
ditahan sekali (decision block), lalu pesan berikutnya di jeda yang sama lolos. Mode tahan baru dipakai sesudah
terbukti aplikasi desktop tidak menghapus pesan yang ditahan. Pesan berisi `#uji-tahan` selalu ditahan, untuk menguji
perilaku itu di aplikasi. Pesan berisi `#lanjut` selalu lolos tanpa peringatan. Galat apa pun berarti lolos tanpa
keluaran, supaya hook ini tidak pernah menghalangi kerja."""
import argparse
import datetime as dt
import json
import os
import sys

BLOK = (1 << 21, 1 << 23, 1 << 25)   # ekor transkrip yang dibaca bertahap: 2, 8, lalu 32 MB


def waktu(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def keadaan(transcript):
    """(waktu panggilan terakhir, ukuran konteks sesudahnya, umur cache dalam detik) dari ekor transkrip, atau None.
    Ringkasan (compact_boundary) sesudah panggilan terakhir berarti konteksnya sudah kecil, jadi juga None."""
    besar = os.path.getsize(transcript)
    for n in BLOK:
        with open(transcript, "rb") as f:
            f.seek(max(0, besar - n))
            lines = f.read().decode("utf-8", "replace").splitlines()
        if besar > n:
            lines = lines[1:]   # baris pertama potongan bisa terpotong
        terakhir, ttl = None, None
        for line in reversed(lines):
            if '"compact_boundary"' in line and terakhir is None:
                try:
                    if json.loads(line).get("subtype") == "compact_boundary":
                        return None
                except ValueError:
                    pass
            if '"usage"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            u = (e.get("message") or {}).get("usage")
            if e.get("type") != "assistant" or e.get("isSidechain") or not u or not e.get("timestamp"):
                continue
            if terakhir is None:
                konteks = sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens",
                                                      "cache_read_input_tokens", "output_tokens"))
                terakhir = (waktu(e["timestamp"]), konteks)
            det = u.get("cache_creation") or {}
            if det.get("ephemeral_1h_input_tokens"):
                ttl = 3600
            elif det.get("ephemeral_5m_input_tokens"):
                ttl = 300
            if ttl:
                break
        if terakhir:
            return terakhir[0], terakhir[1], ttl or 3600   # tanpa tulisan yang terbaca: bawaan langganan 1 jam
        if besar <= n:
            break
    return None


def lama(detik):
    jam, menit = divmod(int(detik // 60), 60)
    return f"{jam} jam {menit} menit" if jam else f"{menit} menit"


def putuskan(payload, ambang, tahan, state_path, sekarang=None):
    """Keluaran JSON hook untuk satu payload, atau None kalau lolos tanpa keluaran."""
    prompt = payload.get("prompt") or ""
    if "#lanjut" in prompt:
        return None
    if "#uji-tahan" in prompt:
        return {"decision": "block", "reason": "Uji penahan jeda: pesan ini sengaja ditahan untuk melihat apakah "
                "aplikasi menyimpan teksnya. Kirim ulang tanpa #uji-tahan untuk lanjut."}
    path = payload.get("transcript_path")
    if not path or not os.path.isfile(path):
        return None
    k = keadaan(path)
    if not k:
        return None
    t, konteks, ttl = k
    jeda = ((sekarang or dt.datetime.now(dt.timezone.utc)) - t).total_seconds()
    if jeda <= ttl or konteks < ambang:
        return None
    inti = (f"Sesi ini sekitar {konteks // 1000} ribu token dan sudah {lama(jeda)} sejak panggilan terakhir, lebih lama "
            f"dari umur cache ({ttl // 60} menit). Pesan berikutnya menulis ulang seluruh konteks itu ke cache.")
    saran = "Lebih hemat mulai sesi baru dari bagian `## Sekarang` halaman proyek dan log terakhir (aturan inti 2)."
    if tahan:
        sesi = str(payload.get("session_id") or path)
        try:
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, ValueError):
            state = {}
        if state.get(sesi) == t.isoformat():
            return None   # sudah ditahan sekali untuk jeda ini: kiriman ulang lolos
        batas = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).isoformat()
        state = {s: v for s, v in state.items() if v >= batas}
        state[sesi] = t.isoformat()
        os.makedirs(os.path.dirname(os.path.abspath(state_path)), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f)
        return {"decision": "block", "reason": f"Ditahan sekali. {inti} {saran} Kirim ulang pesan yang sama untuk "
                "tetap lanjut di sini, atau tambahkan #lanjut."}
    return {"systemMessage": f"{inti} {saran}",
            "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext":
                                   f"[Penahan jeda] {inti} Sebutkan sekali, dalam satu kalimat di awal jawaban, bahwa sesi "
                                   "baru dari `## Sekarang` dan log terakhir lebih hemat, lalu kerjakan permintaannya seperti biasa."}}


def main():
    p = argparse.ArgumentParser(description="Hook UserPromptSubmit: peringatan atau penahanan saat kembali ke sesi besar setelah cache kedaluwarsa.")
    p.add_argument("--ambang", type=int, default=200_000, help="Ukuran konteks minimal (token) yang diperingatkan")
    p.add_argument("--tahan", action="store_true", help="Tahan pesan pertama sesudah jeda sekali, bukan hanya memperingatkan")
    p.add_argument("--state", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                   "Riwayat Perckapan", "penahan-jeda.json"))
    a = p.parse_args()
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        out = putuskan(payload, a.ambang, a.tahan, a.state) if isinstance(payload, dict) else None
    except Exception:
        return
    if out:
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
