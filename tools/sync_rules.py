import os
import re
import sys
import json
import hashlib
import argparse

# Bagian bersama diapit penanda ini, di sumber maupun di setiap salinan. Yang di luar penanda
# (judul, batas berlaku khusus platform) milik masing-masing file dan tidak disentuh.
# Satu salinan boleh memuat beberapa bagian; tiap bagian dikenali dari namanya di penanda begin.
BEGIN = re.compile(r"<!-- sync:begin ([^>]*?) -->")
END = "<!-- sync:end -->"

def span(text, name=None):
    """Posisi bagian bersama bernama `name` (atau bagian pertama), beserta namanya."""
    m = next((m for m in BEGIN.finditer(text) if name is None or m.group(1) == name), None)
    e = text.find(END, m.end()) if m else -1
    return (m.start(), e + len(END), m.group(1)) if m and e >= 0 else None

def read(path):
    raw = open(path, "rb").read()
    return raw.decode("utf-8-sig").replace("\r\n", "\n"), ("\r\n" if b"\r\n" in raw else "\n")

STAMP = re.compile(r"<!-- translated-from: ([0-9a-f]{12}) -->\n?")

def fingerprint(t):
    """Sidik bagian sumber yang diterjemahkan: seluruh file, atau satu heading sampai heading setingkat berikutnya."""
    text, _ = read(t["source"])
    if t.get("section"):
        level = len(t["section"]) - len(t["section"].lstrip("#"))
        head = re.search(rf"(?m)^{re.escape(t['section'])}", text)
        if not head:
            raise ValueError(f"heading '{t['section']}' tidak ada di sumber")
        body_start = text.find("\n", head.start()) + 1
        nxt = re.search(rf"(?m)^#{{1,{level}}} ", text[body_start:])
        text = text[head.start():body_start + nxt.start()] if nxt else text[head.start():]
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(description="Salin bagian bersama aturan dari sumber ke semua salinannya, sesuai registry. "
                                            "Tanpa --check menulis; dengan --check hanya melapor. Keluar dengan kode 1 kalau ada salinan yang belum sama.")
    p.add_argument("--registry", default=os.path.join(os.path.dirname(here), "Konfigurasi", "rule_sync.json"))
    p.add_argument("--check", action="store_true", help="Hanya melapor, tidak mengubah file apa pun")
    p.add_argument("--stamp", action="append", default=[], metavar="CERMIN",
                   help="Setelah terjemahan diperbarui: cap cermin ini dengan sidik sumbernya sekarang (boleh diulang)")
    a = p.parse_args()

    reg = json.load(open(a.registry, encoding="utf-8"))
    problems = 0
    for s in reg["syncs"]:
        print(f"# {s['name']} (sumber: {s['source']})")
        src, _ = read(s["source"])
        sp = span(src)
        if not sp:
            print("  [GAGAL] penanda sync tidak ada di sumber")
            problems += 1
            continue
        shared, label = src[sp[0]:sp[1]], sp[2]
        for c in s["copies"]:
            path = c["path"]
            if c.get("pending"):
                print(f"  [TERTUNDA] {path}: {c['pending']}")
                problems += 1
                continue
            try:
                text, nl = read(path)
            except OSError as e:
                print(f"  [TIDAK TERJANGKAU] {path}: {e}")
                problems += 1
                continue
            cp = span(text, label)
            if not cp:
                print(f"  [TANPA PENANDA] {path}: bagian '{label}' tidak ada, tidak disentuh")
                problems += 1
            elif text[cp[0]:cp[1]] == shared:
                print(f"  [SAMA] {path}")
            elif a.check:
                print(f"  [BEDA] {path}")
                problems += 1
            else:
                with open(path, "w", encoding="utf-8", newline=nl) as f:
                    f.write(text[:cp[0]] + shared + text[cp[1]:])
                print(f"  [DIPERBARUI] {path}")

    # Terjemahan tidak bisa disalin mesin. Cermin membawa cap sidik bagian sumber saat terakhir diterjemahkan;
    # kalau sidik sumber sekarang berbeda, terjemahannya perlu diperiksa.
    stamp = {os.path.normcase(os.path.abspath(m)) for m in a.stamp}
    if reg.get("translations"):
        print("# Terjemahan (diperbarui manual oleh agent, lalu dicap dengan --stamp)")
    for t in reg.get("translations", []):
        note = f" ({t['note']})" if t.get("note") else ""
        try:
            fp = fingerprint(t)
            text, nl = read(t["mirror"])
        except (OSError, ValueError) as e:
            print(f"  [TIDAK TERJANGKAU] {t['mirror']}: {e}")
            problems += 1
            continue
        m = STAMP.search(text)
        if os.path.normcase(os.path.abspath(t["mirror"])) in stamp:
            body = STAMP.sub("", text).rstrip("\n") + "\n"
            with open(t["mirror"], "w", encoding="utf-8", newline=nl) as f:
                f.write(f"{body}\n<!-- translated-from: {fp} -->\n")
            print(f"  [DICAP] {t['mirror']}{note}")
        elif m and m.group(1) == fp:
            print(f"  [OK] {t['mirror']}{note}")
        else:
            print(f"  [PERIKSA] {t['mirror']}{note}: bagian sumbernya berubah sejak terakhir diterjemahkan")
            problems += 1
    sys.exit(1 if problems else 0)

if __name__ == "__main__":
    main()
