"""Blink(1) Status Light platform."""
from __future__ import annotations

import logging
from typing import Any

import homeassistant.util.color as color_util
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .transport import build_fade_to_rgb, build_off

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Blink(1) light entity."""
    device = hass.data[DOMAIN][entry.entry_id]["transport"]
    async_add_entities([Blink1Light(device, entry)])


class Blink1Light(LightEntity):
    """Representation of a blink(1) USB LED as a Home Assistant light.

    Supports full RGB color and brightness control via HS color mode.
    """

    _attr_has_entity_name = True
    _attr_name = None  # entity name == device name
    _attr_color_mode = ColorMode.HS
    _attr_supported_color_modes: set[ColorMode] = {ColorMode.HS}
    _attr_icon = "mdi:led-on"
    _attr_should_poll = False

    def __init__(self, device: Any, entry: ConfigEntry) -> None:
        """Initialise the light entity."""
        self._device = device
        self._entry = entry
        self._attr_unique_id = entry.unique_id or entry.entry_id
        self._attr_is_on = False
        self._attr_brightness = 255
        self._attr_hs_color = (0.0, 0.0)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name="Blink(1)",
            manufacturer="ThingM",
            model="blink(1) mk2",
            configuration_url="https://blink1.thingm.com/",
        )
        _LOGGER.debug("Blink1Light entity initialised entry_id=%s", entry.entry_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the blink(1) on with the given color/brightness."""
        if ATTR_HS_COLOR in kwargs:
            self._attr_hs_color = kwargs[ATTR_HS_COLOR]
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

        self._attr_is_on = True

        # Convert HS + brightness to RGB
        rgb = color_util.color_hsv_to_RGB(
            self._attr_hs_color[0],
            self._attr_hs_color[1],
            self._attr_brightness / 255 * 100,
        )

        payload = build_fade_to_rgb(rgb[0], rgb[1], rgb[2])
        _LOGGER.debug("Turning blink(1) on: RGB=(%d,%d,%d)", rgb[0], rgb[1], rgb[2])

        try:
            await self.hass.async_add_executor_job(self._device.write, payload)
        except OSError:
            _LOGGER.error("Failed to send command to blink(1)")

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the blink(1) off."""
        self._attr_is_on = False
        _LOGGER.debug("Turning blink(1) off")

        try:
            await self.hass.async_add_executor_job(self._device.write, build_off())
        except OSError:
            _LOGGER.error("Failed to send off command to blink(1)")

        self.async_write_ha_state()
