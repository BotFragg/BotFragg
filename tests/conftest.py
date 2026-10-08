"""Shared asynchronous database fixtures for the test suite."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from tortoise import Tortoise
from tortoise.backends.base.executor import EXECUTOR_CACHE


@pytest.fixture(autouse=True)
def reset_database_query_cache():
    """Avoid cached SQLite SQL when the next test uses PostgreSQL, or vice versa."""
    # Tortoise keys this cache by connection name and table, without the dialect.
    EXECUTOR_CACHE.clear()
    yield
    EXECUTOR_CACHE.clear()


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


@asynccontextmanager
async def isolated_postgres():
    """Give each PostgreSQL test its own schema in the disposable test database."""
    url = os.getenv("BOTFRAGG_TEST_POSTGRES_URL")
    if not url:
        if os.getenv("BOTFRAGG_REQUIRE_POSTGRES") == "1":
            pytest.fail("CI requires BOTFRAGG_TEST_POSTGRES_URL")
        pytest.skip("Requires a disposable PostgreSQL database")
    schema = "botfragg_test_" + uuid4().hex
    admin = await asyncpg.connect(url)
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        parsed = urlsplit(url)
        query = dict(parse_qsl(parsed.query))
        query["schema"] = schema
        yield urlunsplit(parsed._replace(query=urlencode(query)))
    finally:
        await Tortoise.close_connections()
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.close()


@pytest_asyncio.fixture
async def postgres_url():
    """Provide an isolated schema for a PostgreSQL-only regression."""
    async with isolated_postgres() as url:
        yield url


@pytest_asyncio.fixture(params=["sqlite", "postgres"])
async def migration_url(request):
    """Run migration verification against both supported database engines."""
    if request.param == "sqlite":
        yield "sqlite://:memory:"
    else:
        async with isolated_postgres() as url:
            yield url
