"""Tests for persistent shard-status message reuse and replacement."""

from __future__ import annotations

import pytest

from src.database import (
    get_shard_status_message_id,
    save_shard_status_message,
)


@pytest.mark.usefixtures("database")
async def test_shard_status_message_can_be_reused_and_replaced() -> None:
    """Verify that shard status message can be reused and replaced."""
    await save_shard_status_message(channel_id=123, message_id=456)
    assert await get_shard_status_message_id(123) == 456

    await save_shard_status_message(channel_id=123, message_id=789)
    assert await get_shard_status_message_id(123) == 789
    assert await get_shard_status_message_id(999) is None
