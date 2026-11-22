---
name: webapp-audit
description: >-
  Audits a built web app on three fronts and writes a ranked findings report. UI: a route
  sweep at several widths and themes that measures horizontal overflow, small touch targets,
  axe-core accessibility violations, console errors, failed requests and banned words.
  Integration: every saving control traced to its request, endpoint and table, then checked
  after reload, with the backend down, and across roles. Product fit: every promised feature
  traced to the original business idea, to the other features, and to the code that delivers
  it. Use when asked to audit, QA or check an app's screens, integration or features ("audit
  tampilan", "audit integrasi", "audit fitur", "kesesuaian fitur dengan ide bisnis", "relevansi
  antarfitur", "celah logika", "cek semua halaman", "E2E", "SIT", "uji integrasi"), before a
  release or demo, or after a large UI change. Do NOT use for a security audit, or to validate
  an idea that isn't built yet. Builds on the webapp-testing skill.
---

# Web App Audit: UI, Integration and Product Fit

Measure the running app instead of eyeballing it. This skill is a procedure plus one sweep script, on top of `webapp-testing` (Playwright on the installed Edge).

## Setup

- `<py>` is `<workspace>\tools\playwright-venv\Scripts\python.exe`, where `<workspace>` is the agent workspace folder named in the work-folder protocol. Set the venv up once with the command at the top of `tools\requirements\playwright-venv.txt`. These paths contain a space, so quote them. In PowerShell, start the command with `&`: `& "<py>" "<script>" ...`.
- Sweep script: `<workspace>\skills\webapp-audit\scripts\sweep_routes.py`. Run it with `--help` first. It exits 1 when it finds anything, so a non-zero exit is a normal result.
- Self-test: `<workspace>\skills\webapp-audit\scripts\test_sweep_routes.py`. It serves the sample pages in `scripts/fixtures/` itself (one with planted defects, one clean), so it needs no server.
- axe-core goes at `<workspace>\tools\axe-core\axe.min.js`, and the sweep loads it. It is not part of the kit: put the `axe.min.js` of the npm package `axe-core` (MPL-2.0) there before the first sweep.
- Servers: start them with `<workspace>\skills\webapp-testing\scripts\with_server.py` on free ports, so they stop when the audit ends. An audit that saves data needs a disposable test database, never a shared dev database.
- Work in a scratch folder. Audit output never goes into the project repo. Edge's temporary profile goes to `<workspace>\tools\playwright-venv\tmp`, so that folder changes on every run and the user profile stays clean.

## Before You Start

1. Read the project's `DESIGN.md` and its vault page if it has one. Their rules become checks: banned words, minimum target size, tokens only, status shown as icon + text + color, and known traps.
2. Write `routes.txt` from the router config, one path per line. Include detail routes with a real id, and every role's portal.
3. Pick the lane for each check. The lane names come from the `integration-e2e-testing` skill in shinpr/claude-code-workflows (MIT).

| Lane | Here it means |
|---|---|
| `integration` | In-process tests, such as the backend's own API suite. Run it first and don't repeat it in the browser |
| `fixture-e2e` | Real UI in a real browser with deterministic data, including the backend-down sweep |
| `service-integration-e2e` | Real UI, real API and a real test database, for anything that must persist |

## Part 1: UI

1. Sweep every route at 360 and 1360 px, light and dark:
   ```
   <py> sweep_routes.py --base-url http://localhost:5180 --routes routes.txt --forbid-text "error,server,API" --out audit-ui
   ```
   - `--login login.py`: a file with `login(page, base_url)`, run once per theme. Read test credentials from environment variables, never from the file.
   - `--spa`: move between routes with `history.pushState` + `popstate`, for apps whose store empties on reload.
   - `--init-script file.js`: runs before every page load. `window.__auditTheme` holds `light` or `dark`, for apps that keep the theme in storage instead of following `prefers-color-scheme`.
   - `--screenshots`: a full-page PNG per view in `<out>/shots`. Open only the ones the report points at.
   - Prefer `--routes <file>` over `--route`: Git Bash rewrites arguments that start with `/` into Windows paths (the script refuses those). If you must pass `--route` there, prefix the command with `MSYS_NO_PATHCONV=1`.
2. Read `<out>/report.json`. Each view (route × width × theme) lists:
   - page-level overflow and the elements sticking out
   - touch targets below `--min-target` (default 44 px, inline text links exempt)
   - axe violations (WCAG 2.0, 2.1 and 2.2, A and AA) and contrast cases axe could not decide
   - console and page errors, failed requests, and HTTP ≥ 400 responses
   - banned words with their context, and the first 200 characters of visible text
3. Check by hand what the script can't:
   - DESIGN.md rules that need judgment: tokens, hierarchy, vocabulary, status as icon + text + color.
   - If the Design Kit is installed, its rulebooks in `<workspace>/tools/design-kit/craft/`: `accessibility-baseline`, `state-coverage` (the empty, loading, error and offline state of each screen), `laws-of-ux`, `ui-mechanics`.
   - Keyboard: tab through one form per screen type. Focus must stay visible and move in a sensible order.
   - Contrast that axe left undecided, such as text over images or gradients.
4. A clean axe result is not a pass. axe only catches what a machine can measure.

## Part 2: Integration

1. **Action matrix.** Write one row per control that saves or changes something: screen, control, request (method and path), backend handler, tables touched, and the roles that should see the change. Build it from the frontend API client, the backend routes and `SCHEMA.md`, then confirm every row with a recorded request. A control that sends no request is a finding: the screen promises a save that only changes local state.
2. **Persists after reload** (`service-integration-e2e`). For each row: act, wait for the response, require 2xx, reload, and confirm the value is still there. Confirm it in the test database too when you can, with a read-only query.
3. **Backend down** (`fixture-e2e`). Sweep again with the API cut off, so no server has to stop: `--block-url "<pattern>" --out audit-offline --screenshots`. Build the pattern from the app's real API address, read from its API client or env (for example `VITE_API_URL`): `"http://localhost:8020/**"` for an API on its own origin, `"**/api/**"` only when the request paths really start with `/api/`. The sweep summary prints a line with the number of blocked requests. If that line is missing, the pattern matched nothing and the app was still online. For a sure cut, also point the frontend's API address at a closed port. Every screen must say honestly that it is offline or showing sample data. A screen that shows numbers as if they were live, or accepts a save as if it worked, is Critical.
4. **Cross-role flows.** Walk each flow end to end with every role in it, for example: the shop orders, the distributor accepts, the shop receives, the stock changes. After each step, sign in as the next role and check what changed.
5. **Route parity.** When two screens or endpoints change the same data, compare their validation and error handling. A difference that lets bad data through is a finding.

Snippets for steps 1 and 2:

```python
API = "http://localhost:8020"   # the app's API address from its client or env, or base_url + "/api"

# Which requests does one click send?
calls = []
page.on("request", lambda r: calls.append(f"{r.method} {r.url}") if r.url.startswith(API) else None)
page.get_by_role("button", name="Simpan").click()
page.wait_for_load_state("networkidle")
print(calls)

# Save, reload, still there
with page.expect_response(lambda r: r.url.startswith(API) and r.request.method != "GET") as info:
    page.get_by_role("button", name="Simpan").click()
assert info.value.ok, f"{info.value.status} {info.value.url}"
page.reload()
page.wait_for_load_state("networkidle")
assert page.get_by_text("Kopi susu 250 ml").is_visible()
```

## Part 3: Product Fit

Parts 1 and 2 show whether the screens and saves work. This part asks whether each feature serves the idea the product started from, whether the features serve each other, and whether each one holds up in its business logic. It reads documents and code, so it needs no server unless a finding has to be reproduced. Lenses and verification rules: `<workspace>\skills\webapp-audit\references\product-lenses.md`, from `apoorvjain25/production-audit` (MIT).

It is expensive. On one real app (2026-11-05, about 53,000 lines of frontend), each lens, and the fit matrix with the feature map, took 500k to 700k tokens and 20 to 27 minutes. Rechecking 18 findings took 450k tokens and 15 minutes. Tell the user the estimate, and agree on which lenses to run, before starting more than one. Build the feature map first and hand a map-only copy to each lens agent, so they don't explore from scratch. Lens agents can run at the same time.

1. **Pin two yardsticks.** The origin is the earliest document that states the idea, such as a proposal or pitch. The current promise is what users are told today, such as the landing page, an exhibition banner or a store listing. A PRD that changes along with the features can't be a yardstick, because it will always agree (check `git log --follow PRD.md`). If no origin document exists, ask the user to state the idea in a few sentences, and use that. Write down where origin and promise differ. That drift goes to the user as a decision without a level, and the user decides which one wins.
2. **Fit matrix.** Write one row per promised feature: the feature, the promise with its `file:line`, the origin problem it serves, and a verdict.

   | Verdict | Meaning |
   |---|---|
   | Core | The origin problem can't be solved without it |
   | Supporting | It serves a core feature, and you can name which one |
   | Detached | It serves no origin problem, and no other feature needs it |

   A detached feature isn't automatically wrong, so report it with what it costs to keep, and let the user decide.
3. **Feature map.** For each feature, trace in the code what it reads and who writes that, then what it writes and who reads that. Keep it as a table or a Mermaid diagram. Each of these is a finding: output nothing reads, input nothing writes, a feature that only ever runs on sample data, two features that decide the same thing by different rules, and a step in a chain that the user must bridge by hand.
4. **Claim-vs-code.** Run lens 3 over every promise, and keep a ledger: `C<n> | claim | source file:line | delivered / finding / unverifiable | code file:line`. A number needs the code or result file that produces it, from the variant that actually runs in production. When a promise document is older than the change that broke it, mark the finding as stale: the fix is to update the document.
5. **Other lenses.** Run the agreed lenses, each once, over the feature list, and keep a ledger: `lens | new findings`. If the last two lenses still add findings, say in the report that the audit did not converge. Don't loop.
6. **Stay blind, then compare.** Run steps 4 and 5 without reading earlier audit results or lists of known gaps, because an agent handed a known list tends to confirm it. Compare afterward, and mark each finding as new or already known.
7. **Verify.** Every finding names a `file:line` or a `URL + selector`, and says which guard you looked for. Drop what you can't pin. Where the platform has subagents, have a separate agent in a fresh context recheck Critical and High findings. Otherwise reread them yourself after the last lens.
8. **What code can't prove.** Whether real users need a feature, or would pay for it, is not a finding. List these as assumptions, each with a question to ask a real user and the answer that would change the plan.

This part leaves out security, which needs its own audit, and appearance and API wiring, which Parts 1 and 2 cover.

## Report

Write it in the user's language, worst first:

| Level | Meaning |
|---|---|
| Critical | Data lost, or false success: the screen says it saved but nothing persisted, or shows data while the backend is down without saying so. A cross-role flow is broken |
| High | An action fails with the backend up. axe `critical` or `serious`. Overflow at 360 px that hides content or controls. Banned words on screen. A promised feature that is absent or only staged |
| Medium | Touch targets below the minimum. axe `moderate`. Console errors with no visible effect. Undecided contrast that fails a manual check. A promise kept only in part, or a business rule with a workaround |
| Low | Cosmetic issues, axe `minor`, and a promise document that has gone stale |

Each finding gives its level, the route and screen, the width and theme, what happens, the evidence (report entry, request, or screenshot path) and the likely file. A Part 3 finding gives the promise's source and the code line instead of the width and theme. Part 3 also reports the fit matrix, the feature map, the drift between origin and promise, both ledgers with totals, and the assumptions. Mark what you inferred rather than observed. End with what the audit did not cover. Before reporting, check that no server or browser from the audit is still running.
