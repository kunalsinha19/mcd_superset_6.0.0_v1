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
"""Password-reuse prevention (audit finding #8, "Password History Not
Maintained") and shared input-length limits (audit finding #10, "Buffer
overflow / missing length validation").

Three separate code paths in this codebase set a user's password --
self-service (superset/views/users/api.py), admin-sets-another-user's
(flask_appbuilder's UserApi, subclassed as SupersetUserApi below), and the
`flask fab reset-password` CLI / SecurityManager.reset_password(). All three
are hooked to call through here rather than duplicating this logic three
times.

Only password *hashes* are ever stored in history, never plaintext -- reuse
is checked by re-hashing the candidate password with the same scheme
(werkzeug's check_password_hash) against each stored hash.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask_appbuilder import Model
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Session
from werkzeug.exceptions import BadRequest
from werkzeug.security import check_password_hash

logger = logging.getLogger(__name__)

# Matches the audit's own recommendation: "Password history should ideally
# be 3" -- i.e. a user can't reuse their current password or either of
# their previous 2.
PASSWORD_HISTORY_SIZE = 3

# Matches the audit's "Buffer overflow" finding -- really a request for
# length limits on input fields. These are generous upper bounds (not UX
# guidance) meant to reject abusive payloads, not to second-guess a real
# password manager's output.
USERNAME_MAX_LENGTH = 64
NAME_MAX_LENGTH = 64
EMAIL_MAX_LENGTH = 254  # RFC 5321 mailbox length limit
PASSWORD_MAX_LENGTH = 128


class PasswordReuseError(BadRequest):
    """Raised when a candidate password matches the user's current password
    or one of their last PASSWORD_HISTORY_SIZE - 1 previous passwords.

    Subclasses werkzeug's BadRequest (not ValueError) so it's caught for
    free by flask_appbuilder's @safe decorator -- which only maps
    BadRequest to a 400 response, anything else becomes a 500."""


class InputTooLongError(BadRequest):
    """Raised when a field exceeds its configured max length. See
    PasswordReuseError docstring for why this subclasses BadRequest."""


class UserPasswordHistory(Model):
    """Retired password hashes for reuse-prevention. Never holds plaintext."""

    __tablename__ = "user_password_history"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("ab_user.id", ondelete="CASCADE"), nullable=False
    )
    password_hash = Column(String(255), nullable=False)
    created_on = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


def assert_password_not_reused(
    db_session: Session, user_id: int, current_password_hash: str | None, new_plain_password: str
) -> None:
    """Raise PasswordReuseError if new_plain_password matches the user's
    current password hash or any of their recent retired ones.

    Call this BEFORE overwriting the user's password hash.
    """
    hashes_to_check = []
    if current_password_hash:
        hashes_to_check.append(current_password_hash)

    history_rows = (
        db_session.query(UserPasswordHistory)
        .filter(UserPasswordHistory.user_id == user_id)
        .order_by(UserPasswordHistory.created_on.desc())
        .limit(PASSWORD_HISTORY_SIZE - 1)
        .all()
    )
    hashes_to_check.extend(row.password_hash for row in history_rows)

    for old_hash in hashes_to_check:
        try:
            matches = check_password_hash(old_hash, new_plain_password)
        except Exception:  # pylint: disable=broad-except
            # A stored hash in an algorithm werkzeug can't parse shouldn't
            # crash the password-change flow -- log and treat as no-match.
            logger.warning(
                "Could not compare candidate password against a stored "
                "password-history hash for user_id=%s; skipping that entry.",
                user_id,
            )
            continue
        if matches:
            raise PasswordReuseError(
                f"This password was used recently. Choose a password you "
                f"haven't used in your last {PASSWORD_HISTORY_SIZE} passwords."
            )


def record_password_history(
    db_session: Session, user_id: int, retired_password_hash: str | None
) -> None:
    """Archive the password hash that's about to stop being current, and
    trim history down to PASSWORD_HISTORY_SIZE - 1 rows.

    Call this AFTER the user's password has been overwritten with the new
    hash, passing the *old* hash (the one just replaced).
    """
    if not retired_password_hash:
        return

    db_session.add(
        UserPasswordHistory(user_id=user_id, password_hash=retired_password_hash)
    )
    db_session.flush()

    stale_rows = (
        db_session.query(UserPasswordHistory)
        .filter(UserPasswordHistory.user_id == user_id)
        .order_by(UserPasswordHistory.created_on.desc())
        .offset(PASSWORD_HISTORY_SIZE - 1)
        .all()
    )
    for row in stale_rows:
        db_session.delete(row)


def assert_length_ok(value: str | None, max_length: int, field_name: str) -> None:
    """Raise InputTooLongError if value exceeds max_length.

    Server-side enforcement -- the actual security-relevant half of
    finding #10 (client-side maxlength is UX only, trivially bypassed by
    anyone not using the browser form)."""
    if value and len(value) > max_length:
        raise InputTooLongError(
            f"{field_name} must be {max_length} characters or fewer."
        )
