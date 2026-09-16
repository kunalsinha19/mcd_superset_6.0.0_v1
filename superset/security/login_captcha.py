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

This is a small, self-hosted, zero-external-dependency math challenge
instead -- works immediately, no API keys, no outbound call to a third
party on every login attempt. It's a floor against naive scripted
credential-stuffing (the actual heavy lifting against brute force is
finding #9's rate limiting, already in place); it is not meant to stop a
determined, custom-built solver.
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

captcha_blueprint = Blueprint("login_captcha", __name__)


@captcha_blueprint.route("/login/captcha", methods=["GET"])
def get_login_captcha():
    """Generates a new challenge, stores the answer server-side in the
    session (never sent to the client), returns only the question."""
    left, right = random.randint(1, 9), random.randint(1, 9)
    session[CAPTCHA_SESSION_KEY] = str(left + right)
    return jsonify({"question": f"{left} + {right}"})


class SupersetAuthDBView(AuthDBView):
    """Overrides FAB's login() to require the captcha answer before even
    checking credentials. Registered via SupersetSecurityManager.authdbview
    (see superset/security/manager.py) -- FAB instantiates whatever class
    is set there as the live /login/ view.

    The captcha-failure and wrong-password paths intentionally behave
    identically (same flash + redirect), so this doesn't introduce any UX
    inconsistency beyond what already existed for a wrong password."""

    @expose("/login/", methods=["GET", "POST"])
    @no_cache
    def login(self):
        if g.user is not None and g.user.is_authenticated:
            return redirect(self.appbuilder.get_url_for_index)

        form = LoginForm_db()
        if form.validate_on_submit():
            next_url = get_safe_redirect(request.args.get("next", ""))

            expected_answer = session.pop(CAPTCHA_SESSION_KEY, None)
            submitted_answer = (request.form.get("captcha_answer") or "").strip()
            if not expected_answer or submitted_answer != expected_answer:
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
