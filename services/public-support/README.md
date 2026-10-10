# Public product assistant (TEST only)

Issue #40 removes the ~16–18s gateway call to reselect a known FAQ. The landing
answers familiar questions locally, including accent-free Vietnamese and
explicit synonyms. It uses 14 reviewed public topics in `public-facts.json`;
`reviewed_in` records the source files used to check each claim. Public source
pages at `/support/knowledge#<id>` provide the actual evidence shown to AI.
No business data, database connection, session secret or MES imports exist here.

## Shared contract for the issue #39 app widget

`GET /support/assistant.js` exposes `window.MESFlowSupport`:

- `topics`: public facts, no review metadata or secrets.
- `match(question)`: local `{mode, answer, topic_ids?, sources, ai?, public_question?}`.
  `faq` is immediate; `clarify`/`decline` never offer AI. Unknown words, names,
  identifiers, numbers, contacts, private-data and injection requests fail closed.
- `faq(id)`: selected public topic, immediate.
- `deeper(ai, signal)`: optional fetch, `credentials: omit`, no raw question,
  page state, history or headers. Call ONLY after the user sees `public_question`
  and explicitly agrees. Render `answer` with textContent, source links from
  the local KB, and label `gateway` vs `gateway_cached` vs `faq` honestly.

`POST /support/chat` retains `{topics:["excel"]}` compatibility: returns
`{mode:"faq",topic_ids,answer,sources,reason}` instantly, with **zero AI calls**.
Legacy clients can continue rendering their local fact text from `topic_ids`.
New AI input is exactly `{topics:["qr","productivity"],intent:"guide",consent:true}`.
Two or three unique approved IDs; intent is `guide`, `compare` or `diagnose`.
Login questions cannot enter the AI path. Additional fields are rejected.
The server reconstructs the same canonical public question from enums and KB
labels. This deliberately sacrifices arbitrary free-text context: visitor prose
and customer identifiers cannot reach upstream even if a browser client bypasses
its privacy filter. The UI previews exactly what the server will construct.

AI receives that canonical question and only matching public excerpts; it writes
short contextual prose with `[id]` citations. Validate strict JSON shape, source
membership, paragraph citations, size, links/markup/numbers, sensitive claims and
a conservative evidence vocabulary envelope. This reduces unsupported claims;
it is not a mathematical proof of entailment. AI is labeled generated, never
"verified content"; users can inspect the sources. Invalid output stays FAQ.

The real gateway is fixed to `https://ai-gateway.mesflow.net/v1`, `facebook-chat`.
The route must be non-queued with only grok-web/gemini-web/deepseek-web; cache this
verification for five minutes, validate actual provider on every completion.
No auto/paid/Claude/mock route, tools or raw model errors are exposed.

## Limits and measurements

- 9s wall deadline covering route check and completion, 10s browser abort.
  FAQ is already visible and the input remains enabled throughout. New questions
  or closing the dialog cancel display of obsolete results.
- Two worker slots, no unbounded queue, duplicate in-flight request returns FAQ
  immediately; five-minute cache, at most 20 upstream attempts/hour globally,
  six AI requests/minute/IP, 30s failure cooldown. FAQ does not consume AI budget.
  A timed-out upstream worker retains its slot until it exits; late answers are
  neither displayed nor cached. One gunicorn process is required.
- 1024-byte body; nginx strips Cookie/Authorization and overwrites client IP.
  No body/access logging, chat persistence, metrics prompts or entity IDs.
- Internal-only `/internal/metrics` reports aggregate counts by mode/fallback
  reason and rolling p50/p95 of the last 200 server durations per mode. It has
  **no nginx route**. Restart resets process-local metrics and budgets.
  Browser first-useful-answer measurements are recorded separately by Playwright.

The generated inline helper in `welcome.html` keeps FAQ available even if the
support service is down. Edit the service JSON/JS, then run
`python3 scripts/sync-public-support.py`; tests enforce `--check` synchronization.

## TEST deployment / rollback

Build only `services/public-support/Dockerfile` from the tested commit and
transfer the same immutable image to the verified TEST VPS `vps-78ae7aec`
(`148.113.207.13`, ready role `PRODUCTION_TEST`). Keep existing root-owned 0600
`/opt/mesflow/public-support.env` credentials. Update SUPPORT_IMAGE only in
`/opt/mesflow/public-support/.env`; run compose **only in that directory**.
The compose publishes no ports and joins only `mesflow-edge`.

Capture the actual nginx configuration and run
`scripts/prepare-support-assistant-nginx.py before.conf candidate.conf`.
It changes only `/support/chat` limits and adds two exact GET-only public asset
routes. All report, app, authentication and other locations remain byte-for-byte
identical. Check drift before replacement, validate `nginx -t`, replace the bind
file IN PLACE, reload (never recreate nginx). Synchronize welcome.html both at
`/opt/mesflow/public-showcase/` and in current `mesflow-nginx` container.

Back up config, both HTML copies, and the support `.env` before touching TEST.
Rollback restores those files, starts the previous support image from the
support-only compose, validates/reloads nginx. Check the MES app image and start
time are unchanged; do not deploy/restart the app, report service or DB.
No production endpoint, migration, business-data read/write, logout or session
revocation is part of verification. Probe public root, source/asset URLs,
anonymous app/auth guards and the public report link; real support generation
uses public excerpts only. Keep real latency/fallback evidence separate from
mocked browser tests. Health alone is never evidence of live AI.
