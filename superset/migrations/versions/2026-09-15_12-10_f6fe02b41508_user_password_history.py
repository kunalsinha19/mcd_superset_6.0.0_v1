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
"""user_password_history

Adds the table backing password-reuse prevention (audit finding #8,
"Password History Not Maintained"). Stores only password *hashes* of
retired passwords, never plaintext -- see superset/security/password_policy.py
for how it's used.

Revision ID: f6fe02b41508
Revises: c233f5365c9e
Create Date: 2026-09-15 12:10:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f6fe02b41508"
down_revision = "c233f5365c9e"


def upgrade():
    op.create_table(
        "user_password_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_on", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["ab_user.id"],
            name="fk_user_password_history_user_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_user_password_history_user_id",
        "user_password_history",
        ["user_id"],
    )


def downgrade():
    op.drop_index("idx_user_password_history_user_id", table_name="user_password_history")
    op.drop_table("user_password_history")
