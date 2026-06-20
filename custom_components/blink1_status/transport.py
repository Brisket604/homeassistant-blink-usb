"""Transport layer for talking to the blink(1) USB device."""
from __future__ import annotations

from dataclasses import dataclass
import glob
import logging
import os
import struct

_LOGGER = logging.getLogger(__name__)


class Blink1Transport:
    """Minimal transport interface for blink(1) communication."""

    def write(self, payload: bytes) -> None:
        """Write one HID feature report to the device."""

    def close(self) -> None:
        """Close transport resources."""


@dataclass(slots=True)
class LinuxHidrawTransport(Blink1Transport):
    """Native Linux hidraw transport using only the Python standard library."""

    fd: int

    def write(self, payload: bytes) -> None:
        os.write(self.fd, payload)

    def close(self) -> None:
        os.close(self.fd)


@dataclass(slots=True)
class PyHidTransport(Blink1Transport):
    """Fallback transport backed by the optional ``hid`` package."""

    device: object

    def write(self, payload: bytes) -> None:
        self.device.write(list(payload))

    def close(self) -> None:
        self.device.close()


def open_blink1_transport(vid: int, pid: int) -> Blink1Transport:
    """Open a blink(1) transport.

    Strategy:
    1) Linux hidraw (no external Python dependency)
    2) Optional ``hid`` package fallback
    """
    first_error: OSError | None = None
    _LOGGER.debug("Opening blink(1) transport for %04x:%04x", vid, pid)

    if os.name == "posix":
        try:
            _LOGGER.debug("Trying Linux hidraw transport")
            return _open_linux_hidraw_transport(vid, pid)
        except OSError as err:
            first_error = err
            _LOGGER.debug("Linux hidraw transport failed: %s", err)

    try:
        _LOGGER.debug("Trying optional pyhid transport")
        return _open_pyhid_transport(vid, pid)
    except OSError as err:
        if first_error is not None:
            raise OSError(f"{first_error}; fallback via hid failed: {err}") from err
        raise


def _open_linux_hidraw_transport(vid: int, pid: int) -> LinuxHidrawTransport:
    """Find and open a matching Linux ``/dev/hidrawX`` node."""
    expected = f"{vid:04X}:{pid:04X}"
    for sys_node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent_path = os.path.join(sys_node, "device", "uevent")
        if not os.path.exists(uevent_path):
            continue

        with open(uevent_path, encoding="utf-8") as file_obj:
            uevent = file_obj.read()

        hid_id_prefix = "HID_ID="
        hid_id_line = next(
            (line for line in uevent.splitlines() if line.startswith(hid_id_prefix)),
            None,
        )
        if hid_id_line is None:
            continue

        # HID_ID format: BUS:VID:PID (all hex), example 0003:000027B8:000001ED
        parts = hid_id_line.removeprefix(hid_id_prefix).split(":")
        if len(parts) != 3:
            continue
        candidate = f"{parts[1][-4:]}:{parts[2][-4:]}".upper()
        if candidate != expected:
            continue

        dev_name = os.path.basename(sys_node)
        dev_path = os.path.join("/dev", dev_name)
        _LOGGER.debug("Matched blink(1) hidraw node at %s", dev_path)
        fd = os.open(dev_path, os.O_RDWR | os.O_CLOEXEC)
        return LinuxHidrawTransport(fd=fd)

    raise OSError(
        f"No matching hidraw device found for {vid:#06x}:{pid:#06x}; "
        "check udev permissions and container device mapping"
    )


def _open_pyhid_transport(vid: int, pid: int) -> PyHidTransport:
    """Open optional ``hid``-based transport."""
    try:
        import hid  # noqa: PLC0415
    except ImportError as err:
        raise OSError(
            "The optional 'hid' package is not installed. "
            "Install it or run on Linux with hidraw access."
        ) from err

    device = hid.device()
    device.open(vid, pid)
    device.set_nonblocking(True)
    _LOGGER.debug("Opened pyhid transport for %04x:%04x", vid, pid)
    return PyHidTransport(device=device)


def build_fade_to_rgb(r: int, g: int, b: int, fade_ms: int = 100) -> bytes:
    """Build the blink(1) HID feature report for 'fade to RGB'.

    blink(1) protocol: report ID 1, command 'c' (0x63), then:
      byte 0: report ID (0x01)
      byte 1: command 'c' (fade to RGB)
      byte 2: red
      byte 3: green
      byte 4: blue
      byte 5-6: fade time in 10ms units (big-endian)
      byte 7: LED index (0 = all)
      byte 8: padding (0x00)
    Total 9 bytes.
    """
    fade_units = fade_ms // 10
    hi = (fade_units >> 8) & 0xFF
    lo = fade_units & 0xFF
    return bytes([0x01, 0x63, r & 0xFF, g & 0xFF, b & 0xFF, hi, lo, 0x00, 0x00])


def build_off() -> bytes:
    """Build the HID report to turn the blink(1) off (fade to black)."""
    return build_fade_to_rgb(0, 0, 0, fade_ms=100)
