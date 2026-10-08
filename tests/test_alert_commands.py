"""Behavior and regression checks for alert commands."""

from __future__ import annotations

from src.cogs.valorant.alerts import AlertsCog


def test_alert_keeps_qotix_direct_skin_input() -> None:
    """Verify that alert keeps Qotix direct skin input."""
    command = AlertsCog.alert
    assert [parameter.name for parameter in command.parameters] == ["skin"]
