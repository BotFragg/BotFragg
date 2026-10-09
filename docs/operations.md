# Operating and recovering BotFragg

## Health evidence

The task cog writes a credential-free JSON heartbeat to
`<system temporary directory>/botfragg-health.json` every 30 seconds. In the
container this is `/tmp/botfragg-health.json`. It reports Discord readiness,
a database `SELECT 1`, and every enabled background loop. Each job includes its
last successful completion, last failure, cumulative failure count, elapsed
seconds for its latest attempt, running state, and overdue state. Cancelled
attempts do not count as successful. Disabled log delivery and shard-status
jobs are omitted.

```sh
docker compose ps
docker compose exec bot python -m src.health
docker compose exec bot cat /tmp/botfragg-health.json
docker compose logs --since=30m bot
```

The probe exits nonzero if the file is absent, malformed, unhealthy, or more
than 120 seconds old. Docker probes every 30 seconds, allows 120 seconds for
startup, and marks the container unhealthy after three failed probes. Docker's
`restart: unless-stopped` restarts an exited process; an unhealthy process
requires operator action. Configure your existing infrastructure to notify on
that state. A blocked event loop or stopped watchdog also makes the heartbeat
stale.

Refresh jobs must complete within their configured interval plus five minutes.
Enabled log and shard-status jobs get the same five-minute allowance. A daily
job that has never run is allowed until its first scheduled UTC run plus
`DAILY_ALERT_HEALTH_GRACE_SECONDS` (default two hours, minimum 60 seconds).
After a successful daily run, its next completion must arrive within 24 hours
plus that allowance. Set the daily allowance above measured full-run duration,
including per-account delays and upstream waits. Failures make a job unhealthy
until a subsequent successful attempt. Temporary HTTP/database failures use the
bounded retries described below.

Daily runs report `expired_logins`, `shop_failures`, and `delivery_failures`
separately; `failures` is their sum. A failed shop lookup or notification delivery
makes the daily job unhealthy even if other accounts succeed. Expired credentials
alone do not: those users receive a re-login notice. An unsuccessful notice counts
as a delivery failure. Recoverable per-account failures do not stop the loop or
re-send the day's successful notifications; health recovers after a clean daily
run. Check Discord DM permissions as well as upstream availability when investigating.

Daily lookups get at most three attempts: rate limits wait for the HTTP client's
bounded host cooldown, and transient database errors wait five seconds between
attempts. Only the failed lookup is retried; delivered notifications are not
replayed. Exhausted database retries skip the affected user's remaining accounts
while other users continue. An exhausted initial database lookup ends the run.
Both cases mark the job unhealthy and leave recovery to the next scheduled run.
Unreadable encrypted credentials count as a shop failure for that account and
remain stored for recovery with the matching key. Incomplete skin catalogs also
count as shop failures and are not cached as complete daily shops.

Returned refresh credentials stay encrypted in memory until their database save
succeeds; a later lookup retries that save before exchanging the refresh token
again. Shard-status updates similarly retain a posted message ID until it is saved.
Suggestion posts retain their message IDs and retry failed database saves every
30 seconds without reposting. Deleted suggestions are discarded, and reviews
completed during an outage are applied to the post when its link is saved.
Restarting loses pending state; unloading a notification cog also loses its
pending IDs. This can require a new login, leave a duplicate status message, or
leave an unlinked suggestion post. Incomplete Night Market catalogs
leave the daily shop usable, report Night Market as unavailable, and are not cached.

Command analytics, suggestion writes, and personal-data deletion coordinate
within one bot process. Commands active during a successful deletion cannot
recreate their analytics, suggestions, or follows. Multiple bot processes require
shared deletion coordination.

Structured logs include background-job durations, daily run counts, failures,
and health-state transitions. The existing privacy filter applies to these
logs and optional GlitchTip telemetry. Frequent log/shard completion messages
are omitted to avoid feeding log delivery its own logs; their evidence remains
in the heartbeat. Job history is process-local and resets on restart.

## Responding to an unhealthy process

1. Inspect the heartbeat's `problems` and structured logs. For `database`,
   check reachability and database health. For `discord`, check connectivity and
   Discord's service status. A failed catalog/version job usually indicates an
   upstream outage; check whether its next retry succeeds.
2. A stopped loop, stale heartbeat, or repeated unexpected exception requires
   investigation. Save relevant scrubbed logs and the image tag before restarting
   with `docker compose restart bot`. Check that readiness and job success return.
3. Do not run migrations repeatedly to fix connectivity or change the encryption
   key to fix credential errors. Those changes do not repair an outage.
4. If a release introduced the problem, use the preceding known-good image with
   a compatible schema. If schema compatibility is uncertain, recover into a
   separate database first. Keep the original database and backup intact.

## Backup and restore

Back up the PostgreSQL database **and its matching `TOKEN_ENCRYPTION_KEY`**.
The database contains Fernet ciphertext, but the key is stored separately.
Losing or replacing the key makes existing Riot credentials unusable. Store the
key in your secret manager and the dump in protected, encrypted storage; the
dump also contains personal records that are not Fernet-encrypted. Record the
application image tag, PostgreSQL version, migration history, backup time,
and key version with the backup. Verify backups by restoring them periodically.
Choose backup cadence and retention with the operator; this change introduces
no automated retention or deletion policy.

The following examples use libpq service profiles and a protected password
file, so credentials do not appear in shell history or process arguments.
Configure `botfragg-backup` for the source database and `botfragg-restore` for a
new, empty database on an isolated recovery server. Use PostgreSQL client tools
compatible with the server version.

```sh
pg_dump --dbname="service=botfragg-backup" --format=custom --file=botfragg.dump
pg_restore --list botfragg.dump
pg_restore --dbname="service=botfragg-restore" --no-owner --exit-on-error botfragg.dump
```

Restore into an empty database; do not pass `--clean` against the running
database. Stop application writers before switching databases. Use a checkout
of the release associated with the backup for verification.

Set `BOTFRAGG_RESTORE_DATABASE_URL` explicitly to the restored clone and load
the original `TOKEN_ENCRYPTION_KEY` from your secret manager into the process
environment, then run:

```sh
uv run --frozen python tools/verify_restore.py
```

This tool uses a read-only, repeatable-read transaction. It checks all seven
model-table counts, requires migration history to match the checked-out release,
and decrypts every stored credential blob without printing credentials or
identifiers. Compare the counts with backup-time evidence. It fails if the key
is wrong or any credential blob cannot be decrypted. It makes no Riot or Discord
requests. If the backup contains no encrypted accounts, the tool cannot prove
that the supplied key is the original key; verify the secret-manager version.

After successful offline verification, perform an approved staging startup
with staging Discord credentials. Confirm readiness, migrations, and job health
before switching production. A restored historical backup can reintroduce
records deleted after that backup: reconcile deletion requests before reopening
the service, following the privacy policy.

The 2026-10-07 disposable PostgreSQL 17 rehearsal restored one record of each
model using `pg_dump -Fc` and `pg_restore --exit-on-error`. All counts, four
migrations, and selected-account state survived. The matching Fernet key
decrypted the restored credentials; another key was rejected. The read-only
verification tool passed against that restored database. The rehearsal's
databases and dump were removed afterward.

## Performance baseline

Run the synthetic benchmark against an explicitly configured disposable
`BOTFRAGG_TEST_POSTGRES_URL`:

```sh
uv run --frozen python tools/benchmark_database.py --users=1000 --invocations=100000 --repeats=5
```

The tool creates and removes only its generated schema. It uses real database
queries, two accounts per user, four matching skin alerts per account,
concurrency 10, and fixed synthetic shops. Notification delivery is forbidden
by the dry-run callbacks. Upstream latency, Discord delivery, and configured
per-account delay are excluded. These are database/orchestration measurements,
not end-to-end production estimates. Peak memory measures Python allocations
in a separate traced run.

PostgreSQL 17 on local Docker, Python 3.14 on Windows, 2026-10-07:

| Workload | Median | Maximum of five runs | Queries |
| --- | ---: | ---: | ---: |
| Daily alerts: 1,000 users / 2,000 accounts / 8,000 alerts | 2,938 ms | 3,176 ms | 4,004 |
| User analytics: 100,000 invocation rows | 10.0 ms | 12.1 ms | 1 |
| Guild analytics: 100,000 invocation rows | 9.8 ms | 10.4 ms | 1 |

The alert run peaked at 3.21 MiB of traced Python allocations. Analytics plans
used sequential scans; server execution took about 4.1–4.5 ms with warm buffers.
Repeat at expected deployment scale before adding indexes or changing batching.
Eligible accounts are currently materialized and ownership is rechecked per
account. Page users if measured memory becomes a problem; add scope indexes if
analytics latency becomes a problem. Preserve those ownership rechecks when
optimizing. No retention policy or query behavior was changed for this baseline.
