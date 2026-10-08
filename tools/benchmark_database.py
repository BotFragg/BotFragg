"""Measure synthetic alert and analytics workloads in a disposable PostgreSQL schema."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
from tortoise import Tortoise, connections

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models import Account, Alert, User
from src.services.alerts import run_daily_alerts
from src.services.analytics import command_stats
from src.services.catalog import Skin
from src.services.shop import Offer, ShopData


async def benchmark(users: int, invocations: int, repeats: int) -> dict:
    """Seed an isolated schema, measure real database queries, and always remove it."""
    url = os.environ["BOTFRAGG_TEST_POSTGRES_URL"]
    schema = "botfragg_benchmark_" + uuid4().hex
    admin = await asyncpg.connect(url)
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        parsed = urlsplit(url)
        query = dict(parse_qsl(parsed.query), schema=schema)
        await Tortoise.init(
            db_url=urlunsplit(parsed._replace(query=urlencode(query))),
            modules={"models": ["src.models.entities"]},
        )
        await Tortoise.generate_schemas()
        await User.bulk_create(
            [
                User(
                    id=i, current_account_id=f"synthetic-{i}-0", daily_shop_enabled=True
                )
                for i in range(1, users + 1)
            ]
        )
        accounts = [
            Account(puuid=f"synthetic-{i}-{j}", user_id=i, username="Synthetic#TEST")
            for i in range(1, users + 1)
            for j in range(2)
        ]
        await Account.bulk_create(accounts)
        skins = [
            Skin(str(uuid4()), str(uuid4()), "Synthetic", None, None) for _ in range(4)
        ]
        await Alert.bulk_create(
            [
                Alert(account_id=account.puuid, skin_uuid=skin.uuid)
                for account in accounts
                for skin in skins
            ]
        )
        await admin.execute(f'SET search_path TO "{schema}"')
        await admin.execute(
            "INSERT INTO commandinvocation(command,user_id,guild_id,channel_id,created_at) "
            "SELECT 'synthetic-' || (i % 7), (i % $1::int) + 1, (i % 100) + 1, NULL, NOW() "
            "FROM generate_series(0, $2::int - 1) AS i",
            users,
            invocations,
        )
        await admin.execute("ANALYZE")
        shop_data = ShopData(
            [Offer(skin, 1000, 4000000000) for skin in skins], [], [], 4000000000, None
        )

        class SyntheticShop:
            """Supply fixed shops without contacting Riot or delivering Discord messages."""

            async def storefront(self, account, *, use_cache):
                await asyncio.sleep(0)
                return shop_data

        async def never_send(*args):
            raise AssertionError("Dry-run benchmark attempted delivery")

        connection = connections.get("default")
        queries = [0]
        for name in ("execute_query", "execute_query_dict"):
            original = getattr(connection, name)

            async def counted(*args, _original=original, **kwargs):
                queries[0] += 1
                return await _original(*args, **kwargs)

            setattr(connection, name, counted)

        async def alerts():
            summary = await run_daily_alerts(
                SyntheticShop(),
                alert_concurrency=10,
                delay_between_alerts_seconds=0,
                dry_run=True,
                on_shop=never_send,
                on_credentials_expired=never_send,
            )
            if summary != {
                "users": users,
                "shops": users * 2,
                "alerts": users * 8,
                "failures": 0,
                "expired_logins": 0,
                "shop_failures": 0,
                "delivery_failures": 0,
            }:
                raise AssertionError(f"Incorrect alert result: {summary}")

        results = {
            "users": users,
            "accounts": users * 2,
            "alerts": users * 8,
            "invocations": invocations,
            "repeats": repeats,
        }
        for name, work in (
            ("daily_alerts", alerts),
            ("user_analytics", lambda: command_stats(user_id=1)),
            ("guild_analytics", lambda: command_stats(guild_id=1)),
        ):
            durations, query_counts = [], []
            for _ in range(repeats):
                queries[0] = 0
                started = time.perf_counter()
                result = await work()
                durations.append((time.perf_counter() - started) * 1000)
                query_counts.append(queries[0])
                divisor = users if name == "user_analytics" else 100
                if (
                    name != "daily_alerts"
                    and result[0] != (invocations + divisor - 1) // divisor
                ):
                    raise AssertionError("Incorrect analytics count")
            results[name] = {
                "median_ms": round(statistics.median(durations), 3),
                "max_ms": round(max(durations), 3),
                "queries": max(query_counts),
            }
        tracemalloc.start()
        await alerts()
        results["daily_alerts"]["peak_python_mib"] = round(
            tracemalloc.get_traced_memory()[1] / 1024**2, 3
        )
        tracemalloc.stop()
        for scope in ("user_id", "guild_id"):
            plan = json.loads(
                await admin.fetchval(
                    # The column comes only from the fixed tuple above, never input.
                    f'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT command, COUNT(id) FROM commandinvocation WHERE "{scope}" = 1 GROUP BY command'  # noqa: S608
                )
            )[0]
            results[scope + "_plan"] = {
                "execution_ms": plan["Execution Time"],
                "plan": plan["Plan"],
            }
        return results
    finally:
        await Tortoise.close_connections()
        try:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await admin.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--invocations", type=int, default=100000)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if min(args.users, args.invocations, args.repeats) < 1:
        parser.error("Workload sizes and repeats must be positive")
    if not os.environ.get("BOTFRAGG_TEST_POSTGRES_URL"):
        parser.error(
            "Set BOTFRAGG_TEST_POSTGRES_URL to a disposable PostgreSQL database"
        )
    print(
        json.dumps(
            asyncio.run(benchmark(args.users, args.invocations, args.repeats)), indent=2
        )
    )
