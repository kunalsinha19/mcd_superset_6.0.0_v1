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
"""revoked_session

Adds the table backing server-side session revocation on logout (audit
finding #1, "Response Replay") -- see superset/security/session_revocation.py.
Holds only opaque random session ids, never session contents.

Revision ID: a7c3e91b5d24
Revises: f6fe02b41508
Create Date: 2026-09-19 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7c3e91b5d24"
down_revision = "f6fe02b41508"


def upgrade():
    op.create_table(
        "revoked_session",
        sa.Column("sid", sa.String(64), primary_key=True),
        sa.Column("revoked_on", sa.DateTime(), nullable=False),
        sa.Column("expires_on", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_revoked_session_expires_on",
        "revoked_session",
        ["expires_on"],
    )


def downgrade():
    op.drop_index("ix_revoked_session_expires_on", table_name="revoked_session")
    op.drop_table("revoked_session")
