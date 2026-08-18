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
   in real values for this environment: `SECRET_KEY`,
   `GUEST_TOKEN_JWT_SECRET`, `SQLALCHEMY_DATABASE_URI`, Redis host, CORS
   origins, etc. Never commit the filled-in file -- it's gitignored.
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
