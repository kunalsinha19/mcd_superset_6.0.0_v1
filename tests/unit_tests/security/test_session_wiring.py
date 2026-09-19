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
"""Wiring of session revocation and the legacy-form block into the real app.

These build the actual Superset app, so they need a configured environment
and a reachable database (the same one `run_local.py` uses); they skip
themselves otherwise. Set at least SUPERSET_CONFIG_PATH, SUPERSET_SECRET_KEY
and GUEST_TOKEN_JWT_SECRET.

The first test is the regression test for a real bug: Flask-AppBuilder hands
`create_login_manager` a `current_app` LocalProxy, and Flask-Login sends its
signals with the *real* app as sender, so receivers connected to the proxy
silently never fired -- nothing was stamped and nothing was ever revoked.
"""
from __future__ import annotations

import os
from datetime import timedelta

import pytest
from flask import session
from flask_login import login_user, logout_user, user_logged_in, user_logged_out
from sqlalchemy import text

from superset.security.session_revocation import (
    is_session_revoked,
    new_session_id,
    revoke_session,
    SESSION_SID_KEY,
)

pytestmark = pytest.mark.skipif(
    not (os.environ.get("SUPERSET_CONFIG_PATH") and os.environ.get("SUPERSET_SECRET_KEY")),
    reason="needs a configured Superset app and database",
)


class StubUser:
    is_active = True
    is_authenticated = True
    is_anonymous = False

    def get_id(self) -> str:
        return "2147483000"


@pytest.fixture(scope="module")
def app():
    from superset.app import create_app

    return create_app()


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture
def sm(app):
    return app.appbuilder.sm


def _forget(sm, sid: str) -> None:
    sm.session.execute(text("delete from revoked_session where sid = :s"), {"s": sid})
    sm.session.commit()


def test_signal_receivers_are_bound_to_the_real_app_not_the_proxy(app) -> None:
    assert user_logged_in.has_receivers_for(app)
    assert user_logged_out.has_receivers_for(app)


def test_login_stamps_a_sid_and_logout_revokes_it(app, sm) -> None:
    with app.test_request_context("/"):
        login_user(StubUser())
        sid = session.get(SESSION_SID_KEY)
        assert sid, "login did not stamp a session id"
        assert is_session_revoked(sm.session, sid) is False
        try:
            logout_user()
            assert is_session_revoked(sm.session, sid) is True
            assert SESSION_SID_KEY not in session
        finally:
            _forget(sm, sid)


def test_each_login_gets_a_different_sid(app, sm) -> None:
    sids = []
    for _ in range(2):
        with app.test_request_context("/"):
            login_user(StubUser())
            sids.append(session[SESSION_SID_KEY])
    assert sids[0] != sids[1]


def test_a_second_login_on_the_same_session_retires_the_old_sid(app, sm) -> None:
    with app.test_request_context("/"):
        login_user(StubUser())
        first = session[SESSION_SID_KEY]
        login_user(StubUser())
        second = session[SESSION_SID_KEY]
        try:
            assert first != second
            assert is_session_revoked(sm.session, first) is True
            assert is_session_revoked(sm.session, second) is False
        finally:
            _forget(sm, first)


def test_session_loader_refuses_a_revoked_sid(app, sm, monkeypatch) -> None:
    monkeypatch.setattr(sm, "load_user", lambda pk: "A-USER")
    sid = new_session_id()
    revoke_session(sm.session, sid, timedelta(days=1))
    try:
        with app.test_request_context("/"):
            session["_user_id"] = "1"
            session[SESSION_SID_KEY] = sid
            assert sm._load_session_user("1") is None
            assert "_user_id" not in session  # cleared, not just ignored
    finally:
        _forget(sm, sid)


def test_session_loader_accepts_a_live_sid(app, sm, monkeypatch) -> None:
    monkeypatch.setattr(sm, "load_user", lambda pk: "A-USER")
    with app.test_request_context("/"):
        session["_user_id"] = "1"
        session[SESSION_SID_KEY] = new_session_id()
        assert sm._load_session_user("1") == "A-USER"


def test_legacy_session_without_a_sid_depends_on_session_require_sid(
    app, sm, monkeypatch
) -> None:
    monkeypatch.setattr(sm, "load_user", lambda pk: "A-USER")
    monkeypatch.setitem(app.config, "SESSION_REQUIRE_SID", False)
    with app.test_request_context("/"):
        session["_user_id"] = "1"
        assert sm._load_session_user("1") == "A-USER"  # default: not logged out
    monkeypatch.setitem(app.config, "SESSION_REQUIRE_SID", True)
    with app.test_request_context("/"):
        session["_user_id"] = "1"
        assert sm._load_session_user("1") is None  # pre-deploy cookie retired
        assert "_user_id" not in session


LEGACY_FORM_PATHS = [
    "/resetmypassword/form",
    "/resetpassword/form",
    "/users/add",
    "/users/edit/1",
    "/users/edit/1/",
]


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("path", LEGACY_FORM_PATHS)
def test_classic_password_forms_are_blocked_by_default(
    app, path, method, monkeypatch
) -> None:
    # CSRF protection would otherwise reject a token-less POST before the
    # block runs; switch it off so this proves the block itself.
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", False)
    assert app.test_client().open(path, method=method).status_code == 404


@pytest.mark.parametrize("path", LEGACY_FORM_PATHS)
def test_a_tokenless_post_to_a_classic_form_is_refused_anyway(app, path) -> None:
    response = app.test_client().post(path, data={"password": "x", "conf_password": "x"})
    assert response.status_code in (302, 400, 401, 403, 404)


def test_classic_password_forms_can_be_re_enabled(app, monkeypatch) -> None:
    monkeypatch.setitem(app.config, "LEGACY_PASSWORD_FORMS_ENABLED", True)
    assert app.test_client().get("/resetmypassword/form").status_code != 404


@pytest.mark.parametrize(
    "path", ["/users/list/", "/users/userinfo/", "/userinfoeditview/form"]
)
def test_neighbouring_user_pages_are_not_blocked(app, path) -> None:
    assert app.test_client().get(path).status_code != 404
