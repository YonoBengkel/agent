"""Sapu rute aplikasi web yang sedang jalan di beberapa lebar layar dan tema, lalu laporkan masalah tampilannya.

Per tampilan (rute x lebar x tema): luberan horizontal halaman dan elemen yang menyembul, target sentuh di bawah ukuran
minimum, pelanggaran axe-core (WCAG 2.0, 2.1, dan 2.2 tingkat A dan AA), kontras yang tidak bisa diputuskan axe, galat
konsol dan halaman, request gagal, respons HTTP >= 400, dan kata terlarang di layar. Hasilnya <out>/report.json plus
ringkasan di layar. Kode keluar 1 kalau ada temuan. Bagian dari skill webapp-audit.

Jalankan dengan venv Playwright:
  "<workspace>/tools/playwright-venv/Scripts/python.exe" sweep_routes.py --base-url http://localhost:5180 --routes routes.txt
"""
import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

AXE = Path(__file__).resolve().parents[3] / "tools" / "axe-core" / "axe.min.js"
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
IGNORED = ("net::ERR_INTERNET_DISCONNECTED", "net::ERR_ABORTED")   # diputus --block-url, atau dibatalkan karena pindah halaman

# Transisi dimatikan dan animasi diselesaikan dulu, karena warna yang sedang bertransisi salah terbaca
SETTLE = r"""() => {
  if (!document.getElementById('__audit_diam')) {
    const s = document.createElement('style');
    s.id = '__audit_diam';
    s.textContent = '*,*::before,*::after{transition:none!important;caret-color:transparent!important}';
    document.head.appendChild(s);
  }
  for (const a of document.getAnimations()) { try { a.finish(); } catch (e) { /* animasi tanpa akhir */ } }
  return document.fonts.ready.then(() => true);
}"""

MEASURE = r"""([minTarget, banned]) => {
  const root = document.documentElement, vw = root.clientWidth;
  const name = el => {
    let s = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '');
    const cls = typeof el.className === 'string' ? el.className.trim().split(/\s+/).filter(Boolean).slice(0, 2) : [];
    if (cls.length) s += '.' + cls.join('.');
    const label = (el.getAttribute('aria-label') || el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    return label ? `${s} "${label}"` : s;
  };
  const shown = el => {
    const r = el.getBoundingClientRect(), st = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && st.visibility !== 'hidden' && st.opacity !== '0';
  };
  // Elemen di dalam wadah overflow-x atau position:fixed tidak membuat halaman bergulir ke samping
  const contained = el => {
    for (let a = el; a && a !== document.body; a = a.parentElement) {
      const st = getComputedStyle(a);
      if (st.position === 'fixed' || (a !== el && st.overflowX !== 'visible')) return true;
    }
    return false;
  };
  const overflow = root.scrollWidth - vw, sticking = [];
  if (overflow > 1) {
    for (const el of document.body.querySelectorAll('*')) {
      if (sticking.length >= 8) break;
      if (sticking.some(o => o.contains(el))) continue;
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.right > vw + 1 && !contained(el)) sticking.push(el);
    }
  }
  const small = [];
  let smallCount = 0;
  for (const el of document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=checkbox],[role=radio],[role=switch],[role=tab],[role=menuitem],[tabindex]:not([tabindex="-1"])')) {
    if (!shown(el)) continue;
    if (getComputedStyle(el).display === 'inline' && el.closest('p,li,td,dd,blockquote')) continue;   // tautan di dalam kalimat: pengecualian WCAG 2.5.8
    const r = el.getBoundingClientRect();
    if (r.width >= minTarget && r.height >= minTarget) continue;
    const lab = el.closest('label') || (el.id ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`) : null);
    if (lab) {   // kotak centang kecil di dalam label yang cukup besar: yang disentuh labelnya
      const lr = lab.getBoundingClientRect();
      if (lr.width >= minTarget && lr.height >= minTarget) continue;
    }
    smallCount++;
    if (small.length < 8) small.push(`${name(el)} ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  const text = (document.body.innerText || '').replace(/\s+/g, ' ').trim(), words = [];
  for (const w of banned) {
    const esc = w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const m = new RegExp(`(^|[^\\p{L}\\p{N}])(${esc})(?=$|[^\\p{L}\\p{N}])`, 'iu').exec(text);
    if (m) {
      const i = m.index + m[1].length;
      words.push(`${w}: "${text.slice(Math.max(0, i - 30), i + w.length + 30)}"`);
    }
  }
  return { overflow: Math.max(0, overflow), sticking: sticking.map(name), smallCount, small, words, text: text.slice(0, 200) };
}"""

AXE_RUN = """async (tags) => {
  const r = await axe.run(document, { runOnly: { type: 'tag', values: tags }, resultTypes: ['violations', 'incomplete'] });
  const brief = v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length,
                        targets: v.nodes.slice(0, 3).map(n => [].concat(n.target).join(' ')) });
  return { violations: r.violations.map(brief), undecided: r.incomplete.filter(v => v.id === 'color-contrast').map(brief) };
}"""


class Watch:
    """Galat dan request per kunjungan rute, plus hitungan request yang masih berjalan."""

    def __init__(self, page):
        self.inflight = 0
        self.reset()
        page.on("request", self._start)
        page.on("requestfinished", self._end)
        page.on("requestfailed", self._failed)
        page.on("response", self._response)
        page.on("console", self._console)
        page.on("pageerror", lambda e: self.page_errors.append(str(e)[:300]))

    def reset(self):
        self.console, self.page_errors, self.failed, self.http, self.blocked = [], [], [], [], []

    def _start(self, request):
        self.inflight += 1

    def _end(self, request):
        self.inflight -= 1

    def _failed(self, request):
        self.inflight -= 1
        if not any(code in (request.failure or "") for code in IGNORED):
            self.failed.append(f"{request.method} {request.url} {request.failure}")

    def _response(self, response):
        if response.status >= 400:
            self.http.append(f"{response.status} {response.request.method} {response.url}")

    def _console(self, message):
        if message.type == "error" and not any(code in message.text for code in IGNORED):
            self.console.append(message.text[:300])

    def block(self, route):
        self.blocked.append(route.request.url)
        route.abort("internetdisconnected")

    def settle(self, page, idle_ms=500, limit_ms=10_000):
        """Tunggu sampai tidak ada request berjalan selama idle_ms. networkidle Playwright tidak berlaku sesudah pushState."""
        waited = idle = 0
        while waited < limit_ms and idle < idle_ms:
            page.wait_for_timeout(100)
            waited += 100
            idle = idle + 100 if self.inflight <= 0 else 0


def slug(route):
    return re.sub(r"[^A-Za-z0-9]+", "-", route).strip("-") or "akar"


def view(page, watch, base_url, route, width, theme, spa, axe, min_target, forbid, shots):
    """Buka satu rute lalu ukur. Rute yang gagal dibuka tetap dicatat supaya sapuan jalan terus."""
    entry = {"route": route, "width": width, "theme": theme}
    watch.reset()
    try:
        if spa and page.url.startswith(base_url):   # pindah tanpa muat ulang, supaya store aplikasi tidak kosong lagi
            page.evaluate("r => { history.pushState(null, '', r); dispatchEvent(new PopStateEvent('popstate')); }", route)
        else:
            response = page.goto(base_url + route)
            entry["status"] = response.status if response else None
        watch.settle(page)
        page.evaluate(SETTLE)
        m = page.evaluate(MEASURE, [min_target, list(forbid)])
        if not page.evaluate("typeof axe !== 'undefined'"):
            page.add_script_tag(path=str(axe))
        a = page.evaluate(AXE_RUN, AXE_TAGS)
        entry.update(overflow_px=m["overflow"], sticking_out=m["sticking"], small_targets=m["smallCount"],
                     small_target_samples=m["small"], axe_violations=a["violations"], contrast_undecided=a["undecided"],
                     banned_words=m["words"], text_sample=m["text"])
        if shots:
            entry["screenshot"] = str(shots / f"{slug(route)}-{width}-{theme}.png")
            page.screenshot(path=entry["screenshot"], full_page=True)
    except Exception as e:
        entry["error"] = str(e).strip().splitlines()[0][:300]
    entry.update(console_errors=watch.console, page_errors=watch.page_errors, failed_requests=watch.failed,
                 http_errors=watch.http, blocked_requests=len(watch.blocked))
    return entry


def sweep(base_url, routes, widths=(360, 1360), themes=("light", "dark"), out=Path("audit-ui"), axe=AXE, min_target=44,
          forbid=(), login=None, init_script=None, spa=False, block_url=None, screenshots=False):
    """Satu entri per tampilan. login: fungsi login(page, base_url), dijalankan sekali per tema."""
    base_url = base_url.rstrip("/")
    tmp = Path(sys.prefix, "tmp")
    tmp.mkdir(exist_ok=True)
    os.environ["TEMP"] = os.environ["TMP"] = str(tmp)   # profil Edge sementara tetap di folder workspace
    if screenshots:
        (out / "shots").mkdir(parents=True, exist_ok=True)
    entries = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, timeout=90_000)
        try:
            for theme in themes:
                ctx = browser.new_context(color_scheme=theme, reduced_motion="reduce", bypass_csp=True)
                ctx.add_init_script(f"window.__auditTheme = {json.dumps(theme)};")
                if init_script:
                    ctx.add_init_script(path=str(init_script))
                page = ctx.new_page()
                watch = Watch(page)
                if block_url:
                    page.route(block_url, watch.block)
                if login:
                    login(page, base_url)
                for width in widths:
                    page.set_viewport_size({"width": width, "height": 900})
                    for route in routes:
                        entries.append(view(page, watch, base_url, route, width, theme, spa, axe, min_target, forbid,
                                            out / "shots" if screenshots else None))
                ctx.close()
        finally:
            browser.close()
    return entries


def summarize(entries):
    """Cetak ringkasan per jenis temuan. Kembalikan jumlah tampilan yang punya temuan."""
    def count(e, *keys):
        return sum(len(e.get(k, [])) for k in keys)
    checks = [
        ("gagal dibuka", lambda e: e.get("error", "")),
        ("luberan horizontal", lambda e: e.get("overflow_px", 0) > 1 and f"+{e['overflow_px']}px"),
        ("target sentuh di bawah minimum", lambda e: e.get("small_targets") and f"{e['small_targets']} elemen"),
        ("pelanggaran axe", lambda e: ", ".join(f"{v['id']} {v['impact']}" for v in e.get("axe_violations", []))),
        ("galat konsol atau halaman", lambda e: count(e, "console_errors", "page_errors") and f"{count(e, 'console_errors', 'page_errors')} galat"),
        ("request gagal atau HTTP >= 400", lambda e: count(e, "failed_requests", "http_errors") and f"{count(e, 'failed_requests', 'http_errors')} request"),
        ("kata terlarang", lambda e: ", ".join(w.split(":")[0] for w in e.get("banned_words", []))),
    ]
    print(f"Disapu {len(entries)} tampilan dari {len({e['route'] for e in entries})} rute.")
    bad = set()
    for label, test in checks:
        hits = [(f"{e['route']} {e['width']}px {e['theme']}", test(e)) for e in entries]
        hits = [h for h in hits if h[1]]
        if hits:
            bad.update(h[0] for h in hits)
            print(f"- {label}: {len(hits)} tampilan. Contoh: " + " | ".join(f"{v} ({d})" for v, d in hits[:3]))
    undecided = sum(v["nodes"] for e in entries for v in e.get("contrast_undecided", []))
    if undecided:
        print(f"- kontras yang tidak bisa diputuskan axe: {undecided} elemen, cek manual")
    blocked = sum(e.get("blocked_requests", 0) for e in entries)
    if blocked:
        print(f"- request yang sengaja diputus (--block-url): {blocked}")
    if not bad:
        print("Tidak ada temuan.")
    return len(bad)


def main(argv=None):
    sys.stdout.reconfigure(errors="replace")   # konsol Windows yang dipipe memakai cp1252
    ap = argparse.ArgumentParser(description="Sapu rute aplikasi web yang sedang jalan dan laporkan masalah tampilannya (skill webapp-audit). Kode keluar 1 berarti ada temuan.")
    ap.add_argument("--base-url", required=True, help="Alamat aplikasi, mis. http://localhost:5180")
    ap.add_argument("--routes", type=Path, help="Berkas berisi satu path per baris. Baris kosong dan baris berawalan # diabaikan")
    ap.add_argument("--route", action="append", default=[], help="Satu path rute, boleh diulang")
    ap.add_argument("--widths", default="360,1360", help="Lebar layar dalam px, dipisah koma (bawaan 360,1360)")
    ap.add_argument("--themes", default="light,dark", help="light, dark, atau keduanya dipisah koma (bawaan light,dark)")
    ap.add_argument("--min-target", type=int, default=44, help="Ukuran target sentuh minimum dalam px (bawaan 44)")
    ap.add_argument("--forbid-text", default="", help="Kata yang tidak boleh tampil di layar, dipisah koma, mis. dari DESIGN.md proyek")
    ap.add_argument("--login", type=Path, help="Berkas Python berisi login(page, base_url), dijalankan sekali per tema")
    ap.add_argument("--init-script", type=Path, help="Berkas JS yang jalan sebelum setiap halaman dimuat. window.__auditTheme berisi light atau dark")
    ap.add_argument("--spa", action="store_true", help="Pindah rute lewat history.pushState + popstate, untuk aplikasi yang store-nya kosong lagi saat dimuat ulang")
    ap.add_argument("--block-url", help="Pola URL API yang diputus, untuk melihat layar saat backend mati. Turunkan dari alamat API aplikasinya, mis. 'http://localhost:8020/**', atau '**/api/**' bila jalurnya memang diawali /api/")
    ap.add_argument("--screenshots", action="store_true", help="Simpan tangkapan layar penuh per tampilan di <out>/shots")
    ap.add_argument("--out", type=Path, default=Path("audit-ui"), help="Folder hasil (bawaan audit-ui di folder kerja)")
    a = ap.parse_args(argv)
    routes = [r.strip() for r in a.route if r.strip()]
    if a.routes:
        lines = a.routes.read_text(encoding="utf-8-sig").splitlines()   # -sig: berkas dari PowerShell sering ber-BOM
        routes += [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    if not routes:
        ap.error("butuh --routes atau --route")
    odd = [r for r in routes if re.match(r"^/?[A-Za-z]:[\\/]", r)]
    if odd:   # Git Bash mengubah argumen berawalan / menjadi path Windows, mis. /cacat.html jadi C:/Program Files/Git/cacat.html
        ap.error(f"rute {odd[0]} terlihat seperti path Windows. Pakai --routes <berkas>, atau jalankan dengan MSYS_NO_PATHCONV=1 di Git Bash")
    routes = [r if r.startswith("/") else "/" + r for r in routes]
    themes = [t.strip() for t in a.themes.split(",") if t.strip()]
    if not themes or any(t not in ("light", "dark") for t in themes):
        ap.error("--themes hanya boleh light dan/atau dark")
    login = None
    if a.login:
        spec = importlib.util.spec_from_file_location("audit_login", a.login)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        login = module.login
    entries = sweep(a.base_url, routes, [int(w) for w in a.widths.split(",")], themes, a.out, min_target=a.min_target,
                    forbid=[w.strip() for w in a.forbid_text.split(",") if w.strip()], login=login,
                    init_script=a.init_script, spa=a.spa, block_url=a.block_url, screenshots=a.screenshots)
    a.out.mkdir(parents=True, exist_ok=True)
    report = a.out / "report.json"
    report.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    found = summarize(entries)
    print(f"Laporan lengkap: {report}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
