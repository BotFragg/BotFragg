"""Shared asynchronous database fixtures for the test suite."""

from __future__ import annotations

import pytest_asyncio
from tortoise import Tortoise


@pytest_asyncio.fixture
async def database():
    """Initialize the in-memory database for a test and close it afterward."""
    await Tortoise.init(
        db_url="sqlite://:memory:", modules={"models": ["src.models.entities"]}
    )
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise.close_connections()
