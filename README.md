# pico-zabbix-dashboard

A **Raspberry Pi Pico W** e-paper dashboard that displays active Zabbix monitoring alerts. Polls the Zabbix API on a configurable interval and renders a compact alert table on a 2.9" Waveshare e-paper display.

## Features

- Pulls active problems from **Zabbix 7.0** via JSON-RPC API with Bearer token auth
- **4-grayscale rendering** — black text, dark-gray severity icons, gray separators on white
- Displays up to **8 alerts** in landscape (296×128) with severity icon, host, problem, and age
- **Smart truncation** — text cut with `.` ellipsis, trailing spaces stripped for clean display
- **Severity icons**: pixel-art bitmaps (circle, triangle, diamond, filled triangle, X-in-box)
- **Sort modes**: by age (newest first) or severity (highest first)
- **NTP time sync** with configurable UTC offset
- **Hash-based change detection** — only refreshes the display when data changes
- **Error resilience** — shows "API ERR" on display only after 5 consecutive failures
- **Overflow indicator** — "+N more" in footer when alerts exceed screen capacity
- Built on [pico-paper-lib](https://github.com/jonbrefe/pico-paper-lib) for display rendering

## Hardware

| Component | Details |
|-----------|---------|
| MCU | Raspberry Pi Pico W (RP2040, MicroPython v1.28.0) |
| Display | Waveshare 2.9" CapTouch e-paper (296×128 px, SSD1680) |
| Connection | SPI — RST=12, DC=8, CS=9, BUSY=13 |

## Dependencies

This project needs the following on the Pico's filesystem:

- **`pico_paper_lib/`** — The [pico-paper-lib](https://github.com/jonbrefe/pico-paper-lib) library (includes fonts)
- **`config.py`** — Your WiFi and Zabbix credentials (see below)

## Setup

### 1. Flash MicroPython

Flash MicroPython v1.28.0+ onto your Pico W. Download from [micropython.org](https://micropython.org/download/RPI_PICO_W/).

### 2. Install everything via `mip` (recommended)

Install the library and the dashboard with [pico-ctl](https://github.com/jonbrefe/pico-ctl):

```bash
# Install the display library (to /lib/)
python3 pico_ctl.py mip github:jonbrefe/pico-paper-lib

# Install the dashboard (main.py + config.example.py to /)
python3 pico_ctl.py mip github:jonbrefe/pico-zabbix-dashboard --target /
```

### 3. Create and upload config.py

Copy the example config, fill in your WiFi and Zabbix credentials, then upload:

```bash
cp config.example.py config.py
```

```python
Params = {
    'WIFI_SSID': 'MyNetwork',
    'WIFI_Password': 'MyPassword',
    'Port': 80,
    'ZABBIX_URL': 'http://192.168.1.10/zabbix/api_jsonrpc.php',
    'ZABBIX_TOKEN': 'your-zabbix-api-token',
    'POLL_INTERVAL': 60,
    'MAX_ALERTS': 12,
    'UTC_OFFSET': -6,
    'SORT_BY': 'age',
}
```

```bash
python3 pico_ctl.py upload config.py /config.py
```

> **Note**: `config.py` is git-ignored. Never commit credentials.

### Alternative: Manual install

Install the library and upload files separately:

```bash
# Install pico-paper-lib
python3 pico_ctl.py mip github:jonbrefe/pico-paper-lib

# Upload dashboard files
python3 pico_ctl.py upload ../pico-zabbix-dashboard/main.py /main.py ../pico-zabbix-dashboard/config.py /config.py
```

### 4. Verify

```bash
# Verify it boots correctly
python3 pico_ctl.py run main.py --timeout 300
```

### 5. Create a Zabbix API Token

In Zabbix web UI: **User settings → API tokens → Create API token**.  
Give it read permissions for `problem.get` and `host.get`.

## Files

| File | Runs on | Description |
|------|---------|-------------|
| `main.py` | Pico | Main application — WiFi connect, NTP sync, Zabbix poll loop, display rendering |
| `config.py` | Pico | Credentials and settings (git-ignored) |
| `config.example.py` | — | Template for config.py |
| `pico_paper_lib/` | Pico | Symlink → ../pico-paper-lib (for local dev). Upload the actual library contents to Pico. |

## Display Layout

```
+--------------------------------------------------+
|##ZABBIX##############################12 alerts##| <- inverted header
| 192.168.27.80                                    | <- IP address
+--------------------------------------------------+
| * RT-AX88U  Interface eth4: Link down        9d  |
| * RT-AX88U  Interface eth1: Link down       44d  |
| * towerbridge  Zabbix agent is not avai.    96d  |
| ^ endeavour Docker: Failed to fetch.       226d  |
| ...                                              |
+--------------------------------------------------+
| mem:149K              13:51           +4 more    | <- footer
+--------------------------------------------------+
```

> `##` = inverted (white-on-black) regions.
> Uses 4-grayscale mode (full refresh only, ~3s per update).
> Display refreshes only when alert data changes.

- **Icon column (1–9px)**: 7×7 pixel severity icons (dark gray for low, black for high/disaster)
- **Host column (10–99px)**: Hostname, max 14 chars, truncated with `.`
- **Problem column (100–260px)**: Problem description, max 25 chars, truncated with `.`
- **Age column (right-aligned)**: Time since alert (e.g. `5s`, `3m`, `2h`, `9d`), max 5 chars
- **ACK badge**: Acknowledged alerts show `A` badge before the problem column
- **Status line**: IP address of the Pico
- **Footer**: `mem:XXXK` (left), `HH:MM` clock (center), `+N more` overflow (right)

## Configuration Options

| Key | Default | Description |
|-----|---------|-------------|
| `POLL_INTERVAL` | `60` | Seconds between Zabbix API polls |
| `MAX_ALERTS` | `12` | Maximum alerts shown on display |
| `UTC_OFFSET` | `-6` | Timezone offset (e.g. -6 for CST) |
| `SORT_BY` | `'age'` | `'age'` = newest first, `'severity'` = highest severity first |

## MicroPython Notes

- **Epoch**: MicroPython v1.28.0 uses Unix epoch (1970), not the old 2000 epoch
- **`const()`**: Values defined with `const()` cannot be imported across modules — plain variables are used instead
- **Memory**: ~163KB free after loading all modules (plenty of headroom)
- **Display refresh**: 4-gray full refresh takes ~3 seconds; only triggered when alert data changes

## Copilot Instructions

The `.github/copilot-instructions.md` file provides project-specific context to GitHub Copilot. It describes the Zabbix JSON-RPC integration, MicroPython conventions (`const()` limitations, Unix epoch), display layout constants, UI rendering approach (inverted headers, badges, bordered panels), and the config/credentials pattern. This helps Copilot generate MicroPython code that correctly uses the Zabbix API and `pico_paper_lib` display features.

## License

MIT — Jonathan Brenes
