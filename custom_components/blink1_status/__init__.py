"""Blink(1) Status Light integration setup."""
from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError

from .commands import (
    build_get_version_request,
    build_play_loop,
    build_play_state_request,
    build_read_color_request,
    build_server_tickle_disable,
    build_server_tickle_enable,
    build_set_pattern_line,
    build_read_pattern_line_request,
    build_save_patterns,
    build_stop_play,
    parse_get_version_response,
    parse_play_state_response,
    parse_read_color_response,
    parse_read_pattern_line_response,
    parse_pattern_string,
    format_pattern_lines,
)
from .const import DOMAIN
from .transport import open_blink1_transport

_LOGGER = logging.getLogger(__name__)

# --- Voluptuous schemas for service validation ---

SCHEMA_SET_PATTERN_LINE = vol.Schema({
    vol.Required("position"): vol.All(int, vol.Range(min=0, max=31)),
    vol.Required("red"): vol.All(int, vol.Range(min=0, max=255)),
    vol.Required("green"): vol.All(int, vol.Range(min=0, max=255)),
    vol.Required("blue"): vol.All(int, vol.Range(min=0, max=255)),
    vol.Required("fade_ms"): vol.All(int, vol.Range(min=0, max=655350)),
    vol.Optional("led", default=0): vol.All(int, vol.Range(min=0, max=2)),
})

SCHEMA_GET_PATTERN_LINE = vol.Schema({
    vol.Required("position"): vol.All(int, vol.Range(min=0, max=31)),
})

SCHEMA_WRITE_PATTERN = vol.Schema({
    vol.Required("pattern"): str,
})

SCHEMA_READ_PATTERN = vol.Schema({
    vol.Required("start"): vol.All(int, vol.Range(min=0, max=31)),
    vol.Required("end"): vol.All(int, vol.Range(min=0, max=31)),
})

SCHEMA_PLAY_PATTERN = vol.Schema({
    vol.Required("start"): vol.All(int, vol.Range(min=0, max=31)),
    vol.Required("end"): vol.All(int, vol.Range(min=0, max=31)),
    vol.Optional("count", default=0): vol.All(int, vol.Range(min=0, max=255)),
})

SCHEMA_BLINK = vol.Schema({
    vol.Required("red"): vol.All(int, vol.Range(min=0, max=255)),
    vol.Required("green"): vol.All(int, vol.Range(min=0, max=255)),
    vol.Required("blue"): vol.All(int, vol.Range(min=0, max=255)),
    vol.Optional("count", default=3): vol.All(int, vol.Range(min=1, max=255)),
    vol.Optional("fade_ms", default=300): vol.All(int, vol.Range(min=0, max=655350)),
    vol.Optional("led", default=0): vol.All(int, vol.Range(min=0, max=2)),
})

SCHEMA_ENABLE_SERVER_TICKLE = vol.Schema({
    vol.Required("timeout_ms"): vol.All(int, vol.Range(min=100, max=655350)),
    vol.Required("start"): vol.All(int, vol.Range(min=0, max=31)),
    vol.Required("end"): vol.All(int, vol.Range(min=0, max=31)),
})

PLATFORMS: list[str] = ["light"]


# ---------------------------------------------------------------------------
# Server Tickle (watchdog) keepalive manager
# ---------------------------------------------------------------------------


class ServerTickleManager:
    """Gère la tâche keepalive du server tickle."""

    def __init__(self, hass: HomeAssistant, transport) -> None:
        """Initialize the server tickle manager.

        Args:
            hass: Home Assistant instance.
            transport: Blink1Transport instance for HID communication.
        """
        self._hass = hass
        self._transport = transport
        self._task: asyncio.Task | None = None
        self._cancel_event: asyncio.Event = asyncio.Event()

    async def start(self, timeout_ms: int, start: int, end: int) -> None:
        """Démarre le keepalive. Annule toute tâche existante.

        Args:
            timeout_ms: Watchdog timeout in milliseconds (10-655350).
            start: Pattern start position (0-31).
            end: Pattern end position (0-31, must be > start).
        """
        await self.stop()
        payload = build_server_tickle_enable(timeout_ms, start, end)
        interval = timeout_ms / 2000  # 50% du timeout, en secondes
        self._cancel_event.clear()
        self._task = self._hass.async_create_task(
            self._keepalive_loop(payload, interval)
        )

    async def stop(self) -> None:
        """Arrête le keepalive et désactive le server tickle."""
        if self._task is not None:
            self._cancel_event.set()
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        payload = build_server_tickle_disable()
        await self._hass.async_add_executor_job(self._transport.write, payload)

    async def _keepalive_loop(self, payload: bytes, interval: float) -> None:
        """Boucle d'envoi périodique du keepalive."""
        try:
            while not self._cancel_event.is_set():
                await self._hass.async_add_executor_job(
                    self._transport.write, payload
                )
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass


class BlinkEffectManager:
    """Gère l'effet de clignotement avec sauvegarde/restauration des patterns."""

    def __init__(self, hass: HomeAssistant, transport) -> None:
        """Initialize the blink effect manager.

        Args:
            hass: Home Assistant instance.
            transport: Blink1Transport instance for HID communication.
        """
        self._hass = hass
        self._transport = transport
        self._active_task: asyncio.Task | None = None

    async def start_blink(
        self, r: int, g: int, b: int, count: int, fade_ms: int, led_n: int
    ) -> None:
        """Démarre un clignotement. Annule tout clignotement en cours.

        Args:
            r: Red component (0-255).
            g: Green component (0-255).
            b: Blue component (0-255).
            count: Number of blinks (1-255).
            fade_ms: Fade duration in milliseconds (0-655350).
            led_n: LED index (0=all, 1=top, 2=bottom).
        """
        if self._active_task is not None:
            self._active_task.cancel()
            try:
                await self._active_task
            except asyncio.CancelledError:
                pass

        self._active_task = self._hass.async_create_task(
            self._blink_sequence(r, g, b, count, fade_ms, led_n)
        )

    async def _blink_sequence(
        self, r: int, g: int, b: int, count: int, fade_ms: int, led_n: int
    ) -> None:
        """Sauvegarde patterns 0-1, écrit le blink, lance play, restaure."""
        saved_0 = None
        saved_1 = None
        try:
            # 1. Save pattern lines at positions 0 and 1
            payload = build_read_pattern_line_request(0)
            await self._hass.async_add_executor_job(self._transport.write, payload)
            response = await self._hass.async_add_executor_job(
                self._transport.read, 0x01
            )
            saved_0 = parse_read_pattern_line_response(response)

            payload = build_read_pattern_line_request(1)
            await self._hass.async_add_executor_job(self._transport.write, payload)
            response = await self._hass.async_add_executor_job(
                self._transport.read, 0x01
            )
            saved_1 = parse_read_pattern_line_response(response)

            # 2. Write blink pattern: target color at position 0, black at position 1
            payload = build_set_pattern_line(r, g, b, fade_ms, 0)
            await self._hass.async_add_executor_job(self._transport.write, payload)

            payload = build_set_pattern_line(0, 0, 0, fade_ms, 1)
            await self._hass.async_add_executor_job(self._transport.write, payload)

            # 3. Start play loop on positions 0-2 with count
            payload = build_play_loop(0, 2, count)
            await self._hass.async_add_executor_job(self._transport.write, payload)

            # 4. Wait for blink to finish (count * 2 * fade_ms milliseconds)
            total_ms = count * 2 * fade_ms
            await asyncio.sleep(total_ms / 1000)

            # 5. Restore original pattern lines
            payload = build_set_pattern_line(
                saved_0.r, saved_0.g, saved_0.b, saved_0.fade_ms, 0
            )
            await self._hass.async_add_executor_job(self._transport.write, payload)

            payload = build_set_pattern_line(
                saved_1.r, saved_1.g, saved_1.b, saved_1.fade_ms, 1
            )
            await self._hass.async_add_executor_job(self._transport.write, payload)

        except asyncio.CancelledError:
            # Try to restore patterns even if cancelled (only if we saved them)
            if saved_0 is not None and saved_1 is not None:
                try:
                    payload = build_set_pattern_line(
                        saved_0.r, saved_0.g, saved_0.b, saved_0.fade_ms, 0
                    )
                    await self._hass.async_add_executor_job(
                        self._transport.write, payload
                    )
                    payload = build_set_pattern_line(
                        saved_1.r, saved_1.g, saved_1.b, saved_1.fade_ms, 1
                    )
                    await self._hass.async_add_executor_job(
                        self._transport.write, payload
                    )
                except Exception:
                    _LOGGER.warning(
                        "Failed to restore pattern lines after blink cancellation"
                    )
        except Exception:
            _LOGGER.warning("Blink effect failed", exc_info=True)
        finally:
            self._active_task = None


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

    tickle_manager = ServerTickleManager(hass, device)
    blink_manager = BlinkEffectManager(hass, device)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "transport": device,
        "tickle_manager": tickle_manager,
        "blink_manager": blink_manager,
    }
    _register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Blink(1) setup complete for entry_id=%s", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and close the HID device."""
    _LOGGER.debug("Unloading Blink(1) entry_id=%s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id)
        # Stop server tickle keepalive before closing transport
        tickle_manager = entry_data["tickle_manager"]
        if tickle_manager is not None:
            try:
                await tickle_manager.stop()
            except Exception:
                _LOGGER.warning("Failed to stop server tickle during unload", exc_info=True)
        transport = entry_data["transport"]
        await hass.async_add_executor_job(transport.close)
        _LOGGER.debug("Closed transport for entry_id=%s", entry.entry_id)
    return unload_ok


# --- Service handler stubs (implemented in tasks 8.3, 8.4, 8.5) ---


async def _handle_set_pattern_line(call: ServiceCall) -> None:
    """Handle set_pattern_line service call."""
    hass = call.hass
    entry_data = next(iter(hass.data[DOMAIN].values()))
    transport = entry_data["transport"]

    position = call.data["position"]
    red = call.data["red"]
    green = call.data["green"]
    blue = call.data["blue"]
    fade_ms = call.data["fade_ms"]

    try:
        payload = build_set_pattern_line(red, green, blue, fade_ms, position)
        await hass.async_add_executor_job(transport.write, payload)
    except ValueError as err:
        raise HomeAssistantError(f"Invalid parameter: {err}") from err
    except OSError as err:
        raise HomeAssistantError(f"blink(1) communication error: {err}") from err


async def _handle_get_pattern_line(call: ServiceCall) -> dict:
    """Handle get_pattern_line service call."""
    hass = call.hass
    entry_data = next(iter(hass.data[DOMAIN].values()))
    transport = entry_data["transport"]

    position = call.data["position"]

    try:
        payload = build_read_pattern_line_request(position)
        await hass.async_add_executor_job(transport.write, payload)
        response = await hass.async_add_executor_job(transport.read, 0x01)
        pl = parse_read_pattern_line_response(response)
    except ValueError as err:
        raise HomeAssistantError(f"Invalid parameter: {err}") from err
    except OSError as err:
        raise HomeAssistantError(f"blink(1) communication error: {err}") from err

    return {"r": pl.r, "g": pl.g, "b": pl.b, "fade_ms": pl.fade_ms}


async def _handle_save_pattern(call: ServiceCall) -> None:
    """Handle save_pattern service call."""
    hass = call.hass
    entry_data = next(iter(hass.data[DOMAIN].values()))
    transport = entry_data["transport"]

    try:
        payload = build_save_patterns()
        await hass.async_add_executor_job(transport.write, payload)
    except OSError as err:
        raise HomeAssistantError(f"blink(1) communication error: {err}") from err


async def _handle_clear_pattern(call: ServiceCall) -> None:
    """Handle clear_pattern service call."""
    hass = call.hass
    entry_data = next(iter(hass.data[DOMAIN].values()))
    transport = entry_data["transport"]

    for pos in range(32):
        try:
            payload = build_set_pattern_line(0, 0, 0, 0, pos)
            await hass.async_add_executor_job(transport.write, payload)
        except OSError as err:
            raise HomeAssistantError(
                f"blink(1) communication error at position {pos}: {err}"
            ) from err


async def _handle_write_pattern(call: ServiceCall) -> None:
    """Handle write_pattern service call."""
    hass = call.hass
    entry_data = next(iter(hass.data[DOMAIN].values()))
    transport = entry_data["transport"]

    pattern_str = call.data["pattern"]

    try:
        lines = parse_pattern_string(pattern_str)
    except ValueError as err:
        raise HomeAssistantError(f"Invalid parameter: {err}") from err

    for i, line in enumerate(lines):
        try:
            payload = build_set_pattern_line(line.r, line.g, line.b, line.fade_ms, i)
            await hass.async_add_executor_job(transport.write, payload)
        except OSError as err:
            raise HomeAssistantError(
                f"blink(1) communication error at position {i}: {err}"
            ) from err


async def _handle_read_pattern(call: ServiceCall) -> dict:
    """Handle read_pattern service call."""
    hass = call.hass
    entry_data = next(iter(hass.data[DOMAIN].values()))
    transport = entry_data["transport"]

    start = call.data["start"]
    end = call.data["end"]

    results = []
    for pos in range(start, end + 1):
        try:
            payload = build_read_pattern_line_request(pos)
            await hass.async_add_executor_job(transport.write, payload)
            response = await hass.async_add_executor_job(transport.read, 0x01)
            pl = parse_read_pattern_line_response(response)
            results.append(pl)
        except ValueError as err:
            raise HomeAssistantError(f"Invalid parameter: {err}") from err
        except OSError as err:
            raise HomeAssistantError(
                f"blink(1) communication error at position {pos}: {err}"
            ) from err

    return {"pattern": format_pattern_lines(results)}


async def _handle_play_pattern(call: ServiceCall) -> None:
    """Handle play_pattern service call."""
    hass = call.hass
    entry_data = next(iter(hass.data[DOMAIN].values()))
    transport = entry_data["transport"]

    start = call.data["start"]
    end = call.data["end"]
    count = call.data["count"]

    try:
        payload = build_play_loop(start, end, count)
        await hass.async_add_executor_job(transport.write, payload)
    except ValueError as err:
        raise HomeAssistantError(f"Invalid parameter: {err}") from err
    except OSError as err:
        raise HomeAssistantError(f"blink(1) communication error: {err}") from err


async def _handle_stop_pattern(call: ServiceCall) -> None:
    """Handle stop_pattern service call."""
    hass = call.hass
    entry_data = next(iter(hass.data[DOMAIN].values()))
    transport = entry_data["transport"]

    try:
        payload = build_stop_play()
        await hass.async_add_executor_job(transport.write, payload)
    except OSError as err:
        raise HomeAssistantError(f"blink(1) communication error: {err}") from err


async def _handle_play_state(call: ServiceCall) -> dict:
    """Handle play_state service call."""
    hass = call.hass
    entry_data = next(iter(hass.data[DOMAIN].values()))
    transport = entry_data["transport"]

    try:
        payload = build_play_state_request()
        await hass.async_add_executor_job(transport.write, payload)
        response = await hass.async_add_executor_job(transport.read, 0x01)
        ps = parse_play_state_response(response)
    except OSError as err:
        raise HomeAssistantError(f"blink(1) communication error: {err}") from err

    return {
        "playing": ps.playing,
        "play_start": ps.play_start,
        "play_end": ps.play_end,
        "play_count": ps.play_count,
        "play_pos": ps.play_pos,
    }


async def _handle_blink(call: ServiceCall) -> None:
    """Handle blink service call."""
    hass = call.hass
    entry_data = next(iter(hass.data[DOMAIN].values()))
    blink_manager = entry_data["blink_manager"]

    red = call.data["red"]
    green = call.data["green"]
    blue = call.data["blue"]
    count = call.data["count"]
    fade_ms = call.data["fade_ms"]
    led = call.data["led"]

    try:
        await blink_manager.start_blink(red, green, blue, count, fade_ms, led)
    except ValueError as err:
        raise HomeAssistantError(f"Invalid parameter: {err}") from err
    except OSError as err:
        raise HomeAssistantError(f"blink(1) communication error: {err}") from err


async def _handle_enable_server_tickle(call: ServiceCall) -> None:
    """Handle enable_server_tickle service call."""
    hass = call.hass
    entry_data = next(iter(hass.data[DOMAIN].values()))
    tickle_manager = entry_data["tickle_manager"]

    timeout_ms = call.data["timeout_ms"]
    start = call.data["start"]
    end = call.data["end"]

    try:
        await tickle_manager.start(timeout_ms, start, end)
    except ValueError as err:
        raise HomeAssistantError(f"Invalid parameter: {err}") from err
    except OSError as err:
        raise HomeAssistantError(f"blink(1) communication error: {err}") from err


async def _handle_disable_server_tickle(call: ServiceCall) -> None:
    """Handle disable_server_tickle service call."""
    hass = call.hass
    entry_data = next(iter(hass.data[DOMAIN].values()))
    tickle_manager = entry_data["tickle_manager"]

    try:
        await tickle_manager.stop()
    except OSError as err:
        raise HomeAssistantError(f"blink(1) communication error: {err}") from err


async def _handle_get_device_state(call: ServiceCall) -> dict:
    """Handle get_device_state service call."""
    hass = call.hass
    entry_data = next(iter(hass.data[DOMAIN].values()))
    transport = entry_data["transport"]

    async def _read_device_state() -> dict:
        # 1. Read firmware version
        try:
            payload = build_get_version_request()
            await hass.async_add_executor_job(transport.write, payload)
            response = await hass.async_add_executor_job(transport.read, 0x01)
            firmware_version = parse_get_version_response(response)
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                f"blink(1) communication error during firmware version read: {err}"
            ) from err

        # 2. Read current color
        try:
            payload = build_read_color_request()
            await hass.async_add_executor_job(transport.write, payload)
            response = await hass.async_add_executor_job(transport.read, 0x01)
            color = parse_read_color_response(response)
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                f"blink(1) communication error during color read: {err}"
            ) from err

        # 3. Read play state
        try:
            payload = build_play_state_request()
            await hass.async_add_executor_job(transport.write, payload)
            response = await hass.async_add_executor_job(transport.read, 0x01)
            ps = parse_play_state_response(response)
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                f"blink(1) communication error during play state read: {err}"
            ) from err

        return {
            "firmware_version": firmware_version,
            "current_color": {"r": color.r, "g": color.g, "b": color.b},
            "play_state": {
                "playing": ps.playing,
                "play_start": ps.play_start,
                "play_end": ps.play_end,
                "play_count": ps.play_count,
                "play_pos": ps.play_pos,
            },
        }

    try:
        return await asyncio.wait_for(_read_device_state(), timeout=5.0)
    except asyncio.TimeoutError as err:
        raise HomeAssistantError(
            "blink(1) get_device_state timed out: operations exceeded 5 second limit"
        ) from err


# --- Service registration ---


def _register_services(hass: HomeAssistant) -> None:
    """Register all blink1_status services. Only registers once."""
    if hass.services.has_service(DOMAIN, "set_pattern_line"):
        return

    # Pattern management services
    hass.services.async_register(
        DOMAIN, "set_pattern_line", _handle_set_pattern_line,
        schema=SCHEMA_SET_PATTERN_LINE,
    )
    hass.services.async_register(
        DOMAIN, "get_pattern_line", _handle_get_pattern_line,
        schema=SCHEMA_GET_PATTERN_LINE,
    )
    hass.services.async_register(
        DOMAIN, "save_pattern", _handle_save_pattern,
        schema=None,
    )
    hass.services.async_register(
        DOMAIN, "clear_pattern", _handle_clear_pattern,
        schema=None,
    )
    hass.services.async_register(
        DOMAIN, "write_pattern", _handle_write_pattern,
        schema=SCHEMA_WRITE_PATTERN,
    )
    hass.services.async_register(
        DOMAIN, "read_pattern", _handle_read_pattern,
        schema=SCHEMA_READ_PATTERN,
    )

    # Play loop services
    hass.services.async_register(
        DOMAIN, "play_pattern", _handle_play_pattern,
        schema=SCHEMA_PLAY_PATTERN,
    )
    hass.services.async_register(
        DOMAIN, "stop_pattern", _handle_stop_pattern,
        schema=None,
    )
    hass.services.async_register(
        DOMAIN, "play_state", _handle_play_state,
        schema=None,
    )

    # Visual effects service
    hass.services.async_register(
        DOMAIN, "blink", _handle_blink,
        schema=SCHEMA_BLINK,
    )

    # Server tickle (watchdog) services
    hass.services.async_register(
        DOMAIN, "enable_server_tickle", _handle_enable_server_tickle,
        schema=SCHEMA_ENABLE_SERVER_TICKLE,
    )
    hass.services.async_register(
        DOMAIN, "disable_server_tickle", _handle_disable_server_tickle,
        schema=None,
    )

    # Device state service
    hass.services.async_register(
        DOMAIN, "get_device_state", _handle_get_device_state,
        schema=None,
    )

    _LOGGER.debug("Registered %d blink1_status services", 13)
