# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Throttling of POST /api/v1/security/login (audit #9 / #11).

Before this, the JWT login had no limit at all -- FAB's AUTH_RATE_LIMIT is only
attached to the web auth blueprint -- so it allowed unlimited password
guessing. Builds the real app, so it skips without a configured environment.
Each test uses its own client address so the per-client buckets don't collide.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not (os.environ.get("SUPERSET_CONFIG_PATH") and os.environ.get("SUPERSET_SECRET_KEY")),
    reason="needs a configured Superset app and database",
)

URL = "/api/v1/security/login"


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


def _post(app, ip: str, username: str, password: str = "wrong") -> int:
    return (
        app.test_client()
        .post(
            URL,
            json={"username": username, "password": password, "provider": "db"},
            environ_base={"REMOTE_ADDR": ip},
        )
        .status_code
    )


def _unique() -> str:
    return "nouser-" + uuid.uuid4().hex[:10]


def test_repeated_failures_for_one_username_are_throttled(app, monkeypatch) -> None:
    monkeypatch.setitem(app.config, "API_LOGIN_RATE_LIMIT", "3 per minute")
    name = _unique()
    codes = [_post(app, "10.20.0.1", name) for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]


def test_one_locked_username_does_not_lock_others_on_the_same_client(
    app, monkeypatch
) -> None:
    monkeypatch.setitem(app.config, "API_LOGIN_RATE_LIMIT", "2 per minute")
    for _ in range(4):
        _post(app, "10.20.0.2", "victim-of-typos")
    assert _post(app, "10.20.0.2", "victim-of-typos") == 429
    assert _post(app, "10.20.0.2", _unique()) == 401  # someone else, not locked


def test_spraying_many_usernames_from_one_client_is_capped(app, monkeypatch) -> None:
    monkeypatch.setitem(app.config, "API_LOGIN_IP_RATE_LIMIT", "4 per minute")
    codes = [_post(app, "10.20.0.3", _unique()) for _ in range(7)]
    assert codes[:4] == [401, 401, 401, 401]
    assert set(codes[4:]) == {429}


def test_a_different_client_is_not_affected(app, monkeypatch) -> None:
    monkeypatch.setitem(app.config, "API_LOGIN_RATE_LIMIT", "2 per minute")
    name = _unique()
    for _ in range(4):
        _post(app, "10.20.0.4", name)
    assert _post(app, "10.20.0.4", name) == 429
    assert _post(app, "10.20.0.5", name) == 401


def test_successful_logins_are_never_counted(app, monkeypatch) -> None:
    monkeypatch.setitem(app.config, "API_LOGIN_RATE_LIMIT", "2 per minute")
    monkeypatch.setitem(app.config, "API_LOGIN_IP_RATE_LIMIT", "2 per minute")
    sm = app.appbuilder.sm
    name, password = "zz_api_limit_" + uuid.uuid4().hex[:6], "Tt9!" + uuid.uuid4().hex[:12]
    sm.add_user(name, "Api", "Limit", name + "@example.invalid", sm.find_role("Gamma"), password)
    try:
        assert [_post(app, "10.20.0.6", name, password) for _ in range(8)] == [200] * 8
    finally:
        sm.session.rollback()
        for (uid,) in sm.session.execute(
            text("select id from ab_user where username = :n"), {"n": name}
        ).fetchall():
            for table in ("ab_user_role", "user_password_history", "logs"):
                sm.session.execute(text(f"delete from {table} where user_id = :u"), {"u": uid})
            sm.session.execute(text("delete from ab_user where id = :u"), {"u": uid})
        sm.session.commit()


def test_the_refresh_endpoint_is_not_throttled_by_this(app, monkeypatch) -> None:
    monkeypatch.setitem(app.config, "API_LOGIN_RATE_LIMIT", "1 per minute")
    monkeypatch.setitem(app.config, "API_LOGIN_IP_RATE_LIMIT", "1 per minute")
    codes = {
        app.test_client()
        .post("/api/v1/security/refresh", environ_base={"REMOTE_ADDR": "10.20.0.7"})
        .status_code
        for _ in range(4)
    }
    assert 429 not in codes
