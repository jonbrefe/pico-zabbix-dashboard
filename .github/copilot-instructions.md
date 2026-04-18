# Project Guidelines

## Overview

Raspberry Pi Pico W e-paper dashboard that polls **Zabbix 7.0** for active monitoring alerts and displays them on a 2.9" Waveshare e-paper screen. Refreshes only when data changes (hash-based comparison).

## Target Platform

- **Runtime**: MicroPython v1.28.0+ on RP2040 (Pico W)
- **Display**: Waveshare 2.9" CapTouch e-paper (296×128 px, SSD1680), SPI (RST=12, DC=8, CS=9, BUSY=13)
- **Network**: WiFi, polls Zabbix JSON-RPC API with Bearer token auth
- **Timezone**: UTC_OFFSET in config (e.g. -6 for Costa Rica), NTP sync at boot

## Dependencies

- **pico_paper_lib** — e-paper display library, installed via `mip` to `/lib/pico_paper_lib/` or uploaded manually
- **config.py** — credentials file (git-ignored, never commit). Use `config.example.py` as template.
- **package.json** — `mip` manifest for installing `main.py` and `config.example.py` from GitHub

## Code Style

- Pure MicroPython — no CPython-only features
- `const()` values are NOT importable across modules — use plain variables
- MicroPython v1.28.0 uses **Unix epoch (1970)** directly, NOT the old 2000 epoch
- All functions must have docstrings
- Config is a `Params` dict in `config.py`, accessed as `Params['KEY']`

## Architecture

```
main.py             → Boot: WiFi → NTP → poll loop → display
config.py           → Credentials + settings (git-ignored)
config.example.py   → Template for config.py
pico_paper_lib/     → Symlink to ../pico-paper-lib (display library)
```

### main.py structure

1. **Boot**: WiFi connect, NTP sync, show boot screen
2. **Poll loop**: `fetch_problems()` → `fetch_host_for_events()` → hash check → `draw_dashboard()`
3. **Clock sub-loop**: Between Zabbix polls, updates footer clock every `CLOCK_INTERVAL` (60s) via partial refresh
4. **Ghosting prevention**: After `PARTIAL_LIMIT` (5) partial refreshes, forces a full redraw
5. **Error handling**: 5 consecutive failures before showing API ERR on display
6. **KeyboardInterrupt**: `main()` is wrapped in `try/except KeyboardInterrupt` so Ctrl+C returns to REPL

### API requests

- `zabbix_api()` uses raw `socket.socket()` with `settimeout(10)` for HTTP POST (MicroPython's `urequests` has no timeout)
- Parses host/port/path from `ZABBIX_URL`, sends HTTP/1.0 request manually
- Returns parsed JSON result or `None` on error

## Conventions

- Zabbix 7.0 `problem.get` only supports a single `sortfield` — client-side sorting is used for multi-field sort (`SORT_BY` config: `'age'` or `'severity'`)
- Severity icons are 7×7 column-major bitmaps in `SEV_ICONS` dict
- Layout: COL_SEV=1, COL_HOST=10, COL_NAME=76, COL_AGE=W-36 (260), row height=9px
- Column headers use inverted bar (fill_rect BLACK + white text)
- Host text is centered within column; problem name is left-aligned
- Acknowledged alerts show a `badge('ACK')` next to the age column
- Status line shows IP on the left and `upd HH:MM` on the right (last Zabbix fetch time)
- Footer shows `mem:XXkB` (left), `HH:MM` clock (center), and `+N more` overflow count (right)
- Clock updates every 60s via partial refresh; full refresh every 5 partial updates to prevent ghosting
- `_CLOCK_X`, `_CLOCK_Y`, `_CLOCK_W`, `_CLOCK_H` define the partial-refresh region for the clock
- `update_clock(d)` clears the clock area and redraws with `d.refresh(full=False)`
- `time_ago()` outputs compact age strings: `5s`, `3min`, `2hr`, `4dy`

## Security

- **config.py** contains WiFi password and Zabbix API token — always git-ignored
- API token uses Bearer auth, not username/password
- Never hardcode credentials in main.py

## Installation

Install via `mip` (requires WiFi on the Pico):

```bash
# From pico-ctl/
python3 pico_ctl.py mip github:jonbrefe/pico-paper-lib
python3 pico_ctl.py mip github:jonbrefe/pico-zabbix-dashboard --target /
python3 pico_ctl.py upload config.py /config.py
```

## Testing

No automated tests. Test by uploading to Pico W:

```bash
# From pico-ctl/
python3 pico_ctl.py reset
python3 pico_ctl.py monitor
```

## License

MIT — Jonathan Brenes
