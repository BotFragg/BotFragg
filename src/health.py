"""Background-job evidence and a local, credential-free container health check."""

from __future__ import annotations

import json
import logging
import math
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

# ponytail: one bot per container; use per-instance paths if processes are co-located.
HEALTH_PATH = Path(tempfile.gettempdir()) / "botfragg-health.json"
HEALTH_STALE_SECONDS = 120
log = logging.getLogger(__name__)


@dataclass(slots=True)
class JobHealth:
    """Track actual completion, failures, and elapsed time for one scheduled job."""

    max_age_seconds: float
    first_deadline: float = field(default_factory=lambda: time.time() + 300)
    last_success: float | None = None
    last_failure: float | None = None
    failures: int = 0
    duration_seconds: float | None = None

    def failure(self, name: str) -> None:
        """Record a failure, including one handled inside a job's retry logic."""
        self.last_failure = time.time()
        self.failures += 1
        log.warning(
            "Background job failed", extra={"job": name, "failures": self.failures}
        )

    @contextmanager
    def track(self, name: str) -> Iterator[None]:
        """Measure one attempt; exceptions and cancellation never count as success."""
        started = time.monotonic()
        failures = self.failures
        try:
            yield
        except Exception:
            self.failure(name)
            raise
        else:
            if self.failures == failures:
                self.last_success = time.time()
                # Avoid feeding the log-delivery job its own completion message.
                if name not in {"log_flush", "shard_status"}:
                    log.info(
                        "Background job completed",
                        extra={
                            "job": name,
                            "duration_seconds": time.monotonic() - started,
                        },
                    )
        finally:
            self.duration_seconds = time.monotonic() - started

    def snapshot(self, *, running: bool, failed: bool, now: float) -> dict[str, object]:
        """Report stopped, failed, or overdue work without exposing user data."""
        deadline = (
            self.last_success + self.max_age_seconds
            if self.last_success is not None
            else self.first_deadline
        )
        recent_failure = self.last_failure is not None and (
            self.last_success is None or self.last_failure > self.last_success
        )
        return {
            "healthy": running
            and not failed
            and not recent_failure
            and now <= deadline,
            "running": running,
            "failed": failed,
            "overdue": now > deadline,
            "last_success": self.last_success,
            "last_failure": self.last_failure,
            "failures": self.failures,
            "duration_seconds": self.duration_seconds,
        }


def write_health(snapshot: dict[str, object], path: Path = HEALTH_PATH) -> None:
    """Replace the status file atomically so probes never read partial JSON."""
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as output:
        temporary = Path(output.name)
        try:
            json.dump(snapshot, output)
            output.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def healthcheck(path: Path = HEALTH_PATH) -> bool:
    """Require a fresh successful heartbeat; malformed or missing files fail closed."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        checked_at = data.get("checked_at")
        return (
            data.get("healthy") is True
            and isinstance(checked_at, (int, float))
            and not isinstance(checked_at, bool)
            and math.isfinite(checked_at)
            and 0 <= time.time() - checked_at <= HEALTH_STALE_SECONDS
        )
    except OSError, ValueError, TypeError, AttributeError, OverflowError:
        return False


if __name__ == "__main__":
    raise SystemExit(0 if healthcheck() else 1)
