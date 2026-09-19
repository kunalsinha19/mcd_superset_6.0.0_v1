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
"""enc_password -> password hook for the authenticated endpoints (audit #4)."""
from __future__ import annotations

import pytest
from flask import Flask, request
from werkzeug.exceptions import BadRequest

from superset.security.password_transport import (
    decrypt_password_in_request,
    issue_password_key,
    PASSWORD_ENC_NONCE_SESSION_KEY,
)

from .test_login_encryption import encrypt_like_browser

SECRET = "transport-test-secret"


@pytest.fixture
def flask_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET
    return app


def test_issue_password_key_returns_key_and_stores_a_fresh_nonce(flask_app) -> None:
    with flask_app.test_request_context("/api/v1/me/password_key"):
        from flask import session

        first = issue_password_key()
        assert first["key"] and first["nonce"]
        assert session[PASSWORD_ENC_NONCE_SESSION_KEY] == first["nonce"]
        assert issue_password_key()["nonce"] != first["nonce"]


def test_issue_password_key_is_empty_when_disabled(flask_app) -> None:
    flask_app.config["LOGIN_PASSWORD_ENCRYPTION"] = False
    with flask_app.test_request_context("/api/v1/me/password_key"):
        assert issue_password_key() == {"key": "", "nonce": ""}


@pytest.mark.parametrize(
    "method,path",
    [
        ("PUT", "/api/v1/me/"),
        ("POST", "/api/v1/security/users/"),
        ("PUT", "/api/v1/security/users/7"),
    ],
)
def test_enc_password_becomes_password_on_the_covered_endpoints(
    flask_app, method: str, path: str
) -> None:
    with flask_app.test_request_context(path, method=method, json={"first_name": "A"}):
        nonce = issue_password_key()["nonce"]
    with flask_app.test_request_context(
        path,
        method=method,
        json={
            "first_name": "A",
            "enc_password": encrypt_like_browser("N3w-Pass!", SECRET, nonce),
        },
    ) as ctx:
        ctx.session[PASSWORD_ENC_NONCE_SESSION_KEY] = nonce
        decrypt_password_in_request()
        body = request.get_json()
        assert body["password"] == "N3w-Pass!"
        assert "enc_password" not in body
        assert body["first_name"] == "A"
        # consumed: the nonce cannot be used twice
        assert PASSWORD_ENC_NONCE_SESSION_KEY not in ctx.session


def test_nonce_is_single_use(flask_app) -> None:
    body = {"enc_password": encrypt_like_browser("pw", SECRET, "n1")}
    with flask_app.test_request_context("/api/v1/me/", method="PUT", json=body) as ctx:
        ctx.session[PASSWORD_ENC_NONCE_SESSION_KEY] = "n1"
        decrypt_password_in_request()
    with flask_app.test_request_context("/api/v1/me/", method="PUT", json=body):
        # fresh request context = fresh session with no nonce left
        with pytest.raises(BadRequest):
            decrypt_password_in_request()


@pytest.mark.parametrize("bad", ["garbage", "", None, 123, ["x"]])
def test_undecryptable_enc_password_is_a_400(flask_app, bad) -> None:
    with flask_app.test_request_context(
        "/api/v1/me/", method="PUT", json={"enc_password": bad}
    ) as ctx:
        ctx.session[PASSWORD_ENC_NONCE_SESSION_KEY] = "n1"
        with pytest.raises(BadRequest):
            decrypt_password_in_request()


def test_wrong_nonce_is_a_400(flask_app) -> None:
    with flask_app.test_request_context(
        "/api/v1/me/",
        method="PUT",
        json={"enc_password": encrypt_like_browser("pw", SECRET, "the-real-one")},
    ) as ctx:
        ctx.session[PASSWORD_ENC_NONCE_SESSION_KEY] = "a-different-one"
        with pytest.raises(BadRequest):
            decrypt_password_in_request()


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("PUT", "/api/v1/me/", {"password": "plain-still-works"}),  # API clients
        ("GET", "/api/v1/me/", None),
        ("PUT", "/api/v1/dashboard/1", {"enc_password": "ignored-here"}),
        ("POST", "/login/", {"enc_password": "handled-by-login-view"}),
        ("PUT", "/api/v1/security/users/7/extra", {"enc_password": "x"}),
    ],
)
def test_other_requests_are_left_alone(flask_app, method, path, body) -> None:
    with flask_app.test_request_context(path, method=method, json=body):
        decrypt_password_in_request()  # must not raise or consume anything
        if body is not None:
            assert request.get_json() == body
