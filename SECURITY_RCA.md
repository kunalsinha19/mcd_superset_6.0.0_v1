# Security RCA — AAA Technologies Web App Security Audit (Superset)

Source report: *Web Application Security Audit Report of Superset*, AAA Technologies Ltd,
v2.0 (Level‑2), 20‑Aug‑2026. Client: NIC‑MCD. Target: `10.194.73.8/superset`.

This tracks root cause, fix status, and ownership for each finding against this fork.
Update the **Status / Fix commit** column as items are closed; don't delete rows —
history of what was disputed vs. fixed is the point of this doc.

Legend: 🔴 Open · 🟡 In progress · 🟢 Fixed · ⚪ Disputed (see notes)

## A. Genuine gaps — root cause confirmed in this repo

| # | Finding | Risk | Root cause | Evidence | Fix | Status / Fix commit |
|---|---|---|---|---|---|---|
| 4 | Password travels in clear text | High | App reachable over plain HTTP; TLS and secure-cookie flags not forced. | [config.py:1856-1857](superset/config.py#L1856-L1857) `force_https: False`, `session_cookie_secure: False`; [config.py:1901](superset/config.py#L1901) `SESSION_COOKIE_SECURE = False` | Set `force_https=True`, `session_cookie_secure=True` for real deployment; enforce HTTP→HTTPS redirect at proxy. | 🔴 Open |
| 6 | Dangerous method (OPTIONS) enabled | High | Flask/FAB auto-registers OPTIONS on every route by default; not disabled or blocked at edge. Note: cited CVE‑2004‑2320 (IIS/WebDAV) does not apply to this stack — the underlying "verbose Allow header" observation is still valid, cite is wrong. | No `automatic_options` restriction in [initialization/\_\_init\_\_.py](superset/initialization/__init__.py) or config | Block OPTIONS at reverse proxy, or set `provide_automatic_options=False` on blueprints. | 🔴 Open |
| 8 | Password history not maintained | Low | No `FAB_PASSWORD_COMPLEXITY_VALIDATOR` / reuse-check configured; no history table. | Confirmed absent from [config.py](superset/config.py) | Add password-history table + validator on reset-password command, or delegate to SSO/LDAP IdP. | 🔴 Open |
| 11 | Login form not protected (no CAPTCHA) | Low | Stock FAB `AuthDBView` login, unmodified. | `AUTH_TYPE = AUTH_DB` at [config.py:356](superset/config.py#L356) | Add hCaptcha/reCAPTCHA to login template; rate limiting (#9) partially mitigates. | 🔴 Open |
| 12, 14 | Port number / internal IP disclosure | Low | Leaked hostnames (`mcdonline.nic.in`, `esbm.mcdonline.nic.in`) and internal IPs/ports do **not** originate from this repo's config — introduced by the reverse proxy/load balancer echoing upstream addresses into response headers. | `grep -i mcdonline` across repo → no hits | Fix at proxy: strip/rewrite `Server`/upstream headers; don't let internal FQDNs/IPs leak into CSP directives sent to client. | 🔴 Open (infra, not app) |
| 13 | CSP misconfigured | Low | Reported `'unsafe-inline'`/`'unsafe-eval'` combo matches `TALISMAN_DEV_CONFIG`, not hardened prod config — tested env was likely serving dev CSP (`FLASK_ENV=development` or equivalent). Prod config separately still has `'unsafe-inline'` in `style-src`. | Dev: [config.py:1887](superset/config.py#L1887); Prod: [config.py:1849-1853](superset/config.py#L1849-L1853) | Confirm deployment runs prod config (`SUPERSET_ENV=production`, no `--debug`); remove `'unsafe-inline'` from prod `style-src` via nonced/external CSS. | 🔴 Open |

## B. Already fixed in code — verify it's actually live on the tested host

| # | Finding | Risk | Status | Notes |
|---|---|---|---|---|
| 7 | Outdated Apache Superset version | High | 🟢 Fixed | Upgraded 4.1.3 → 6.0.0 per audit's own email thread (Neha Yadav, 20‑Aug). Matches `Initial commit: MCD Superset 6.0.0 fork`. |
| 9 | No lockout implemented | Low | 🟢 Fixed | [superset_config.py.example:45-47](superset_config.py.example#L45-L47): `RATELIMIT_ENABLED=True`, `AUTH_RATE_LIMITED=True`, `AUTH_RATE_LIMIT="5 per minute"`. **Verify:** live host loads an actual `superset_config.py` (gitignored — not auto-deployed) with this set, and `RATELIMIT_STORAGE_URI` points at Redis, not in-memory (in-memory limiter resets per-worker on a multi-worker deployment, silently reopening this gap). |

**Systemic root cause worth chasing:** most items in bucket A are still "Not Complied" at Level‑2 despite fixes existing for #7 and #9. If the live `10.194.73.8` host isn't consistently pulling the current `superset_config.py`, none of the config-level fixes above will show up in a retest either. Confirm deployment/config-sync process before doing more remediation work that won't be visible to the next audit pass.

## C. Disputed — report doesn't demonstrate the claimed issue

| # | Finding | Risk (as reported) | Why disputed |
|---|---|---|---|
| 1 | Response Replay | High | Screenshot is an unremarkable Burp-intercepted login request/response. No replayed request, no session-fixation PoC, no evidence a captured response was resubmitted to bypass anything. Generic template text, identical framing at both L1 and L2. |
| 2 | Weak Algorithm is used | High | Screenshot shows Burp *Decoder* reading Base64 back to `Admin@123` — normal transport encoding, not a broken hash/cipher. No algorithm (MD5/SHA1/DES) actually identified in the app. |
| 3 | Broken Access Control | High | Screenshots show the tester's own dashboards loading normally. No cross-tenant/IDOR access demonstrated (e.g., swapping another user's `native_filters_key` and retrieving their data). |
| 10 | Buffer overflow possible | Low | Python/Flask has no classical stack-buffer-overflow surface. The actual observation ("max length not defined on input fields") is a real, separate, minor issue — missing input length validation — mislabeled with an inapplicable CWE/title. |

**Action:** request a reproducible PoC (exact request/response pair + the specific unauthorized outcome achieved) from AAA Technologies for #1–#3 before allocating engineering time; recommend re-titling #10 as "Missing input length validation" rather than "Buffer overflow."

## Also flagged, not a code fix

- The PDF's screenshots contain live-looking credentials (`admin`/`admin`, `admin`/`Admin@123`) for the tested environment. Rotate these regardless of test-account status — the document circulates by email and gets archived.

## E. Retest validity — two problems with how the audit itself was run (added 2026‑08‑24)

Two facts changed the read on nearly every "Not Complied" result above:

### E.1 — Level‑2 retest ran against unfixed 6.0.0, not this fork's remediation work

`superset_config.py` is intentionally gitignored and mounted per-environment
([.gitignore:3](.gitignore#L3), [docker-compose.yml:56](docker-compose.yml#L56)) — none of the
fixes tracked in sections A/D above (`force_https`, `RATELIMIT_STORAGE_URI`, CAPTCHA, password
history, `SECRET_KEY`/DB-password rotation) are things that ship by editing this repo's tracked
code; they land on the live host's own config file. The Level‑2 email thread (finding #5) only
confirms the **version bump** (4.1.3→6.0.0) was communicated as done — it says nothing about the
config/code hardening. Given 12 of 14 findings still read "Not Complied" after that retest, the
simplest explanation is that `10.194.73.8` was retested on a build that predates this hardening
work, not that the fixes don't work.

**Root cause:** no gate ties "request a retest" to "confirm the target host is running the
branch + `superset_config.py` the fixes actually landed in." This is a process gap, not a code
gap — it needs a pre-retest checklist, not a PR: (1) deploy current code, (2) push the updated
`superset_config.py` with `force_https`, `session_cookie_secure`, `RATELIMIT_STORAGE_URI`,
rotated `SECRET_KEY`/DB password, (3) confirm `FLASK_DEBUG` is unset, (4) only then ask AAA for
Level‑3.

**Action:** don't spend more remediation effort reacting to the Level‑2 "Not Complied" statuses
individually — most of them are stale by construction. Re-verify against the checklist above,
then request a clean retest.

### E.2 — Auditor is benchmarking against Superset 6.1.0, not a specific known CVE

6.1.0 was released 13‑May‑2026 and is primarily a **feature** release — Matrixify control-panel
revamp, a dataset-folders editor, and a new (opt-in, flag-gated) Task framework — not a
security-patch release. [Preset's 6.1 release post](https://preset.io/blog/apache-superset-6-1-release/)
doesn't mention any CVE fix. Checking Superset's own "CVEs fixed by release" page (fetched
2026‑08‑24, page last updated 2026‑08‑22 — i.e. current):

| CVE | Issue | Fixed in |
|---|---|---|
| CVE‑2026‑23980 | Improper Neutralization of Special Elements used in a SQL Command | 6.0.0 |
| CVE‑2026‑23982 | Improper Authorization in Dataset Creation — access control bypass | 6.0.0 |
| CVE‑2026‑23983 | Information Disclosure of sensitive user info via Tags | 6.0.0 |
| CVE‑2026‑23984 | SQLLab Read-Only Bypass on PostgreSQL (DML execution) | 6.0.0 |

All four affected versions **before** 6.0.0 and are already fixed in the 6.0.0 this fork is on
([package.json:3](superset-frontend/package.json#L3) confirms `"version": "6.0.0"`). As of this
check, there is no CVE published against 6.0.x that 6.1.0 specifically remediates — 6.1.0's own
"latest non-vulnerable version" label on scanner sites (Snyk/cvedetails) looks like it just means
"newest release with zero CVEs filed yet," which is true of any brand-new release by default, not
evidence 6.0.0 has an open hole.

This also explains an inconsistency worth pointing out to AAA directly: findings **#5 "Vulnerable
Version"** (Not Complied) and **#7 "Outdated Version"** (Complied) use identical abstract text and
the identical evidence (the same screenshot, the same Neha Yadav email) but got opposite verdicts.
That's consistent with #5 being scored by an automated "is this the latest tag?" check and #7 by a
human manually confirming the upgrade happened — i.e. the same finding, counted twice, disagreeing
with itself.

**Action for the reply to AAA:** ask them to name the specific CVE/advisory 6.1.0 fixes that
6.0.0 doesn't — if none exists, #5 should be downgraded/merged into #7 rather than tracked as an
open High. Separately, still worth planning a 6.0.0→6.1.0 upgrade on normal cadence (staying
current is good hygiene, and this fork carries custom patches — PDF export, embedding, the
Python 3.13/SQLAlchemy 2.0 compatibility fixes — that need re-verification against 6.1.0 before
that bump, which is real engineering work, just not urgent/security-driven work).

## F. New claim (2026‑08‑24, verbal, no PoC yet): "we can log in without knowing the password"

AAA has raised this outside the written report, with no request/response evidence yet. "Login
without a password" against a Flask/Flask-AppBuilder app is almost always one of a short, known
list of mechanisms — and the fix is different for each, so **the first ask is the reproduction
steps** (exact request, or which tool they used), not a blind fix.

**Primary suspect, ranked by how well it matches evidence we already have:**

**Forged Flask-Login session cookie via the weak `SECRET_KEY`.** Flask signs the session cookie
(which is where Flask-Login stores `_user_id` for an authenticated session, and where the
"remember me" token lives too) using `SECRET_KEY` via `itsdangerous`. Anyone who has or can
derive that key can mint a cookie claiming to be `_user_id=1` (admin) themselves — no password
prompt ever touched, no bruteforce, no lockout to trip. This is exactly the class of bug tools
like `flask-unsign` are built to demonstrate, and it's a two-step attack: capture *any* cookie the
app sets (even for an anonymous visitor — Flask sets one as soon as anything touches `session`,
e.g. CSRF token storage or locale), then crack/guess `SECRET_KEY` offline against it.

We already flagged this key before this claim came up: [superset_config.py:5-6](superset_config.py#L5-L6)
holds `SECRET_KEY = "SupersetDev2024!@#$%^&*()_+-=[]{}|;:',.<>?/~\`abcd1234"` — a human-composed,
comment-labeled *"generated for development"* string, not `secrets.token_urlsafe()` output. Whether
AAA cracked it, found it reused from a shared example/tutorial, or obtained it some other way, the
fix is the same and is a config change, not a code change:

**Action — do this now, independent of getting a PoC:** rotate `SECRET_KEY` in the live
`superset_config.py` to a real generated value. This alone invalidates every existing session
*and* every forged cookie built against the old key, closing this path immediately regardless of
how they got in. Plan for the fact that it logs everyone out.

**Checked and ruled less likely:**

- **Guest-token misuse (`EMBEDDED_SUPERSET`/`PUBLIC_ROLE_LIKE=Gamma`):** the `/api/v1/security/guest_token/`
  endpoint is `@protect()`-gated behind the `grant_guest_token` permission
  ([security/api.py:137-143](superset/security/api.py#L137-L143)), which stock FAB/Superset does
  not grant to Gamma/Public by default — so minting a guest token still requires an already
  privileged, already-authenticated session. Worth a one-time check that this fork's
  `PUBLIC_ROLE_LIKE` mirroring didn't inadvertently carry that permission onto Gamma, but this
  isn't a no-credential bypass on its own.
- **Default admin bootstrap:** `deploy/entrypoint.sh` only creates the admin account when
  `SUPERSET_ADMIN_USERNAME`/`SUPERSET_ADMIN_PASSWORD` env vars are explicitly set, and skips
  creation if the user already exists — no hardcoded default credential in that path.
- **Custom auth bypass in this fork's `SupersetSecurityManager`:** no suspicious override found
  on inspection (no `bypass`/`skip_auth`/hardcoded-credential patterns anywhere in `superset/`);
  can't fully rule this out without the specific request AAA used, though.

**Query to send AAA:** ask for the exact request (or tool name, e.g. `flask-unsign`) they used, so
the fix can be verified against the real mechanism rather than guessed at. Status: 🔴 Open,
unconfirmed mechanism — `SECRET_KEY` rotation queued as a same-day mitigation regardless.

## D. Newly discovered by reading the live `superset_config.py`

`superset_config.py` is gitignored ([.gitignore:3](.gitignore#L3)) and mounted per-environment
([docker-compose.yml:56](docker-compose.yml#L56) — "the one file every environment must supply
for itself"). Reading the actual file in use (not the `.example` template) surfaces issues the
PDF never tested for:

| Finding | Root cause | Evidence |
|---|---|---|
| Weak, hardcoded session signing key | `SECRET_KEY` is a predictable, comment-labeled "development" string, not a generated secret. Anyone who has seen this value (repo history, a shared screen, a backup) can forge signed session cookies. | [superset_config.py:5-6](superset_config.py#L5-L6) |
| Default database credentials | `postgres:postgres` on `10.197.214.46:5432/SDMC_BETA` — factory-default Postgres credentials against a real internal host. That IP is in the same `10.197.214.x` range the audit already flagged as disclosed externally (findings #12/#14) — if that range is reachable from outside the perimeter, this is a direct DB-compromise path, not just an info leak. | [superset_config.py:9](superset_config.py#L9) |
| Rate limiting weaker than intended | `RATELIMIT_ENABLED`/`AUTH_RATE_LIMIT` are set (good — fixes #9 as reported), but `RATELIMIT_STORAGE_URI` is never set. Flask-Limiter then defaults to **in-memory, per-process** storage. Container runs gunicorn with `--workers 4` ([Dockerfile:66-73](Dockerfile#L66-L73)), so 4 independent counters exist — effective limit is closer to `4 × 5/min` than `5/min`, and it resets on every worker restart/deploy. A Redis service already exists in the reference compose file ([docker-compose.yml:26-35](docker-compose.yml#L26-L35)) but isn't wired to the limiter. | [superset_config.py:40-42](superset_config.py#L40-L42), no `RATELIMIT_STORAGE_URI` |
| Dev CSP likely served in "beta" | `TALISMAN_DEV_CONFIG` (the `'unsafe-inline'`/`'unsafe-eval'` one the audit caught in #13) is selected whenever `FLASK_DEBUG` is truthy ([initialization/\_\_init\_\_.py:832-838](superset/initialization/__init__.py#L832-L838), driven by [config.py:290](superset/config.py#L290)). `superset_config.py` doesn't override this, so whatever's in the live process's `FLASK_DEBUG` env var decides it — worth confirming that's unset/false on the host, since debug mode on a reachable host is also a much bigger risk than CSP alone (Werkzeug's interactive debugger is RCE if reachable). | [config.py:290](superset/config.py#L290) |

Contrast: `GUEST_TOKEN_JWT_SECRET` in this same file **is** a properly generated random value
([superset_config.py:35](superset_config.py#L35)) — proof the team knows how to do this correctly.
`SECRET_KEY` and the DB password just weren't rotated the same way.

## Code-level vs. admin-level split

**Code-level = requires a change in this repository (new code/config template, needs a PR + review).**
**Admin-level = a value or process on the live host/infra — no repo change, owned by whoever manages `10.194.73.8` and its `superset_config.py`.**

| Item | Level | What's needed |
|---|---|---|
| #8 Password history | 🧑‍💻 Code | New validator + history table/migration — FAB has no built-in reuse check to just configure. |
| #11 No CAPTCHA on login | 🧑‍💻 Code | Integrate hCaptcha/reCAPTCHA into the FAB login view/template — doesn't exist to enable via config. |
| #10 Missing input length validation | 🧑‍💻 Code | Add `maxlength` client-side + server-side length validation on forms/serializers. |
| #13 (residual) `'unsafe-inline'` in prod `style-src` | 🧑‍💻 Code | Move inline styles to nonce/external CSS in `TALISMAN_CONFIG` ([config.py:1849-1853](superset/config.py#L1849-L1853)). |
| Ratelimit storage template | 🧑‍💻 Code (template only) | Add a commented, documented `RATELIMIT_STORAGE_URI` line to `superset_config.py.example` pointing at the compose `redis` service, so new environments don't silently ship in-memory limiting. |
| #4 Force HTTPS / secure cookies | 🛠️ Admin | Set `force_https=True`, `session_cookie_secure=True` in the **live** `superset_config.py`; terminate TLS and redirect HTTP→HTTPS at the proxy in front of `10.194.73.8`. |
| #6 OPTIONS method exposed | 🛠️ Admin | Block/deny `OPTIONS` at the reverse proxy/load balancer. |
| #9 Rate limit storage | 🛠️ Admin | Set `RATELIMIT_STORAGE_URI = "redis://<redis-host>:6379/0"` in the live `superset_config.py` and confirm Redis is actually reachable from the app host. |
| #12 / #14 Port & internal IP disclosure | 🛠️ Admin | Strip/rewrite upstream headers and internal hostnames/IPs at the reverse proxy/LB — not present anywhere in app config or code. |
| #13 (root cause) Dev CSP served | 🛠️ Admin | Confirm `FLASK_DEBUG` is unset/false and `SUPERSET_ENV=production` in the live process environment. Also independently audit whether the Werkzeug debugger is reachable — separate, higher-severity check. |
| **New:** weak `SECRET_KEY` | 🛠️ Admin | Rotate to a real generated secret (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) in the live `superset_config.py`. This invalidates all active sessions on rotation — schedule it. |
| **New:** default DB password | 🛠️ Admin | Rotate the Postgres password for `10.197.214.46`/`SDMC_BETA` off `postgres:postgres`, update `SQLALCHEMY_DATABASE_URI` in the live `superset_config.py`, and confirm that host isn't reachable from outside the trusted network. |
| Config-sync process | 🛠️ Admin | Confirm the host being retested actually loads the `superset_config.py` with these values — several "Not Complied" Level‑2 results may just mean the fix never shipped to that box. |
| Credentials shown in the audit PDF | 🛠️ Admin | Rotate the app admin password used during testing. |
| #1 / #2 / #3 (disputed) | ⚪ Neither, yet | No action until AAA Technologies provides a reproducible request/response chain — nothing to fix in code or config against what's currently documented. |

**Bottom line:** of the items still genuinely open, code changes are needed for 4 things (#8, #11, #10, residual #13), and everything else — including two issues worse than anything in the original report (weak `SECRET_KEY`, default DB password) — is a same-day config/credential change on the live host, no PR required.
