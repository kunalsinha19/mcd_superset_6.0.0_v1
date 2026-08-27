# Deployment handoff notes

## What this is
A Docker-packaged version of this Superset fork with the Python 3.13 /
SQLAlchemy 2.0 / Flask-SQLAlchemy 3.x compatibility fixes applied, plus
per-chart PDF export and dashboard embedding support. Frontend is
pre-built (`superset/static/assets/`) -- no Node.js is needed to build or
run the image.

## Before you build: read this
**The JWT-based auth / role-mapping feature referenced in the production
`superset_config.py` (`ENABLE_JWT_AUTH`, `JWT_ROLE_MAPPINGS`,
`JWT_ROLE_CLAIM`, etc.) is not implemented in this codebase.** Those
config keys are not read anywhere in the source -- confirmed by exhaustive
search. If the Angular frontend's login flow depends on that JWT bridge
actually working, it will not work against this image as-is. Either:
- your team already maintains that auth bridge as a separate layer/patch
  applied during your own deployment process, or
- it needs to be located and ported in before this replaces production.

This was flagged, not silently dropped -- confirm which case applies
before cutting over.

## What you actually need to do

1. **Copy `superset_config.py.example` to `superset_config.py`** and fill
   in real values for this environment. Never commit the filled-in file --
   it's gitignored. In particular:
   - `SECRET_KEY` -- generate once (`python -c "import secrets;
     print(secrets.token_urlsafe(48))"`) and **back it up in a secrets
     vault immediately**. It's not just session signing -- anything
     Superset encrypts at rest (saved DB connection passwords, etc.)
     depends on this exact value forever. Swapping it later breaks
     decryption of everything encrypted under the old one; there's no
     recovery short of a proper `re-encrypt-secrets` migration. Confirmed
     this failure mode directly during local testing.
   - `GUEST_TOKEN_JWT_SECRET` -- generate the same way, a different value.
   - `SQLALCHEMY_DATABASE_URI` -- the real server DB, not a local one.
   - `RATELIMIT_STORAGE_URI` -- real Redis (`redis://<host>:6379/2`), not
     `memory://`. Also set `RATELIMIT_SWALLOW_ERRORS = True` -- without
     it, a Redis blip makes every request 500 instead of degrading
     gracefully (hit this exact failure locally).
   - `SESSION_COOKIE_SAMESITE` / `SESSION_COOKIE_SECURE` -- set as a
     matched pair per the comment in `.example`. Getting this wrong drops
     the session cookie silently in the browser and breaks login/CSRF in
     a way that doesn't obviously point back to this setting.
   - CORS origins / CSP `frame-ancestors`, Redis host -- real values for
     this environment.
   - `SUPERSET_ADMIN_USERNAME` / `SUPERSET_ADMIN_PASSWORD` /
     `SUPERSET_ADMIN_EMAIL` -- set as container env vars. A fresh DB has
     zero users; this is how the first admin login gets created (see
     below).
2. **Build the image**: `docker build -t mcd-superset:6.0.0 .`
3. **Run it** -- either via the provided `docker-compose.yml` (a starting
   point, adjust to match your actual Postgres/Redis) or your own
   orchestration. Mount `superset_config.py` into the container at
   `/app/superset_config.py`.
4. That's it for the app itself -- `deploy/entrypoint.sh` runs
   `flask db upgrade` and role/permission sync (`superset init`)
   automatically on every container start, so there's no separate manual
   migration step.

## Optional: bootstrap an admin user automatically
Set these env vars on the `superset` service and the entrypoint creates
the user on first boot (skips silently if it already exists, so it's safe
to leave set across restarts):
- `SUPERSET_ADMIN_USERNAME`
- `SUPERSET_ADMIN_PASSWORD`
- `SUPERSET_ADMIN_EMAIL` (optional, defaults to `admin@example.com`)

## Verify before calling it live
- [ ] Log in with the bootstrapped admin account.
- [ ] `curl <host>/health` -> `200`.
- [ ] `curl <host>/static/version_info.json` -> should `404` (confirms the
      version-fingerprint-file block is active -- see "Version disclosure"
      below).
- [ ] Create one throwaway dashboard/chart to confirm the DB write path
      works end-to-end on the real database.
- [ ] If scheduled reports/alerts/thumbnails matter for launch, run one
      through a Celery worker -- this has not been exercised in any
      testing so far, local or otherwise (see Known gaps below).

## Version disclosure -- fixed, worth knowing how
Two things used to leak the exact Superset version/build; both are now
blocked in code rather than left as a config toggle someone has to
remember to set:
- `/static/version_info.json` and `/static/assets/package.json` (served
  unauthenticated by default -- confirmed this is what automated scanners
  fingerprint first) now 404. See `configure_middlewares()` in
  `superset/initialization/__init__.py`.
- The authenticated Settings > About menu and the telemetry pixel no
  longer show version/SHA/build -- gated behind a new feature flag,
  `MENU_HIDE_VERSION_INFO`, defaulted to `True` in `superset/config.py`.
  Set it `False` in `FEATURE_FLAGS` in your `superset_config.py` if you
  ever want it back (e.g. internal debugging).

## Known gaps / things I could not verify from here
- **gunicorn was never actually run in this session.** Development
  happened on Windows, where gunicorn can't even install (`fcntl`
  doesn't exist there) -- `waitress` was used instead for local testing.
  `gunicorn==23.0.0` is pinned in `requirements-lock.txt` and the
  Dockerfile's CMD is a standard invocation, but **this specific piece
  needs a real smoke test on Linux** before you trust it. If it doesn't
  come up cleanly, that's the first thing to look at.
- **Celery/Redis-backed async queries, scheduled reports, alerts, and
  thumbnails were never exercised this session** -- only synchronous
  chart rendering, exports, and embedding were tested end-to-end. Given
  nearly everything else in this codebase needed a fix for the
  Python 3.13 / newer-dependency jump, treat these as unverified until
  someone runs an actual report/alert through the worker.
- **Dependency pinning**: `requirements-lock.txt` is frozen from the
  exact working dev environment. Do not `pip install .` from
  `pyproject.toml`'s own (loose) version ranges for a production build --
  that's what caused the original round of compatibility bugs in the
  first place, since pip resolves whatever the newest allowed version is
  at build time.
- **Multiple gitignored/untested config toggles** in the production
  config you shared aren't real Superset settings and are currently
  silent no-ops there: `SUPERSET_APP_INITIALIZER` (real hook is
  `FLASK_APP_MUTATOR`) and `EXTRA_CSS`. Worth knowing before assuming
  those are doing anything today, JWT auth aside.
