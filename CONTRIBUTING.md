# Contributing to pico-zabbix-dashboard

Thank you for your interest in contributing!

## Bug Reports

Open a GitHub issue with:

1. **What you expected** vs **what happened**
2. MicroPython version (`import sys; print(sys.version)`)
3. Zabbix version
4. Serial output from `pico_ctl monitor`

## Development Setup

```bash
git clone https://github.com/jonbrefe/pico-zabbix-dashboard.git
cd pico-zabbix-dashboard
cp config.example.py config.py
# Fill in your WiFi and Zabbix credentials in config.py
```

Testing requires a Pico W with [pico-paper-lib](https://github.com/jonbrefe/pico-paper-lib) installed and a reachable Zabbix instance.

## Code Style

- Pure MicroPython — no CPython-only features
- `const()` values cannot be imported across modules — use plain variables
- All functions must have docstrings
- Keep everything in `main.py` — no splitting into submodules

## Testing

No automated tests — all testing requires a physical Pico W with a Waveshare 2.9" e-paper and a Zabbix server.

Upload and monitor:

```bash
python3 pico_ctl.py upload main.py /main.py
python3 pico_ctl.py monitor
```

## Pull Requests

1. Fork the repo and create a feature branch
2. Keep changes focused — one feature or fix per PR
3. Never commit `config.py` (contains credentials)
4. Update `README.md` if adding user-facing features
5. Test against a physical Pico W with e-paper

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
