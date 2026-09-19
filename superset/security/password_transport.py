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
"""Encrypted-password transport for the *authenticated* password endpoints
(audit finding #4), the counterpart of what login_captcha.py does for login.

Three endpoints accept a password in a JSON body: `PUT /api/v1/me/`
(change my password) and `POST`/`PUT /api/v1/security/users/[<id>]` (admin
creates or updates a user). The browser now sends `enc_password` (see
superset/security/login_encryption.py and
superset-frontend/src/utils/passwordEncryption.ts) instead of `password`.

Rather than reimplement three FAB/marshmallow request paths, a single
`before_request` hook turns `enc_password` back into `password` *inside the
parsed JSON body* before any view or schema sees it. Everything downstream --
length checks, complexity validator, password-history reuse check, scrypt
hashing -- therefore behaves exactly as it does today, and plain `password`
requests (API clients, scripts, non-HTTPS hosts) keep working untouched.
"""
from __future__ import annotations

import re
import secrets
from typing import Any

from flask import current_app, request, session
from werkzeug.exceptions import BadRequest

from superset.security.login_encryption import (
    decrypt_login_password,
    server_public_key,
)

PASSWORD_ENC_NONCE_SESSION_KEY = "pw_enc_nonce"  # noqa: S105 -- not a credential

_ENCRYPTED_PASSWORD_PATHS = re.compile(r"^/api/v1/(me|security/users(/\d+)?)/?$")


def issue_password_key() -> dict[str, str]:
    """Key + fresh single-use nonce for the calling (logged-in) session.
    Empty strings when encryption is switched off, which the browser treats
    as "send the password the old way"."""
    if not current_app.config.get("LOGIN_PASSWORD_ENCRYPTION", True):
        return {"key": "", "nonce": ""}
    nonce = secrets.token_urlsafe(16)
    session[PASSWORD_ENC_NONCE_SESSION_KEY] = nonce
    return {
        "key": server_public_key(current_app.config["SECRET_KEY"]),
        "nonce": nonce,
    }


def decrypt_password_in_request() -> None:
    """before_request hook: `enc_password` -> `password`, in place."""
    if request.method not in ("POST", "PUT") or not request.is_json:
        return
    if not _ENCRYPTED_PASSWORD_PATHS.match(request.path):
        return
    data: Any = request.get_json(silent=True)
    if not isinstance(data, dict) or "enc_password" not in data:
        return

    # Consumed whether or not it decrypts: one nonce, one attempt.
    nonce = session.pop(PASSWORD_ENC_NONCE_SESSION_KEY, None)
    encrypted = data.pop("enc_password")
    password = decrypt_login_password(
        current_app.config["SECRET_KEY"],
        encrypted if isinstance(encrypted, str) else None,
        nonce,
    )
    if password is None:
        raise BadRequest("Could not read the encrypted password. Please retry.")
    # Werkzeug caches the parsed body and hands the same dict to every later
    # get_json()/request.json call, so this is what the view will see.
    data["password"] = password
