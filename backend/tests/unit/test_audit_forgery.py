"""Unit tests for audit hash-chain tamper detection.

These tests verify that direct database modifications (bypassing the audit
service) are caught by the chain integrity verification.
"""

import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.services.audit.audit_service import _compute_hash, verify_chain


def _make_entry(*, id=1, user_id=1, action="login", resource_type="session",
                resource_id="s1", prev_hash=None, entry_hash="good",
                created_at=None):
    """Build a plain-object mock of an AuditLog row."""
    class _Entry:
        pass
    e = _Entry()
    e.id = id
    e.user_id = user_id
    e.action = action
    e.resource_type = resource_type
    e.resource_id = resource_id
    e.prev_hash = prev_hash
    e.entry_hash = entry_hash
    e.created_at = created_at or datetime(2025, 1, 1, tzinfo=timezone.utc)
    return e


def _mock_db_with_entries(entries):
    """Return an AsyncMock db session that yields *entries* from execute()."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = entries
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result
    return mock_db


class TestAuditForgeryDetection:
    """Verify that tampered audit rows are caught by verify_chain."""

    def test_tampered_entry_hash_detected(self):
        """A row whose entry_hash was overwritten after creation is invalid."""
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        real_hash = _compute_hash("genesis", "login", "session", "s1",
                                  ts.isoformat(), "1")
        fake_hash = hashlib.sha256(b"tampered").hexdigest()

        entry = _make_entry(entry_hash=real_hash, created_at=ts)
        # Simulate an attacker overwriting the row's hash via direct SQL UPDATE
        entry.entry_hash = fake_hash

        mock_db = _mock_db_with_entries([entry])
        result = asyncio_run(verify_chain(mock_db))

        assert result["valid"] is False
        assert result["first_bad_entry_id"] == 1
        assert result["actual_hash"] == fake_hash
        assert result["expected_hash"] == real_hash

    def test_valid_chain_passes(self):
        """Unmodified chain entries pass verification."""
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        h1 = _compute_hash("genesis", "login", "session", "s1",
                           ts.isoformat(), "1")
        h2 = _compute_hash(h1, "logout", "session", "s1",
                           ts.isoformat(), "1")

        entries = [
            _make_entry(id=1, entry_hash=h1, created_at=ts),
            _make_entry(id=2, action="logout", entry_hash=h2, prev_hash=h1,
                        created_at=ts),
        ]

        mock_db = _mock_db_with_entries(entries)
        result = asyncio_run(verify_chain(mock_db))

        assert result["valid"] is True
        assert result["checked"] == 2
        assert result["first_bad_entry_id"] is None

    def test_tampered_action_detected(self):
        """Changing the action field invalidates the hash."""
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        real_hash = _compute_hash("genesis", "login", "session", "s1",
                                  ts.isoformat(), "1")

        entry = _make_entry(action="login", entry_hash=real_hash, created_at=ts)
        entry.action = "admin_transfer"  # attacker changed action in DB

        mock_db = _mock_db_with_entries([entry])
        result = asyncio_run(verify_chain(mock_db))

        assert result["valid"] is False
        assert result["first_bad_entry_id"] == 1

    def test_tampered_user_id_detected(self):
        """Changing the user_id field invalidates the hash."""
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        real_hash = _compute_hash("genesis", "login", "session", "s1",
                                  ts.isoformat(), "1")

        entry = _make_entry(user_id=1, entry_hash=real_hash, created_at=ts)
        entry.user_id = 999  # attacker escalated privileges

        mock_db = _mock_db_with_entries([entry])
        result = asyncio_run(verify_chain(mock_db))

        assert result["valid"] is False
        assert result["first_bad_entry_id"] == 1

    def test_tampered_resource_type_detected(self):
        """Changing the resource_type invalidates the hash."""
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        real_hash = _compute_hash("genesis", "login", "session", "s1",
                                  ts.isoformat(), "1")

        entry = _make_entry(entry_hash=real_hash, created_at=ts)
        entry.resource_type = "payment"  # attacker modified the row

        mock_db = _mock_db_with_entries([entry])
        result = asyncio_run(verify_chain(mock_db))

        assert result["valid"] is False
        assert result["first_bad_entry_id"] == 1

    def test_tampered_timestamp_detected(self):
        """Changing the created_at timestamp invalidates the hash."""
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        real_hash = _compute_hash("genesis", "login", "session", "s1",
                                  ts.isoformat(), "1")

        entry = _make_entry(entry_hash=real_hash, created_at=ts)
        # Attacker moved the entry to a different time
        entry.created_at = datetime(2025, 6, 15, tzinfo=timezone.utc)

        mock_db = _mock_db_with_entries([entry])
        result = asyncio_run(verify_chain(mock_db))

        assert result["valid"] is False
        assert result["first_bad_entry_id"] == 1

    def test_write_audit_then_detect_tamper(self):
        """End-to-end: write via service, tamper via 'SQL UPDATE', detect."""
        from app.services.audit.audit_service import write_audit

        fixed_ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        call_count = 0

        async def fake_execute(query):
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                r.scalar.return_value = None  # get_last_hash → genesis
            else:
                r.scalars.return_value.all.return_value = []
            return r

        mock_db = AsyncMock()
        mock_db.execute = fake_execute
        mock_db.add = lambda x: None

        entry = asyncio_run(write_audit(
            mock_db, user_id=1, action="login",
            resource_type="session", resource_id="s1",
        ))

        assert entry.entry_hash is not None
        assert entry.prev_hash is None

        # Tamper: overwrite entry_hash like a direct SQL UPDATE would
        entry.entry_hash = "0" * 64

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [entry]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = asyncio_run(verify_chain(mock_db))
        assert result["valid"] is False
        assert result["first_bad_entry_id"] == entry.id
        assert result["actual_hash"] == "0" * 64


def asyncio_run(coro):
    """Run an async coroutine synchronously for unit tests."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
