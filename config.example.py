# Copy this file to config.py and fill in your values.
# config.py is git-ignored (contains credentials).

Params = {
    'WIFI_SSID': 'YOUR_WIFI_SSID',
    'WIFI_Password': 'YOUR_WIFI_PASSWORD',
    'Port': 80,
    'ZABBIX_URL': 'http://YOUR_ZABBIX_IP/zabbix/api_jsonrpc.php',
    'ZABBIX_TOKEN': 'YOUR_ZABBIX_API_TOKEN',
    'POLL_INTERVAL': 60,       # seconds between Zabbix API polls
    'MAX_ALERTS': 12,          # max alerts to display
    'UTC_OFFSET': -6,          # timezone offset from UTC
    'SORT_BY': 'age',          # 'age' (newest first) or 'severity' (highest first)
}
