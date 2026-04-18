# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] — 2026-04-12

### Added
- Initial release
- Zabbix 7.0 JSON-RPC API integration with Bearer token auth
- 4-grayscale rendering on Waveshare 2.9" e-paper (296×128 landscape)
- Up to 8 alert cards with severity icon, host, problem, and age columns
- Smart text truncation with `.` ellipsis
- 7×7 pixel severity icons (circle, triangle, diamond, filled triangle, X-in-box)
- Sort by age (newest first) or severity (highest first)
- NTP time sync with configurable UTC offset
- Hash-based change detection — display refreshes only when data changes
- Error resilience — shows API ERR only after 5 consecutive failures
- Overflow indicator (`+N more`) when alerts exceed screen capacity
- Boot screen on mono display (fast refresh), then switches to 4-gray for dashboard
- `config.example.py` template for credentials
- `mip` installable via `package.json`
