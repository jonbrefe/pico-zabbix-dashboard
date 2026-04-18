"""Zabbix alert dashboard — 4-grayscale edition for Raspberry Pi Pico W.

Polls the Zabbix JSON-RPC API for active problems and renders them as
single-line cards on a Waveshare 2.9" e-paper using 4 gray levels for
severity differentiation.  Landscape orientation (296×128) with the
display mounted horizontally.

Boot sequence uses mono Display (fast refresh), then switches to
Display4Gray for the main dashboard loop.

Requires: pico_paper_lib, config.py with WiFi/Zabbix credentials.
"""
from machine import Pin
import network
import ujson
import time
import gc
import ntptime
from pico_paper_lib import Display, Display4Gray
from pico_paper_lib.display import (
    BLACK, WHITE,
    GRAY_BLACK, GRAY_DARKGRAY, GRAY_LIGHTGRAY, GRAY_WHITE,
)
from pico_paper_lib.fonts import font_small, font_medium
from config import Params

# --- Config ---
SSID = Params['WIFI_SSID']
PASSWORD = Params['WIFI_Password']
ZABBIX_URL = Params['ZABBIX_URL']
ZABBIX_TOKEN = Params['ZABBIX_TOKEN']
POLL_INTERVAL = Params['POLL_INTERVAL']
MAX_ALERTS = Params['MAX_ALERTS']
UTC_OFFSET = Params['UTC_OFFSET']
SORT_BY = Params.get('SORT_BY', 'age')  # 'age' or 'severity'

# Landscape dimensions (296 × 128)
W = 296
H = 128

# Layout constants (5x7 font: 6px/char wide, 9px row height)
RH = 9
HEADER_H = 11       # header bar
STATUS_Y = 12       # status line y
DATA_Y = 22         # first alert card y
CARD_H = 11         # single-line card + 1px separator
FOOTER_Y = H - 10   # 118
MAX_CARDS = (FOOTER_Y - DATA_Y) // CARD_H  # ~8

# Card column positions (landscape: 296px wide)
COL_ICON = 1        # severity icon x
COL_HOST = 10       # host name x
COL_PROB = 100      # problem text x
COL_AGE = W - 2     # age (right-aligned)
HOST_MAX = 14       # max chars for host
PROB_MAX = 25       # max chars for problem (leave room for age)
AGE_MAX = 5         # max chars for age (e.g. '226d')

# Severity → gray level for icon and text
SEV_ICON_COLOR = {
    0: GRAY_DARKGRAY,  1: GRAY_DARKGRAY,
    2: GRAY_DARKGRAY,  3: GRAY_DARKGRAY,
    4: GRAY_BLACK,      5: GRAY_BLACK,
}
SEV_TEXT_COLOR = {
    0: GRAY_BLACK,  1: GRAY_BLACK,
    2: GRAY_BLACK,  3: GRAY_BLACK,
    4: GRAY_BLACK,  5: GRAY_BLACK,
}

# Severity icons: 7×7 column-major bitmaps (LSB=top row)
SEV_ICONS = {
    0: b'\x1c\x22\x41\x41\x41\x22\x1c',  # circle (info)
    1: b'\x1c\x22\x41\x41\x41\x22\x1c',  # circle (info)
    2: b'\x60\x58\x46\x41\x46\x58\x60',  # triangle outline (warn)
    3: b'\x08\x1c\x3e\x7f\x3e\x1c\x08',  # filled diamond (avg)
    4: b'\x60\x78\x7e\x7f\x7e\x78\x60',  # filled triangle (high)
    5: b'\x7f\x63\x55\x49\x55\x63\x7f',  # X in box (disaster)
}

SEV_LABELS = {0: 'Info', 1: 'Info', 2: 'Warn', 3: 'Avg', 4: 'High', 5: 'DISA'}


def sync_ntp():
    """Sync RTC to NTP (UTC). Timezone applied only on display."""
    for attempt in range(3):
        try:
            ntptime.settime()
            t = time.localtime(time.time() + UTC_OFFSET * 3600)
            print('NTP synced, local:', '{:02d}:{:02d}:{:02d}'.format(t[3], t[4], t[5]))
            return True
        except Exception as e:
            print('NTP attempt', attempt + 1, 'failed:', e)
            time.sleep(2)
    print('NTP sync failed, using boot time')
    return False


def local_time():
    """Return localtime tuple adjusted for timezone."""
    return time.localtime(time.time() + UTC_OFFSET * 3600)


def wifi_connect():
    """Connect to WiFi using SSID/PASSWORD from config. Returns (wlan, ip)."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    for _ in range(20):
        if wlan.isconnected():
            break
        time.sleep(1)
    if not wlan.isconnected():
        raise RuntimeError('WiFi connection failed')
    ip = wlan.ifconfig()[0]
    print('WiFi connected:', ip)
    return wlan, ip


def zabbix_api(method, params):
    """Call Zabbix JSON-RPC API. Returns result dict or None on error."""
    import socket
    payload = ujson.dumps({
        'jsonrpc': '2.0',
        'method': method,
        'params': params,
        'id': 1
    })
    try:
        url = ZABBIX_URL
        proto, _, host_path = url.split('/', 2)
        host_port, path = host_path.split('/', 1)
        host = host_port.split(':')[0] if ':' in host_port else host_port
        port = int(host_port.split(':')[1]) if ':' in host_port else 80
        path = '/' + path

        addr = socket.getaddrinfo(host, port)[0][-1]
        s = socket.socket()
        s.settimeout(10)
        s.connect(addr)

        body = payload.encode()
        req = 'POST {} HTTP/1.0\r\nHost: {}\r\nContent-Type: application/json\r\nAuthorization: Bearer {}\r\nContent-Length: {}\r\n\r\n'.format(
            path, host, ZABBIX_TOKEN, len(body))
        s.send(req.encode())
        s.send(body)

        resp = b''
        while True:
            chunk = s.recv(1024)
            if not chunk:
                break
            resp += chunk
        s.close()

        parts = resp.split(b'\r\n\r\n', 1)
        data = ujson.loads(parts[1] if len(parts) > 1 else parts[0])
        if 'error' in data:
            print('Zabbix API error:', data['error'])
            return None
        return data.get('result')
    except Exception as e:
        print('Zabbix request failed:', e)
        return None


def fetch_problems():
    """Fetch active problems from Zabbix, sorted by SORT_BY config."""
    result = zabbix_api('problem.get', {
        'output': ['eventid', 'name', 'severity', 'clock', 'acknowledged'],
        'recent': True,
        'sortfield': ['eventid'],
        'sortorder': 'DESC',
        'limit': MAX_ALERTS,
        'suppressed': False,
    })
    if not result:
        return []
    if SORT_BY == 'severity':
        result.sort(key=lambda p: (int(p.get('severity', '0')), int(p.get('clock', '0'))), reverse=True)
    else:
        result.sort(key=lambda p: int(p.get('clock', '0')), reverse=True)
    return result


def fetch_host_for_events(event_ids):
    """Map event IDs to hostnames via Zabbix event.get."""
    if not event_ids:
        return {}
    result = zabbix_api('event.get', {
        'eventids': event_ids,
        'selectHosts': ['host'],
        'output': ['eventid'],
    })
    mapping = {}
    if result:
        for ev in result:
            hosts = ev.get('hosts', [])
            if hosts:
                mapping[ev['eventid']] = hosts[0]['host']
    return mapping


def time_ago(clock_str):
    """Convert Zabbix Unix timestamp to human-readable age."""
    try:
        diff = time.time() - int(clock_str)
    except:
        return '?'
    if diff < 0:
        return 'now'
    if diff < 120:
        return str(int(diff)) + 's'
    elif diff < 7200:
        return str(int(diff // 60)) + 'm'
    elif diff < 172800:
        return str(int(diff // 3600)) + 'h'
    else:
        return str(int(diff // 86400)) + 'd'


# ------------------------------------------------------------------
# 4-gray drawing helpers (landscape 296×128)
# ------------------------------------------------------------------

def draw_header(g, ip, n_problems, error=None):
    """Draw header bar + status line on the 4-gray display."""
    g.fill_rect(0, 0, W, HEADER_H, GRAY_BLACK)
    g.text('ZABBIX', 2, 2, GRAY_WHITE, font=font_medium)

    if error:
        g.text(error, 70, 2, GRAY_WHITE, font=font_medium)
    else:
        count = str(n_problems) + ' alerts'
        g.text_right(count, W - 2, 2, GRAY_WHITE, font=font_medium)

    # Status line: IP left
    g.text(ip, 2, STATUS_Y, GRAY_BLACK)

    # Divider
    g.hline(0, DATA_Y - 1, W, GRAY_BLACK)


def draw_alert_card(g, y, sev, host, name, age, ack):
    """Draw one single-line alert card at y position.

    Layout: [icon] host | problem text ... age
    """
    sev_int = int(sev) if isinstance(sev, str) else sev
    icon_color = SEV_ICON_COLOR.get(sev_int, GRAY_LIGHTGRAY)
    text_color = SEV_TEXT_COLOR.get(sev_int, GRAY_DARKGRAY)

    # Severity icon
    icon_data = SEV_ICONS.get(sev_int, SEV_ICONS[0])
    g.icon(icon_data, COL_ICON, y + 1, color=icon_color)

    # Host name (truncate with ellipsis)
    h = host[:HOST_MAX] if len(host) <= HOST_MAX else host[:HOST_MAX - 1].rstrip() + '.'
    g.text(h, COL_HOST, y + 1, text_color)

    # ACK badge
    if str(ack) == '1':
        g.badge('A', COL_PROB - 14, y, GRAY_DARKGRAY)

    # Problem name (truncate with ellipsis)
    n = name[:PROB_MAX] if len(name) <= PROB_MAX else name[:PROB_MAX - 1].rstrip() + '.'
    g.text(n, COL_PROB, y + 1, text_color)

    # Age (right-aligned)
    g.text_right(age[:AGE_MAX], COL_AGE, y + 1, GRAY_BLACK)

    # Card separator
    g.hline(0, y + CARD_H - 1, W, GRAY_DARKGRAY)


def draw_footer(g, overflow=0):
    """Draw footer bar with memory, clock, and overflow count."""
    gc.collect()
    mem = gc.mem_free()
    g.hline(0, FOOTER_Y - 2, W, GRAY_BLACK)
    g.text('mem:' + str(mem // 1024) + 'K', 2, FOOTER_Y, GRAY_BLACK)

    t = local_time()
    ts = '{:02d}:{:02d}'.format(t[3], t[4])
    g.text_centered(ts, W // 2, FOOTER_Y, GRAY_BLACK)

    if overflow > 0:
        g.text_right('+' + str(overflow) + ' more', W - 2, FOOTER_Y, GRAY_BLACK)


def draw_dashboard(g, ip, problems, hosts):
    """Render the full 4-gray dashboard."""
    g.clear()

    if not problems:
        draw_header(g, ip, 0)
        # "All clear" panel
        g.rect(60, 35, 176, 50, GRAY_DARKGRAY)
        g.fill_rect(61, 36, 174, 11, GRAY_DARKGRAY)
        g.text_centered('Status', W // 2, 37, GRAY_WHITE)
        g.text_centered('All clear!', W // 2, 55, GRAY_BLACK, font=font_medium)
        g.text_centered('No active problems.', W // 2, 70, GRAY_BLACK)
        draw_footer(g)
        g.refresh()
        return

    draw_header(g, ip, len(problems))

    card_y = DATA_Y
    overflow = 0
    card_idx = 0

    for p in problems:
        if card_y + CARD_H > FOOTER_Y - 2:
            overflow = len(problems) - card_idx
            break
        eid = p.get('eventid', '')
        host = hosts.get(eid, '???')
        name = p.get('name', '???')
        sev = p.get('severity', '0')
        age = time_ago(p.get('clock', '0'))
        ack = p.get('acknowledged', '0')
        draw_alert_card(g, card_y, sev, host, name, age, ack)
        card_y += CARD_H
        card_idx += 1

    draw_footer(g, overflow=overflow)
    g.refresh()


def main():
    """Boot sequence: WiFi connect, NTP sync, then 4-gray poll/display loop."""
    led = Pin('LED', Pin.OUT)
    led.value(1)

    # --- Boot screen (mono landscape — fast refresh) ---
    d = Display()
    d.clear()
    d.fill_rect(0, 0, 296, 11, BLACK)
    d.text('ZABBIX', 2, 2, WHITE, font=font_medium)
    d.text('booting...', 296 - font_medium.text_width('booting...') - 2, 2, WHITE, font=font_medium)
    d.bordered_panel(30, 25, 236, 45, title='Connecting', radius=3)
    d.text_centered('WiFi: ' + SSID, 148, 48)
    d.refresh()

    wlan, ip = wifi_connect()
    sync_ntp()
    led.value(0)

    # Show connected screen
    d.clear()
    d.fill_rect(0, 0, 296, 11, BLACK)
    d.text('ZABBIX', 2, 2, WHITE, font=font_medium)
    d.bordered_panel(30, 25, 236, 45, title='Connected', radius=3)
    d.text_centered(ip, 148, 42)
    d.text_centered('Switching to 4-gray...', 148, 55)
    d.refresh()

    # Free mono display, switch to 4-gray landscape
    del d
    gc.collect()
    print('Switching to 4-gray mode')
    g = Display4Gray()

    last_data_hash = None
    consecutive_errors = 0

    while True:
        led.value(1)
        gc.collect()

        problems = fetch_problems()

        if problems is None:
            consecutive_errors += 1
            print('Fetch error #', consecutive_errors)
            if consecutive_errors >= 5:
                g.clear()
                draw_header(g, ip, 0, error='API ERR')
                g.text_centered('Cannot reach Zabbix API', W // 2, 60, GRAY_BLACK, font=font_medium)
                g.text_centered('Retrying...', W // 2, 80, GRAY_BLACK)
                draw_footer(g)
                g.refresh()
            led.value(0)
            time.sleep(POLL_INTERVAL)
            continue

        consecutive_errors = 0

        event_ids = [p['eventid'] for p in problems]
        hosts = fetch_host_for_events(event_ids)

        data_hash = str([(p['eventid'], p['severity']) for p in problems])
        if data_hash != last_data_hash:
            draw_dashboard(g, ip, problems, hosts)
            last_data_hash = data_hash
            print('Display updated:', len(problems), 'problems')
        else:
            print('No change, skipping refresh')

        led.value(0)
        gc.collect()
        print('Free mem:', gc.mem_free())
        time.sleep(POLL_INTERVAL)


try:
    main()
except KeyboardInterrupt:
    Pin('LED', Pin.OUT).value(0)
    print('\nInterrupted – returning to REPL')
