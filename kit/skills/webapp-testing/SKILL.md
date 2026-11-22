---
name: webapp-testing
description: Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browser logs.
license: Complete terms in LICENSE.txt
---

# Web Application Testing

> Adapted from anthropics/skills (commit `ca45fc4`, Apache-2.0) for this workspace: the installed Edge instead of a downloaded Chromium, one shared venv in the agent workspace, and a Windows-safe `with_server.py`. The changes and their reasons are in `SOURCE.md`. For a full UI and integration audit, use the `webapp-audit` skill, which builds on this one.

To test local web applications, write native Python Playwright scripts.

## Setup in This Workspace

- **Python:** `<workspace>\tools\playwright-venv\Scripts\python.exe` (Playwright 1.64.1), where `<workspace>` is the agent workspace folder named in the work-folder protocol, written `<py>` below. Run every script with it. The path contains a space, so quote it, and in PowerShell start the command with `&`. Reinstall from `tools\requirements\playwright-venv.txt`.
- **Browser:** the installed Microsoft Edge, `channel="msedge"`. Never run `playwright install`: it downloads browsers to `C:`.
- **Paths:** `scripts/` and `examples/` are in `<workspace>\skills\webapp-testing\`.
- **Where to run:** from a scratch folder, since outputs land in the current folder. Never from inside a project repo.
- **Servers are off by default:** start them through `with_server.py` so they stop when the command ends. If a run is cut off (tool timeout, kill), its cleanup does not run: check that the ports are free again with `Get-NetTCPConnection -LocalPort <port> -State Listen`. Right after a server stops, Windows can list its port as Listen with PID 0 for about a minute. That is not a live server, so use another port if you need one straight away.

**Helper Scripts Available**:
- `scripts/with_server.py` - Manages server lifecycle (supports multiple servers)

**Always run scripts with `--help` first** to see usage. DO NOT read the source until you try running the script first and find that a customized solution is abslutely necessary. These scripts can be very large and thus pollute your context window. They exist to be called directly as black-box scripts rather than ingested into your context window.

## Decision Tree: Choosing Your Approach

```
User task → Is it static HTML?
    ├─ Yes → Read HTML file directly to identify selectors
    │         ├─ Success → Write Playwright script using selectors
    │         └─ Fails/Incomplete → Treat as dynamic (below)
    │
    └─ No (dynamic webapp) → Is the server already running?
        ├─ No → Run: <py> scripts/with_server.py --help
        │        Then use the helper + write simplified Playwright script
        │
        └─ Yes → Reconnaissance-then-action:
            1. Navigate and wait for networkidle
            2. Take screenshot or inspect DOM
            3. Identify selectors from rendered state
            4. Execute actions with discovered selectors
```

## Example: Using with_server.py

To start a server, run `--help` first, then use the helper:

**Single server** (Vite with `--strictPort`, so it fails instead of silently moving to another port):
```bash
<py> scripts/with_server.py --server "npm run dev -- --port 5180 --strictPort" --port 5180 -- <py> your_automation.py
```

**Multiple servers (e.g., backend + frontend):** server commands run through the system shell (`cmd.exe` on Windows), so `cd x && ...` works.
```bash
<py> scripts/with_server.py \
  --server "cd backend && python server.py" --port 3000 \
  --server "cd frontend && npm run dev" --port 5173 \
  -- <py> your_automation.py
```

`with_server.py` refuses ports that are already in use (other sessions on this machine often hold 5173, 8000 and 8001), and `--log-dir <folder>` keeps each server's output for debugging.

To create an automation script, include only Playwright logic (servers are managed automatically):
```python
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

os.environ["TEMP"] = os.environ["TMP"] = str(Path(sys.prefix, "tmp"))  # Edge's temporary profile stays on D:
Path(os.environ["TEMP"]).mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True, timeout=90_000)  # installed Edge, first start can be slow
    page = browser.new_page()
    page.goto('http://localhost:5180') # Server already running and ready
    page.wait_for_load_state('networkidle') # CRITICAL: Wait for JS to execute
    # ... your automation logic
    browser.close()
```

## Reconnaissance-Then-Action Pattern

1. **Inspect rendered DOM**:
   ```python
   page.screenshot(path='inspect.png', full_page=True)
   content = page.content()
   page.locator('button').all()
   ```

2. **Identify selectors** from inspection results

3. **Execute actions** using discovered selectors

## Common Pitfall

❌ **Don't** inspect the DOM before waiting for `networkidle` on dynamic apps
✅ **Do** wait for `page.wait_for_load_state('networkidle')` before inspection

## Best Practices

- **Use bundled scripts as black boxes** - To accomplish a task, consider whether one of the scripts available in `scripts/` can help. These scripts handle common, complex workflows reliably without cluttering the context window. Use `--help` to see usage, then invoke directly. 
- Use `sync_playwright()` for synchronous scripts
- Always close the browser when done
- Use descriptive selectors: `text=`, `role=`, CSS selectors, or IDs
- Add appropriate waits: `page.wait_for_selector()` or `page.wait_for_timeout()`
- Accessibility: inject `<workspace>\tools\axe-core\axe.min.js` (the npm package `axe-core`, not part of the kit) with `page.add_script_tag(path=...)`, then `page.evaluate("axe.run()")`

## Reference Files

- **examples/** - Examples showing common patterns:
  - `element_discovery.py` - Discovering buttons, links, and inputs on a page
  - `static_html_automation.py` - Using file:// URLs for local HTML
  - `console_logging.py` - Capturing console logs during automation
