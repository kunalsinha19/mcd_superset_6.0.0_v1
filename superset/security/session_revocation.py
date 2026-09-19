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
"""Server-side session revocation (audit finding #1, "Response Replay").

Root cause this closes: Flask's default session is a signed *client-side*
cookie. Nothing is stored server-side, so "logout" can only ask the browser
to drop its copy -- a copy someone already captured (e.g. the Set-Cookie in a
recorded login response, as in the Burp PoC) keeps verifying against
SECRET_KEY until it expires (Flask's default lifetime is 31 days), logout or
not. Re-injecting that old response restores a fully authenticated session.

Fix: every login stamps a random session id (`sid`) into the session, and
every logout records that sid in a small revocation table. The Flask-Login
user loader refuses any session whose sid has been revoked, so a captured
cookie dies the moment its owner logs out. Only revoked ids are stored
(rows are purged once the cookie they belong to has expired anyway), so the
table stays tiny and each request costs one primary-key lookup.

Sessions issued before this shipped carry no sid and stay valid until they
expire naturally -- deliberately, so deploying it doesn't log everyone out.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from flask_appbuilder import Model
from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SESSION_SID_KEY = "sid"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RevokedSession(Model):
    """A session id that has been logged out. Never holds session contents."""

    __tablename__ = "revoked_session"

    sid = Column(String(64), primary_key=True)
    revoked_on = Column(DateTime, nullable=False, default=_utcnow)
    expires_on = Column(DateTime, nullable=False, index=True)


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def revoke_session(db_session: Session, sid: str, lifetime: timedelta) -> None:
    """Record `sid` as logged out for as long as a cookie carrying it could
    still be accepted (`lifetime` = the app's permanent_session_lifetime)."""
    try:
        now = _utcnow()
        db_session.query(RevokedSession).filter(
            RevokedSession.expires_on < now
        ).delete(synchronize_session=False)
        if db_session.get(RevokedSession, sid) is None:
            db_session.add(
                RevokedSession(sid=sid, revoked_on=now, expires_on=now + lifetime)
            )
        db_session.commit()
    except Exception:  # pylint: disable=broad-except
        db_session.rollback()
        # Loud on purpose: if this fails, the logout did not invalidate the
        # cookie server-side.
        logger.exception("Failed to record session revocation on logout")


def is_session_revoked(db_session: Session, sid: str) -> bool:
    """True if `sid` was logged out.

    Fails open (returns False) only if the lookup itself errors -- e.g. the
    migration creating this table hasn't run yet. Failing closed there would
    lock every user out of the whole app over an ops slip; a real database
    outage breaks loading the user right after this anyway.
    """
    try:
        return (
            db_session.query(RevokedSession.sid)
            .filter(RevokedSession.sid == sid)
            .first()
            is not None
        )
    except Exception:  # pylint: disable=broad-except
        db_session.rollback()
        logger.exception(
            "Session revocation lookup failed; treating session as not revoked"
        )
        return False
