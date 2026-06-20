"""Blink(1) Status Light integration setup."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .transport import open_blink1_transport

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["light"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Blink(1) from a config entry."""
    vid: int = entry.data["vid"]
    pid: int = entry.data["pid"]

    _LOGGER.debug(
        "Setting up Blink(1) entry_id=%s for %04x:%04x",
        entry.entry_id,
        vid,
        pid,
    )

    try:
        device = await hass.async_add_executor_job(open_blink1_transport, vid, pid)
    except OSError as err:
        _LOGGER.debug(
            "Transport open failed for %04x:%04x: %s",
            vid,
            pid,
            err,
        )
        raise ConfigEntryNotReady(
            f"Cannot open USB HID device {vid:#06x}:{pid:#06x} — "
            "check the blink(1) is plugged in and you have HID access permissions"
        ) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = device
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Blink(1) setup complete for entry_id=%s", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and close the HID device."""
    _LOGGER.debug("Unloading Blink(1) entry_id=%s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        device = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(device.close)
        _LOGGER.debug("Closed transport for entry_id=%s", entry.entry_id)
    return unload_ok
