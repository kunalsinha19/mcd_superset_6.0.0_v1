#!/bin/bash
# Runs on every container start, before the CMD (gunicorn) takes over.
#
# - `flask db upgrade` and `superset init` are both safe to run every time
#   (idempotent -- upgrade is a no-op once at head, init just re-syncs
#   roles/permissions). This is what makes "just supply superset_config.py
#   and start the container" actually work without a separate manual step.
# - Admin user creation is opt-in via env vars and only attempted if the
#   user doesn't already exist, so restarts don't fail on "user exists".
set -e

echo "[entrypoint] Waiting for the database to accept connections..."
python - <<'PYEOF'
import sys
import time

from superset.app import create_app

for attempt in range(30):
    try:
        app = create_app()
        with app.app_context():
            from superset import db
            from sqlalchemy import text
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        print("[entrypoint] Database reachable.")
        sys.exit(0)
    except Exception as ex:  # noqa: BLE001
        print(f"[entrypoint] DB not ready yet ({ex}); retrying...")
        time.sleep(2)
print("[entrypoint] Database never became reachable; continuing anyway.")
PYEOF

echo "[entrypoint] Checking whether this database has been bootstrapped yet..."
# Checks for `ab_user` specifically, not "any tables at all" -- the target
# database may already contain unrelated tables from another application
# sharing the same Postgres instance.
FRESH_DB=$(python -c "
import superset.app
app = superset.app.create_app()
with app.app_context():
    import sqlalchemy
    from superset import db
    insp = sqlalchemy.inspect(db.engine)
    print('yes' if 'ab_user' not in insp.get_table_names() else 'no')
" 2>/dev/null | tail -1)

if [ "$FRESH_DB" = "yes" ]; then
    # On a database with no ab_user table yet, `flask db upgrade` fails on
    # its very first migration: the earliest revisions create tables with
    # foreign keys into ab_user, which only Flask-AppBuilder's own bootstrap
    # (not Alembic) creates -- and that bootstrap only runs when explicitly
    # invoked, not automatically on app boot. Trigger it directly, which
    # builds the full current-model schema in one shot, then mark migration
    # history as already at head instead of replaying 300+ migrations
    # against a schema that already matches their end state.
    echo "[entrypoint] Not bootstrapped yet -- creating schema from current models..."
    python -c "
import superset.app
app = superset.app.create_app()
with app.app_context():
    from superset.extensions import appbuilder
    appbuilder.sm.create_db()
"
    echo "[entrypoint] Stamping migration history as up to date..."
    flask --app superset.app:create_app db stamp head
else
    echo "[entrypoint] Running database migrations (flask db upgrade)..."
    flask --app superset.app:create_app db upgrade
fi

if [ -n "$SUPERSET_ADMIN_USERNAME" ] && [ -n "$SUPERSET_ADMIN_PASSWORD" ]; then
    echo "[entrypoint] Ensuring admin user '$SUPERSET_ADMIN_USERNAME' exists..."
    flask --app superset.app:create_app fab create-admin \
        --username "$SUPERSET_ADMIN_USERNAME" \
        --firstname "${SUPERSET_ADMIN_FIRSTNAME:-Admin}" \
        --lastname "${SUPERSET_ADMIN_LASTNAME:-User}" \
        --email "${SUPERSET_ADMIN_EMAIL:-admin@example.com}" \
        --password "$SUPERSET_ADMIN_PASSWORD" \
        || echo "[entrypoint] create-admin skipped (user likely already exists)."
fi

echo "[entrypoint] Syncing roles/permissions (superset init)..."
# `init` isn't registered on the plain `flask` CLI in this fork (no
# console-script entry point in pyproject.toml) -- it only exists on the
# custom superset.cli.main click group, so it must be invoked this way.
python -c "from superset.cli.main import superset; superset()" init

echo "[entrypoint] Startup checks complete, handing off to: $*"
exec "$@"
