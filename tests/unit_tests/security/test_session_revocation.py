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
"""Session revocation store (audit #1), against an in-memory SQLite DB."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from superset.security.session_revocation import (
    is_session_revoked,
    new_session_id,
    revoke_session,
    RevokedSession,
)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://")
    RevokedSession.__table__.create(engine)
    with Session(engine) as session:
        yield session


def test_new_session_ids_are_unique_and_fit_the_column() -> None:
    ids = {new_session_id() for _ in range(200)}
    assert len(ids) == 200
    assert all(len(i) <= 64 for i in ids)


def test_unknown_id_is_not_revoked(db: Session) -> None:
    assert is_session_revoked(db, "never-seen") is False


def test_revoked_id_is_reported_revoked_and_others_are_not(db: Session) -> None:
    revoke_session(db, "sid-a", timedelta(days=31))
    assert is_session_revoked(db, "sid-a") is True
    assert is_session_revoked(db, "sid-b") is False


def test_revoking_twice_is_harmless(db: Session) -> None:
    revoke_session(db, "sid-a", timedelta(days=31))
    revoke_session(db, "sid-a", timedelta(days=31))
    assert db.query(RevokedSession).count() == 1


def test_expired_rows_are_purged_on_the_next_revocation(db: Session) -> None:
    db.add(
        RevokedSession(
            sid="old",
            revoked_on=datetime(2020, 1, 1),
            expires_on=datetime(2020, 2, 1),
        )
    )
    db.commit()
    revoke_session(db, "new", timedelta(days=31))
    assert is_session_revoked(db, "old") is False
    assert is_session_revoked(db, "new") is True


def test_lookup_fails_open_and_recovers_when_the_table_is_missing() -> None:
    # e.g. the migration hasn't run yet: must not lock everyone out.
    with Session(create_engine("sqlite://")) as broken:
        assert is_session_revoked(broken, "anything") is False
        # the failed lookup rolled back, so the session is still usable
        RevokedSession.__table__.create(broken.get_bind())
        revoke_session(broken, "x", timedelta(days=1))
        assert is_session_revoked(broken, "x") is True


def test_failed_revoke_does_not_raise() -> None:
    with Session(create_engine("sqlite://")) as broken:
        revoke_session(broken, "x", timedelta(days=1))  # table missing
