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
"""Audit finding #11, "Login Form Not Protected" (no CAPTCHA).

`RECAPTCHA_PUBLIC_KEY`/`RECAPTCHA_PRIVATE_KEY` already exist in
superset_config.py.example but were never wired to anything -- FAB's DB
login view has no CAPTCHA hook at all, and flask_wtf.recaptcha.RecaptchaField
needs real Google/hCaptcha API keys this deployment doesn't have; wiring it
up now would just be a no-op until someone provisions those externally.

This is a small, self-hosted, zero-external-dependency challenge instead --
works immediately, no API keys, no outbound call to a third party on every
login attempt. It's a floor against naive scripted credential-stuffing (the
actual heavy lifting against brute force is finding #9's rate limiting,
already in place); it is not meant to stop a determined, custom-built
solver that actually parses the response and echoes the code back.

Alphanumeric per the audit team's explicit follow-up instruction, not a
2-digit arithmetic sum -- the original math version only had ~17 possible
answers (sums of 1-9 + 1-9), so a bot could have a real per-attempt hit
rate just by guessing blind, without ever reading the question. A random
code drawn from a 32-character alphabet at length 6 has 32**6 (~1 billion)
possibilities, which makes blind guessing infeasible while keeping the
same zero-dependency, no-image design.
"""
from __future__ import annotations

import random

from flask import Blueprint, flash, g, jsonify, redirect, request, session
from flask_appbuilder._compat import as_unicode
from flask_appbuilder.security.decorators import no_cache
from flask_appbuilder.security.forms import LoginForm_db
from flask_appbuilder.security.views import AuthDBView
from flask_appbuilder.utils.base import get_safe_redirect
from flask_appbuilder.views import expose
from flask_login import login_user

CAPTCHA_SESSION_KEY = "login_captcha_answer"  # noqa: S105 -- not a credential

# Excludes 0/O/1/I/L -- easy to mistype/misread as plain text, no image
# rendering to disambiguate them with a font.
CAPTCHA_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CAPTCHA_LENGTH = 6

captcha_blueprint = Blueprint("login_captcha", __name__)


def _generate_captcha_code() -> str:
    return "".join(random.choices(CAPTCHA_ALPHABET, k=CAPTCHA_LENGTH))


def _captcha_matches(expected: str | None, submitted: str) -> bool:
    return bool(expected) and submitted.strip().upper() == expected


@captcha_blueprint.route("/login/captcha", methods=["GET"])
def get_login_captcha():
    """Generates a new alphanumeric code, stores it server-side in the
    session, and returns the same code to be re-typed. (Read/parse this
    endpoint yourself and answering correctly is trivial by design -- the
    point is only to stop attempts that skip the challenge entirely.)"""
    code = _generate_captcha_code()
    session[CAPTCHA_SESSION_KEY] = code
    return jsonify({"code": code})


class SupersetAuthDBView(AuthDBView):
    """Overrides FAB's login() to require the captcha answer before even
    checking credentials. Registered via SupersetSecurityManager.authdbview
    (see superset/security/manager.py) -- FAB instantiates whatever class
    is set there as the live /login/ view.

    The captcha-failure and wrong-password paths intentionally behave
    identically (same message), so this doesn't introduce any UX
    inconsistency beyond what already existed for a wrong password.

    The React login page (src/pages/Login/index.tsx) submits here as a
    fetch() with a JSON body rather than a browser form-navigation POST --
    that's what lets it catch a failed/locked-out attempt in place and
    freeze+countdown the password field, instead of the whole page
    reloading to a raw error. That branch (_login_json) returns JSON with
    a real status code (401 on bad creds/captcha, 429 forwarded untouched
    by Flask-Limiter's own decorator on this blueprint -- see
    AUTH_RATE_LIMIT/AUTH_RATE_LIMITED in superset_config.py.example) instead
    of the flash+redirect the classic form path below uses. Both paths
    share the same Flask-Limiter-enforced attempt limit; the JSON path just
    surfaces it more usefully than a page navigation to a JSON error body
    could.
    """

    @expose("/login/", methods=["GET", "POST"])
    @no_cache
    def login(self):
        if g.user is not None and g.user.is_authenticated:
            return redirect(self.appbuilder.get_url_for_index)

        if request.method == "POST" and request.is_json:
            return self._login_json()

        form = LoginForm_db()
        if form.validate_on_submit():
            next_url = get_safe_redirect(request.args.get("next", ""))

            expected_answer = session.pop(CAPTCHA_SESSION_KEY, None)
            submitted_answer = request.form.get("captcha_answer") or ""
            if not _captcha_matches(expected_answer, submitted_answer):
                flash(
                    as_unicode(
                        "Incorrect security check answer. Please try again."
                    ),
                    "warning",
                )
                return redirect(self.appbuilder.get_url_for_login_with(next_url))

            user = self.appbuilder.sm.auth_user_db(
                form.username.data, form.password.data
            )
            if not user:
                flash(as_unicode(self.invalid_login_message), "warning")
                return redirect(self.appbuilder.get_url_for_login_with(next_url))
            login_user(user, remember=False)
            return redirect(next_url)
        return self.render_template(
            self.login_template, title=self.title, form=form, appbuilder=self.appbuilder
        )

    def _login_json(self):
        """JSON counterpart of login() above -- same checks, same order,
        same Flask-Limiter attempt limit (enforced by the decorator FAB
        applies to this whole blueprint), just returning a response the
        React login page can act on without a page navigation."""
        payload = request.get_json(silent=True) or {}
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        submitted_answer = payload.get("captcha_answer") or ""
        next_url = get_safe_redirect(request.args.get("next", ""))

        expected_answer = session.pop(CAPTCHA_SESSION_KEY, None)
        if not _captcha_matches(expected_answer, submitted_answer):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": as_unicode(
                            "Incorrect security check answer. Please try again."
                        ),
                    }
                ),
                401,
            )

        user = self.appbuilder.sm.auth_user_db(username, password)
        if not user:
            return (
                jsonify(
                    {"success": False, "message": as_unicode(self.invalid_login_message)}
                ),
                401,
            )

        login_user(user, remember=False)
        return jsonify({"success": True, "redirect": next_url})
