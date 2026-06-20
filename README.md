# Blink(1) Status Light - Home Assistant Integration

Custom integration for [Home Assistant](https://www.home-assistant.io/) to control a [ThingM blink(1)](https://blink1.thingm.com/) USB LED indicator.

## Features

- Full RGB color control via HS color mode
- Brightness control
- Zero external Python dependencies (uses Linux hidraw directly)
- USB auto-discovery
- Config flow (UI setup)
- HACS compatible

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS
2. Install "Blink(1) Status Light"
3. Restart Home Assistant
4. The blink(1) should be auto-discovered, or add it via Settings → Devices & Services → Add Integration

### Manual

1. Copy `custom_components/blink1_status/` to your HA config directory
2. Restart Home Assistant

## Requirements

- blink(1) mk2 USB device (VID: 27b8, PID: 01ed)
- The device must be accessible via `/dev/hidrawX` with appropriate permissions

## USB Permissions on HA OS

This integration declares the USB device in its manifest, which should grant HA OS automatic access. If you encounter permission issues, create a udev rule on the host:

```
KERNEL=="hidraw*", ATTRS{idVendor}=="27b8", ATTRS{idProduct}=="01ed", MODE="0666"
```

## Credits

Based on the [blink(1) protocol](https://github.com/todbot/blink1/blob/main/docs/blink1-hid-commands.md).
