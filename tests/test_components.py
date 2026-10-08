"""Behavior checks for components."""

from __future__ import annotations

from src.views import OwnedActionButton, OwnedSelect


def test_dynamic_component_ids_fit_discord_limit() -> None:
    """Verify that dynamic component IDs fit Discord limit."""
    owner_id = 12345678901234567890
    assert (
        len(
            OwnedSelect(
                "alert_create",
                owner_id,
                "12345678-1234-1234-1234-123456789012",
                empty_option_label="Unavailable",
            ).item.custom_id
        )
        <= 100
    )
    assert (
        len(
            OwnedSelect(
                "shop_variant",
                owner_id,
                "4000000000|12345678-1234-1234-1234-123456789012",
                empty_option_label="Unavailable",
            ).item.custom_id
        )
        <= 100
    )


def test_alert_removal_control_fits_a_persistent_dm() -> None:
    """Verify that alert removal control fits a persistent DM."""
    button = OwnedActionButton("remove_alert", 123456789012345678, "12345678")
    assert len(button.item.custom_id) <= 100
