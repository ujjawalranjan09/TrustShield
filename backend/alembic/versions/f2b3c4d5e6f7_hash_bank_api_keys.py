"""hash bank api keys and rename column

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-19 21:00:00.000000

Migrates plaintext api_key column to api_key_hash (SHA-256).
Existing plaintext keys are hashed in-place. Existing banks must
re-register or be issued new keys after this migration.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import hashlib


revision: str = "f2b3c4d5e6f7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the new hashed column
    op.add_column("intel_banks", sa.Column("api_key_hash", sa.String(64), nullable=True))

    conn = op.get_bind()

    # Hash existing plaintext keys in-place
    result = conn.execute(sa.text("SELECT id, api_key FROM intel_banks"))
    for row in result:
        if row.api_key:
            hashed = hashlib.sha256(row.api_key.encode()).hexdigest()
            conn.execute(
                sa.text("UPDATE intel_banks SET api_key_hash = :h WHERE id = :id"),
                {"h": hashed, "id": row.id},
            )

    # SQLite-compatible: recreate table to make NOT NULL and add unique constraint
    dialect = conn.dialect.name
    if dialect == "sqlite":
        # Get existing table info
        meta = sa.MetaData()
        meta.reflect(bind=conn)
        old_table = sa.Table("intel_banks", meta, autoload_with=conn)

        # Build new column list excluding api_key, with api_key_hash NOT NULL
        new_columns = []
        for col in old_table.columns:
            if col.name == "api_key":
                continue
            elif col.name == "api_key_hash":
                new_columns.append(sa.Column("api_key_hash", sa.String(64), nullable=False))
            else:
                new_columns.append(col)

        # Create new table
        new_table = sa.Table("intel_banks_new", meta, *new_columns, sa.UniqueConstraint("api_key_hash", name="uq_intel_banks_api_key_hash"))
        new_table.create(bind=conn)

        # Copy data
        col_names = [c.name for c in new_columns]
        conn.execute(sa.text(f"INSERT INTO intel_banks_new ({', '.join(col_names)}) SELECT {', '.join(col_names)} FROM intel_banks"))

        # Drop old, rename new
        conn.execute(sa.text("DROP TABLE intel_banks"))
        conn.execute(sa.text("ALTER TABLE intel_banks_new RENAME TO intel_banks"))
    else:
        # Make the new column NOT NULL and unique
        op.alter_column("intel_banks", "api_key_hash", nullable=False)
        op.create_unique_constraint("uq_intel_banks_api_key_hash", "intel_banks", ["api_key_hash"])
        # Drop the old plaintext column
        op.drop_column("intel_banks", "api_key")


def downgrade() -> None:
    # Cannot reverse: plaintext keys are gone. Re-create as empty column.
    op.add_column("intel_banks", sa.Column("api_key", sa.String(100), nullable=True))
    op.drop_column("intel_banks", "api_key_hash")
