# Product Audit Lenses

Nine lenses and the verification rules for Part 3 of `webapp-audit`. Each pass takes ONE lens and sweeps the whole feature list through it. The example row under each lens is illustrative, not a template: your rows must point at real locations in the audited product.

Adapted from `SKILL.md`, `references/audit-angles.md` and `references/finding-taxonomy.md` in [apoorvjain25/production-audit](https://github.com/apoorvjain25/production-audit), commit `5acb1ed` (MIT, notice at the end). The lens text is unchanged and keeps upstream's numbers. Changed by us on 2026-11-05: kept 9 of the 24 lenses, and left out the security lenses, fix mode, looping until two passes come back empty, "do not stop for confirmation", and the expectation of hundreds of findings. Report levels come from `webapp-audit`'s own table. Lens 1 calls itself the best first pass, but here the feature map in Part 3 already builds that mental map, so start with lens 3.

Lens 3 passed a blind pilot on a real app on 2026-11-05, and lenses 4, 6, 7 and 13 ran on it the same day. Lenses 1, 8, 9 and 24 have not been tried here yet.

## 3. Claim-vs-code

Take every specific promise in the README / landing page / docs / FAQ / security page (numbers, guarantees, feature names) and find the code that delivers it. "AES-256 encrypted", "undo within 5 minutes", "we never train on your data", "sub-second search": each is either verified or it's a finding. Fake/staged demo data presented as real counts too.

> `[HIGH] [CONTENT] landing/index.html §features - "unlimited version history" but versions are pruned after 30 days in jobs/prune-versions.ts:12 - fix the claim or the cron`

## 1. Subsystem sweep

Walk one subsystem at a time (auth, billing, search, notifications, import/export, admin, ...) end to end. Read the entry points, trace to storage and back. Best first pass; it builds the mental map the other lenses need.

> `[CRITICAL] [BACKEND] src/billing/invoice.ts:88 - invoice total computed from client-supplied line-item prices, not server-side prices - recompute from the DB before charging`

## 4. Data-shape

Re-run key flows mentally (or actually) at the extremes: zero items, one item, partially-filled records, unicode/emoji/RTL, very long strings, 100k rows. Pagination without limits, unbounded `IN` clauses, UI that assumes at least one element, reducers that crash on empty.

> `[MEDIUM] [FRONTEND] src/components/Chart.tsx:54 - reduce() over data.points with no initial value; crashes on an empty dataset - add an initial value and an empty state`

## 6. Lifecycle

Follow one actor through time: signup → onboarding → daily use → plan change → member leaves → account deletion. Offboarding is where data-retention promises die: does departed-user data actually get purged? Do revoked integrations stop syncing? Does deletion cascade or strand orphans?

> `[HIGH] [DATA] src/jobs/delete-account.ts:40 - deletion removes the user row but leaves their uploads in object storage forever - cascade the delete to S3`

## 7. Write-path integrity

Every write with an external effect (email, webhook, payment, third-party API): is it idempotent under retry? What happens if the process dies between the two writes? Look specifically for non-atomic sibling writes (record persisted before its permission row, flag set before the index is built): these create windows where data is live but unprotected, and they are invisible to tests.

> `[HIGH] [DATA] src/import/processor.ts:142 - document row committed before its permission row, non-atomically; content is live and unprotected in the gap - one transaction, permission first`

## 8. Failure-mode

For each dependency (database, queue, third-party API, LLM provider): what does the product do when it's down, slow, or returns garbage? Missing timeouts, retries without backoff, errors swallowed into silent no-ops, dead-letter handling, malformed-response parsing.

> `[HIGH] [RELIABILITY] src/lib/llm.ts:27 - provider call has no timeout; one hung request pins a worker forever - add a timeout and abort handling`

## 9. Dead-and-stale

Hunt code and content that lies about the present: docs for removed features, screenshots of old UI, TODO/FIXME shipping in prod paths, feature flags permanently off with live marketing, exported symbols nothing imports, migrations that drifted from the schema.

> `[MEDIUM] [DOCS] docs/integrations.md:9 - documents a Slack integration removed three releases ago - delete the section`

## 13. Content & copy

Read every page as a first-time, non-technical user. Typos and grammar; placeholder text (lorem ipsum, "test", TODO) shipped to prod; jargon where plain language belongs; raw technical artifacts rendered as content: stack traces, error codes, JSON blobs, `NaN`/`undefined`/`null` on screen. Terminology consistent across pages, and every number, stat, and price identical everywhere it appears: landing vs pricing vs docs vs in-app.

> `[LOW] [CONTENT] pricing.html §faq - "recieve" twice, and the failed-payment state renders raw "Error: ECONNREFUSED" - fix the copy, map errors to human text`

## 24. Concurrency & races

Two of anything at once: a user double-clicking submit; the same form open in two tabs; two workers grabbing the same job; a webhook delivered twice. Check-then-act gaps with no unique constraint as the last line of defense; concurrent edits where the last write silently wins; counters updated read-modify-write instead of atomically; job locks that don't expire when a worker dies.

> `[HIGH] [DATA] src/api/redeem/route.ts:30 - coupon checked then decremented in two steps; parallel requests over-redeem - atomic decrement guarded by a constraint`

## Verifying a candidate finding

- Open the actual file/page. Confirm the issue exists at that exact location, today.
- Verify it against the real code: is there a guard upstream that makes it safe? Is the dead code actually unreachable? Is the "missing check" genuinely enforced elsewhere? Where a test would settle it, run that test.
- If you cannot pin it to a `file:line` or a `URL + selector`, drop it.
- Verify, do not argue it away; the goal is an honest verdict, not a shorter list. Plausible-but-wrong findings destroy trust in the whole list; so do real findings dismissed too quickly.
- Anything you would have to hedge to state is not a finding yet. Go verify until the hedge disappears, or drop it.
- Torn between two severities? Take the lower one and make the row's evidence undeniable. An inflated list reads as alarmism and gets ignored; an understated row with perfect evidence still gets fixed.

## License of the upstream text

MIT License

Copyright (c) 2026 Apoorv Jain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
