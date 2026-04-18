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

1. **Boot**: WiFi connect, NTP sync, show boot screen (mono `Display` for fast refresh)
2. **Switch**: Free mono display, create `Display4Gray` (landscape 296×128)
3. **Poll loop**: `fetch_problems()` → `fetch_host_for_events()` → hash check → `draw_dashboard()`
4. **Error handling**: 5 consecutive failures before showing API ERR on display
5. **KeyboardInterrupt**: `main()` is wrapped in `try/except KeyboardInterrupt` so Ctrl+C returns to REPL

### API requests

- `zabbix_api()` uses raw `socket.socket()` with `settimeout(10)` for HTTP POST (MicroPython's `urequests` has no timeout)
- Parses host/port/path from `ZABBIX_URL`, sends HTTP/1.0 request manually
- Returns parsed JSON result or `None` on error

## Conventions

- Zabbix 7.0 `problem.get` only supports a single `sortfield` — client-side sorting is used for multi-field sort (`SORT_BY` config: `'age'` or `'severity'`)
- Severity icons are 7×7 column-major bitmaps in `SEV_ICONS` dict
- Layout: COL_ICON=1, COL_HOST=10, COL_PROB=100, COL_AGE=W-2 (right-aligned), row height=11px (9px text + 1px separator + 1px padding)
- No column headers row — maximizes space for alert cards (8 visible)
- All text is rendered in `GRAY_BLACK`; grays are reserved for severity icons (`SEV_ICON_COLOR`) and separator lines
- Text truncation uses `.` ellipsis with `.rstrip()` to avoid trailing-space artifacts (e.g. `"Failed to fetch."` not `"Failed to fetch ."`)
- HOST_MAX=14 chars, PROB_MAX=25 chars, AGE_MAX=5 chars
- Acknowledged alerts show a `badge('A')` before the problem column
- Status line shows IP address only (left-aligned)
- Footer shows `mem:XXXK` (left), `HH:MM` clock (center), and `+N more` overflow count (right)
- Header shows `ZABBIX` (left, inverted) and `N alerts` (right, inverted)
- `time_ago()` outputs compact age strings: `5s`, `3m`, `2h`, `4d`
- 4-gray mode uses full refresh only (~3s); no partial refresh or clock sub-loop
- Display only refreshes when the alert data hash changes

## Security

- **config.py** contains WiFi password and Zabbix API token — always git-ignored
- API token uses Bearer auth, not username/password
- Never hardcode credentials in main.py

## Installation

For first-time setup on a blank Pico (no WiFi), upload directly via USB serial:

```bash
# From pico-ctl/
python3 pico_ctl.py upload --dir ../pico-paper-lib /lib/pico_paper_lib
python3 pico_ctl.py upload ../pico-zabbix-dashboard/main.py /main.py
python3 pico_ctl.py upload config.py /config.py
```

For updates when WiFi is already configured, `mip` works too:

```bash
python3 pico_ctl.py mip github:jonbrefe/pico-paper-lib
python3 pico_ctl.py mip github:jonbrefe/pico-zabbix-dashboard --target /
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
