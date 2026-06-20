"""Config flow for Blink(1) Status Light."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import BLINK1_PID, BLINK1_VID, DOMAIN
from .transport import open_blink1_transport

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.components.usb import UsbServiceInfo


@config_entries.HANDLERS.register(DOMAIN)
class Blink1ConfigFlow(config_entries.ConfigFlow):
    """Handle a config flow for the Blink(1)."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise flow state."""
        self._vid: int = BLINK1_VID
        self._pid: int = BLINK1_PID

    # ------------------------------------------------------------------
    # USB auto-discovery path
    # ------------------------------------------------------------------

    async def async_step_usb(
        self, discovery_info: UsbServiceInfo
    ) -> FlowResult:
        """Handle USB auto-discovery triggered by the manifest usb table."""
        _LOGGER.debug("USB discovery received: %s", discovery_info)
        self._vid = int(str(discovery_info.vid), 16)
        self._pid = int(str(discovery_info.pid), 16)

        unique_id = (
            discovery_info.serial_number
            if discovery_info.serial_number
            else f"{str(discovery_info.vid).lower()}:{str(discovery_info.pid).lower()}"
        )
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        _LOGGER.debug(
            "USB discovery accepted for %04x:%04x unique_id=%s",
            self._vid,
            self._pid,
            unique_id,
        )

        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask the user to confirm a discovered device before creating an entry."""
        if user_input is not None:
            _LOGGER.debug(
                "Discovery confirmed by user for %04x:%04x",
                self._vid,
                self._pid,
            )
            return self.async_create_entry(
                title=f"Blink(1) {self._vid:04x}:{self._pid:04x}",
                data={"vid": self._vid, "pid": self._pid},
            )

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "vid": f"{self._vid:04x}",
                "pid": f"{self._pid:04x}",
            },
        )

    # ------------------------------------------------------------------
    # Manual setup path
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual setup initiated from the UI."""
        errors: dict[str, str] = {}

        if user_input is not None:
            vid = BLINK1_VID
            pid = BLINK1_PID
            _LOGGER.debug("Manual setup test for %04x:%04x", vid, pid)
            try:
                await self.hass.async_add_executor_job(_test_device, vid, pid)
            except OSError:
                _LOGGER.debug("Manual setup connection failed for %04x:%04x", vid, pid)
                errors["base"] = "cannot_connect"
            else:
                vid_str = f"{vid:04x}"
                pid_str = f"{pid:04x}"
                await self.async_set_unique_id(f"{vid_str}:{pid_str}")
                self._abort_if_unique_id_configured()
                _LOGGER.debug("Manual setup succeeded for %s:%s", vid_str, pid_str)
                return self.async_create_entry(
                    title=f"Blink(1) {vid_str}:{pid_str}",
                    data={"vid": vid, "pid": pid},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            errors=errors,
        )


def _test_device(vid: int, pid: int) -> None:
    """Attempt to open and immediately close the HID device. Blocking."""
    transport = open_blink1_transport(vid, pid)
    transport.close()
