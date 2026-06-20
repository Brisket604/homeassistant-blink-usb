# Blink(1) Status Light - Home Assistant Integration

Custom integration for [Home Assistant](https://www.home-assistant.io/) to control a [ThingM blink(1)](https://blink1.thingm.com/) USB LED indicator.

## Features

- Full RGB color control via HS color mode
- Brightness control
- Zero external Python dependencies (uses Linux hidraw directly)
- USB auto-discovery
- Config flow (UI setup)
- HACS compatible
- 13 services exposing the full blink(1) mk2+ HID protocol

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS
2. Install "Blink(1) Status Light"
3. Restart Home Assistant
4. The blink(1) should be auto-discovered, or add it via Settings → Devices & Services → Add Integration

### Manual

1. Copy the `custom_components/blink1_status/` folder into your HA `config/` directory
2. Restart Home Assistant

## Requirements

- blink(1) mk2 USB device (VID: 27b8, PID: 01ed)
- The device must be accessible via `/dev/hidrawX` with appropriate permissions

## USB Permissions on HA OS

This integration declares the USB device in its manifest, which should grant HA OS automatic access. If you encounter permission issues, create a udev rule on the host:

```
KERNEL=="hidraw*", ATTRS{idVendor}=="27b8", ATTRS{idProduct}=="01ed", MODE="0666"
```

---

## Services

All services are available under **Developer Tools → Services** in the `blink1_status` domain.

---

### Pattern Management

#### `blink1_status.set_pattern_line`

Write a pattern line (color + fade time) at a given position in RAM.

| Parameter | Type | Required | Range | Default |
|-----------|------|----------|-------|---------|
| `position` | int | yes | 0–31 | — |
| `red` | int | yes | 0–255 | — |
| `green` | int | yes | 0–255 | — |
| `blue` | int | yes | 0–255 | — |
| `fade_ms` | int | yes | 0–655350 | — |
| `led` | int | no | 0–2 | 0 |

```yaml
service: blink1_status.set_pattern_line
data:
  position: 0
  red: 255
  green: 0
  blue: 0
  fade_ms: 500
```

```yaml
# Rainbow pattern across 3 positions
service: blink1_status.set_pattern_line
data:
  position: 0
  red: 255
  green: 0
  blue: 0
  fade_ms: 1000

service: blink1_status.set_pattern_line
data:
  position: 1
  red: 0
  green: 255
  blue: 0
  fade_ms: 1000

service: blink1_status.set_pattern_line
data:
  position: 2
  red: 0
  green: 0
  blue: 255
  fade_ms: 1000
```

---

#### `blink1_status.get_pattern_line`

Read a pattern line from memory. Returns `{ r, g, b, fade_ms }`.

| Parameter | Type | Required | Range |
|-----------|------|----------|-------|
| `position` | int | yes | 0–31 |

```yaml
service: blink1_status.get_pattern_line
data:
  position: 0
```

Response:
```json
{ "r": 255, "g": 0, "b": 0, "fade_ms": 500 }
```

---

#### `blink1_status.write_pattern`

Write a full pattern from a formatted string. Each segment is written to consecutive positions starting at 0.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pattern` | string | yes | Format: `R,G,B,fade_ms;R,G,B,fade_ms;...` (max 32 segments) |

```yaml
# Write a red-green-blue pattern with 500ms fade each
service: blink1_status.write_pattern
data:
  pattern: "255,0,0,500;0,255,0,500;0,0,255,500"
```

```yaml
# Alert pattern: fast red blink
service: blink1_status.write_pattern
data:
  pattern: "255,0,0,200;0,0,0,200"
```

```yaml
# White to black gradient
service: blink1_status.write_pattern
data:
  pattern: "255,255,255,1000;128,128,128,1000;0,0,0,1000"
```

---

#### `blink1_status.read_pattern`

Read a range of pattern lines and return the formatted string.

| Parameter | Type | Required | Range |
|-----------|------|----------|-------|
| `start` | int | yes | 0–31 |
| `end` | int | yes | 0–31 |

```yaml
service: blink1_status.read_pattern
data:
  start: 0
  end: 5
```

Response:
```json
{ "pattern": "255,0,0,500;0,255,0,500;0,0,255,500;0,0,0,0;0,0,0,0;0,0,0,0" }
```

---

#### `blink1_status.save_pattern`

Save all 32 pattern lines from RAM to flash memory (persists across power cycles).

```yaml
service: blink1_status.save_pattern
data: {}
```

---

#### `blink1_status.clear_pattern`

Clear all 32 pattern positions (set to black, fade 0ms). RAM only — does not write to flash.

```yaml
service: blink1_status.clear_pattern
data: {}
```

---

### Play Loop Control

#### `blink1_status.play_pattern`

Start looping playback of pattern lines between two positions.

| Parameter | Type | Required | Range | Default |
|-----------|------|----------|-------|---------|
| `start` | int | yes | 0–31 | — |
| `end` | int | yes | 0–31 (> start) | — |
| `count` | int | no | 0–255 (0=infinite) | 0 |

```yaml
# Loop positions 0 to 3 forever
service: blink1_status.play_pattern
data:
  start: 0
  end: 3
  count: 0
```

```yaml
# Play positions 0 to 2 exactly 5 times
service: blink1_status.play_pattern
data:
  start: 0
  end: 2
  count: 5
```

---

#### `blink1_status.stop_pattern`

Stop the currently playing pattern loop.

```yaml
service: blink1_status.stop_pattern
data: {}
```

---

#### `blink1_status.play_state`

Read the current playback state. Returns `{ playing, play_start, play_end, play_count, play_pos }`.

```yaml
service: blink1_status.play_state
data: {}
```

Response:
```json
{ "playing": true, "play_start": 0, "play_end": 3, "play_count": 0, "play_pos": 1 }
```

---

### Visual Effects

#### `blink1_status.blink`

Blink a color. Automatically saves and restores pattern lines at positions 0 and 1.

| Parameter | Type | Required | Range | Default |
|-----------|------|----------|-------|---------|
| `red` | int | yes | 0–255 | — |
| `green` | int | yes | 0–255 | — |
| `blue` | int | yes | 0–255 | — |
| `count` | int | no | 1–255 | 3 |
| `fade_ms` | int | no | 0–655350 | 300 |
| `led` | int | no | 0–2 | 0 |

```yaml
# Blink red 5 times
service: blink1_status.blink
data:
  red: 255
  green: 0
  blue: 0
  count: 5
```

```yaml
# Fast green flash on top LED only
service: blink1_status.blink
data:
  red: 0
  green: 255
  blue: 0
  count: 3
  fade_ms: 100
  led: 1
```

```yaml
# Slow subtle blue notification
service: blink1_status.blink
data:
  red: 0
  green: 100
  blue: 255
  count: 2
  fade_ms: 1000
```

---

### Server Tickle (Watchdog)

The watchdog automatically plays a pattern if Home Assistant stops communicating with the blink(1). Useful to visually signal a connection loss or HA crash.

#### `blink1_status.enable_server_tickle`

Enable the watchdog. HA sends a keepalive at 50% of the configured timeout.

| Parameter | Type | Required | Range |
|-----------|------|----------|-------|
| `timeout_ms` | int | yes | 100–655350 |
| `start` | int | yes | 0–31 |
| `end` | int | yes | 0–31 (> start) |

```yaml
# If HA doesn't respond for 5 seconds, play the pattern at positions 0-2
service: blink1_status.enable_server_tickle
data:
  timeout_ms: 5000
  start: 0
  end: 2
```

```yaml
# Long timeout (30s) for monitoring
service: blink1_status.enable_server_tickle
data:
  timeout_ms: 30000
  start: 4
  end: 6
```

---

#### `blink1_status.disable_server_tickle`

Disable the watchdog and stop the keepalive task.

```yaml
service: blink1_status.disable_server_tickle
data: {}
```

---

### Diagnostics

#### `blink1_status.get_device_state`

Read the full device state in one call. Returns firmware version, current color, and playback state.

```yaml
service: blink1_status.get_device_state
data: {}
```

Response:
```json
{
  "firmware_version": "2.10",
  "current_color": { "r": 255, "g": 0, "b": 0 },
  "play_state": {
    "playing": false,
    "play_start": 0,
    "play_end": 0,
    "play_count": 0,
    "play_pos": 0
  }
}
```

---

## `led` Parameter (LED Targeting)

On blink(1) mk2+ devices, two LEDs are available:

| Value | Target |
|-------|--------|
| `0` | All LEDs (default) |
| `1` | Top LED |
| `2` | Bottom LED |

---

## Automation Examples

### Blink when a door opens

```yaml
automation:
  - alias: "Red blink on door open"
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door
        to: "on"
    action:
      - service: blink1_status.blink
        data:
          red: 255
          green: 0
          blue: 0
          count: 5
          fade_ms: 200
```

### Continuous status indicator with watchdog

```yaml
automation:
  - alias: "Enable blink(1) watchdog on HA start"
    trigger:
      - platform: homeassistant
        event: start
    action:
      # Write an alert pattern (red blinking) at positions 0-1
      - service: blink1_status.write_pattern
        data:
          pattern: "255,0,0,300;0,0,0,300"
      # Enable watchdog: if HA crashes, the red pattern plays
      - service: blink1_status.enable_server_tickle
        data:
          timeout_ms: 10000
          start: 0
          end: 2
```

### Weather color indicator

```yaml
automation:
  - alias: "Weather color on blink(1)"
    trigger:
      - platform: state
        entity_id: weather.home
    action:
      - choose:
          - conditions:
              - condition: state
                entity_id: weather.home
                state: "sunny"
            sequence:
              - service: blink1_status.blink
                data:
                  red: 255
                  green: 200
                  blue: 0
                  count: 2
          - conditions:
              - condition: state
                entity_id: weather.home
                state: "rainy"
            sequence:
              - service: blink1_status.blink
                data:
                  red: 0
                  green: 0
                  blue: 255
                  count: 2
```

---

## Credits

Based on the [blink(1) protocol](https://github.com/todbot/blink1/blob/main/docs/blink1-hid-commands.md).
