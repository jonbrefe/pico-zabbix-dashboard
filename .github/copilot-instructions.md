# Project Guidelines

## Overview

Raspberry Pi Pico W e-paper dashboard that polls **Zabbix 7.0** for active monitoring alerts and displays them on a 2.9" Waveshare e-paper screen. Refreshes only when data changes (hash-based comparison).

## Target Platform

- **Runtime**: MicroPython v1.28.0+ on RP2040 (Pico W)
- **Display**: Waveshare 2.9" CapTouch e-paper (296×128 px, SSD1680), SPI (RST=12, DC=8, CS=9, BUSY=13)
- **Network**: WiFi, polls Zabbix JSON-RPC API with Bearer token auth
- **Timezone**: UTC_OFFSET in config (e.g. -6 for Costa Rica), NTP sync at boot

## Dependencies

- **pico_paper_lib** — e-paper display library (symlinked as `pico_paper_lib/` → `../pico-paper-lib`)
- **config.py** — credentials file (git-ignored, never commit). Use `config.example.py` as template.

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
3. **Error handling**: 5 consecutive failures before showing API ERR on display

## Conventions

- Zabbix 7.0 `problem.get` only supports a single `sortfield` — client-side sorting is used for multi-field sort (`SORT_BY` config: `'age'` or `'severity'`)
- Severity icons are 7×7 column-major bitmaps in `SEV_ICONS` dict
- Layout: COL_SEV=1, COL_HOST=10, COL_NAME=76, COL_AGE=W-36 (260), row height=9px
- Column headers use inverted bar (fill_rect BLACK + white text)
- Host text is centered within column; problem name is left-aligned
- Acknowledged alerts show a `badge('ACK')` next to the age column
- Status line shows IP on the left and `upd HH:MM` on the right (last Zabbix fetch time)
- Footer shows `mem:XXkB` only
- `time_ago()` outputs compact age strings: `5s`, `3min`, `2hr`, `4dy`

## Security

- **config.py** contains WiFi password and Zabbix API token — always git-ignored
- API token uses Bearer auth, not username/password
- Never hardcode credentials in main.py

## Testing

No automated tests. Test by uploading to Pico W:

```bash
# From pico-ctl/
python3 pico_ctl.py upload --dir ../pico-paper-lib /pico_paper_lib
python3 pico_ctl.py upload ../pico-zabbix-dashboard/main.py /main.py ../pico-zabbix-dashboard/config.py /config.py
python3 pico_ctl.py run main.py --timeout 300
```

## License

MIT — Jonathan Brenes
