"""Zabbix alert dashboard for Raspberry Pi Pico W with 2.9" e-paper display.

Polls the Zabbix JSON-RPC API for active problems and renders them as a
compact table on a Waveshare SSD1680 e-paper.  The display refreshes only
when the alert data changes (hash-based comparison).

Requires: pico_paper_lib, config.py with WiFi/Zabbix credentials.
"""
from machine import Pin
import network
import urequests
import ujson
import time
import gc
import ntptime
from pico_paper_lib import Display
from pico_paper_lib.display import BLACK, WHITE
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

# Partial-refresh safety: full refresh every N partial updates to clear ghosting
PARTIAL_LIMIT = 5
# Clock update interval in seconds (between Zabbix polls)
CLOCK_INTERVAL = 60

# Severity icons: 7 wide x 7 tall, column-major bitmaps (LSB=top row)
# 0/1: Info - open circle
# 2: Warning - triangle outline
# 3: Average - filled diamond
# 4: High - filled triangle
# 5: Disaster - X in filled box
SEV_ICONS = {
    0: b'\x1c\x22\x41\x41\x41\x22\x1c',  # circle
    1: b'\x1c\x22\x41\x41\x41\x22\x1c',  # circle
    2: b'\x60\x58\x46\x41\x46\x58\x60',  # triangle outline
    3: b'\x08\x1c\x3e\x7f\x3e\x1c\x08',  # filled diamond
    4: b'\x60\x78\x7e\x7f\x7e\x78\x60',  # filled triangle
    5: b'\x7f\x63\x55\x49\x55\x63\x7f',  # X in box
}

# Display: 296 x 128 landscape (from Display object)
W = 296
H = 128

# Layout constants (5x7 font: 6px/char wide, 9px row height)
CW = font_small.cell_w
RH = 9
# Column positions
COL_SEV = 1
COL_HOST = 10
COL_NAME = 76
COL_AGE = W - 36
# Max chars per column
HOST_MAX = 10
NAME_MAX = 30
AGE_MAX = 5

# Column widths for layout
_HOST_W = COL_NAME - COL_HOST       # 66
_NAME_W = COL_AGE - COL_NAME        # 184
_AGE_W = W - COL_AGE                # 36

# Severity labels for badges
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
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + ZABBIX_TOKEN
    }
    try:
        # Parse host/port from URL for raw socket with timeout
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

        # Read response
        resp = b''
        while True:
            chunk = s.recv(1024)
            if not chunk:
                break
            resp += chunk
        s.close()

        # Split headers and body
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
    """Fetch active problems from Zabbix, sorted by SORT_BY config.

    Returns a list of problem dicts, or None on API error.
    Zabbix 7.0 only supports single sortfield, so we sort client-side.
    """
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
    """Map event IDs to hostnames via Zabbix event.get. Returns {eventid: hostname}."""
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
        now_unix = time.time()
        diff = now_unix - int(clock_str)
    except:
        return '?'
    if diff < 0:
        return 'now'
    if diff < 120:
        return str(int(diff)) + 's'
    elif diff < 7200:
        return str(int(diff // 60)) + 'min'
    elif diff < 172800:
        return str(int(diff // 3600)) + 'hr'
    else:
        d = int(diff // 86400)
        return str(d) + 'dy'


def draw_header(d, ip, n_problems, error=None):
    """Draw the inverted header bar with title, alert count, IP, and time."""
    # Black header bar
    d.fill_rect(0, 0, W, 11, BLACK)
    d.text('ZABBIX', 2, 2, WHITE, font=font_medium)

    if error:
        d.text(error, 56, 2, WHITE)
    else:
        # Alert count badge
        count_text = str(n_problems) + ' active'
        d.text(count_text, W - font_medium.text_width(count_text) - 2, 2, WHITE, font=font_medium)

    # Status line: IP left, last-update time right
    y = 13
    d.text(ip, 2, y)
    t = local_time()
    ts = 'upd {:02d}:{:02d}'.format(t[3], t[4])
    d.text_right(ts, W - 1, y)
    d.hline(0, y + 8, W)


def draw_col_headers(d, y):
    """Draw inverted column header bar at y."""
    d.fill_rect(0, y, W, RH, BLACK)
    d.text_in_rect('Host', COL_HOST, y, _HOST_W, RH, WHITE, align='center', valign='middle')
    d.text_in_rect('Problem', COL_NAME, y, _NAME_W, RH, WHITE, align='center', valign='middle')
    d.text_in_rect('Age', COL_AGE, y, _AGE_W, RH, WHITE, align='center', valign='middle')


def draw_alert_row(d, y, sev, host, name, age, ack, row_idx):
    """Draw one alert row with severity icon, host, problem, age, and ACK badge."""
    sev_int = int(sev) if isinstance(sev, str) else sev

    # Draw severity icon
    icon = SEV_ICONS.get(sev_int, SEV_ICONS[0])
    d.icon(icon, COL_SEV, y + 1)

    # Host — centered in column
    h = host[:HOST_MAX]
    d.text_in_rect(h, COL_HOST, y, _HOST_W, RH, align='center', valign='middle')

    # Problem name — left-aligned for readability
    n = name[:NAME_MAX]
    d.text(n, COL_NAME + 2, y + 1)

    # Age — right-aligned
    a = age[:AGE_MAX]
    d.text_right(a, W - 2, y + 1)

    # Acknowledged badge
    if str(ack) == '1':
        d.badge('ACK', COL_AGE - 22, y + 1)


def draw_footer(d, overflow=0):
    """Draw a footer bar with memory info, centered clock, and overflow count."""
    gc.collect()
    mem = gc.mem_free()
    y = H - 9
    d.hline(0, y - 3, W)
    d.text('mem:' + str(mem // 1024) + 'KB', 2, y)
    # Clock in center
    t = local_time()
    ts = '{:02d}:{:02d}'.format(t[3], t[4])
    d.text_centered(ts, W // 2, y)
    # Overflow count in bottom-right
    if overflow > 0:
        d.text_right('+' + str(overflow) + ' more', W - 2, y)


# Clock region: center of footer where HH:MM is drawn
_CLOCK_W = 5 * CW + 2        # 5 chars * cell_width + small margin
_CLOCK_X = (W - _CLOCK_W) // 2
_CLOCK_Y = H - 9
_CLOCK_H = 9


def update_clock(d):
    """Partial-refresh only the clock region in the footer."""
    t = local_time()
    ts = '{:02d}:{:02d}'.format(t[3], t[4])
    # Clear clock area and redraw
    d.fill_rect(_CLOCK_X, _CLOCK_Y, _CLOCK_W, _CLOCK_H, WHITE)
    d.text_centered(ts, W // 2, _CLOCK_Y)
    d.refresh(full=False)
    print('Clock:', ts)


def draw_dashboard(d, ip, problems, hosts):
    """Render the full dashboard: header, column headers, alert rows, and footer."""
    d.clear()

    if not problems:
        draw_header(d, ip, 0)
        d.bordered_panel(30, 35, 236, 55, title='Status', radius=3)
        d.text_centered('All clear!', W // 2, 55, font=font_medium)
        d.text_centered('No active problems.', W // 2, 68)
        draw_footer(d)
        d.refresh()
        return

    draw_header(d, ip, len(problems))

    header_y = 23
    draw_col_headers(d, header_y)

    row_y = header_y + RH + 1
    max_row_y = H - 12  # leave room for footer bar
    row_idx = 0
    overflow = 0
    for p in problems:
        if row_y + RH > max_row_y:
            overflow = len(problems) - row_idx
            break
        eid = p.get('eventid', '')
        host = hosts.get(eid, '???')
        name = p.get('name', '???')
        sev = p.get('severity', '0')
        age = time_ago(p.get('clock', '0'))
        ack = p.get('acknowledged', '0')
        draw_alert_row(d, row_y, sev, host, name, age, ack, row_idx)
        row_y += RH
        row_idx += 1

    draw_footer(d, overflow=overflow)
    d.refresh()


def main():
    """Boot sequence: WiFi connect, NTP sync, then poll/display loop."""
    led = Pin('LED', Pin.OUT)
    led.value(1)

    d = Display()
    d.clear()
    d.fill_rect(0, 0, W, 11, BLACK)
    d.text('ZABBIX', 2, 2, WHITE, font=font_medium)
    d.text('booting...', W - font_medium.text_width('booting...') - 2, 2, WHITE, font=font_medium)
    d.bordered_panel(30, 25, 236, 45, title='Connecting', radius=3)
    d.text_centered('WiFi: ' + SSID, W // 2, 48)
    d.refresh()

    wlan, ip = wifi_connect()
    sync_ntp()
    led.value(0)

    d.clear()
    d.fill_rect(0, 0, W, 11, BLACK)
    d.text('ZABBIX', 2, 2, WHITE, font=font_medium)
    d.bordered_panel(30, 25, 236, 45, title='Connected', radius=3)
    d.text_centered(ip, W // 2, 42)
    d.text_centered('Fetching alerts...', W // 2, 55)
    d.refresh()

    last_data_hash = None
    consecutive_errors = 0
    partial_count = 0          # partial refreshes since last full refresh
    last_problems = None       # cached for forced full-refresh redraw
    last_hosts = None

    while True:
        led.value(1)
        gc.collect()

        problems = fetch_problems()

        if problems is None:
            consecutive_errors += 1
            print('Fetch error #', consecutive_errors)
            if consecutive_errors >= 5:
                d.clear()
                draw_header(d, ip, 0, error='API ERR')
                d.bordered_panel(30, 30, 236, 55, title='Error', radius=3)
                d.text_centered('Cannot reach Zabbix API', W // 2, 50)
                d.text_centered('Retrying every ' + str(POLL_INTERVAL) + 's...', W // 2, 62)
                draw_footer(d)
                d.refresh()
                partial_count = 0
            led.value(0)
            time.sleep(POLL_INTERVAL)
            continue

        consecutive_errors = 0

        event_ids = [p['eventid'] for p in problems]
        hosts = fetch_host_for_events(event_ids)

        data_hash = str([(p['eventid'], p['severity']) for p in problems])
        if data_hash != last_data_hash:
            draw_dashboard(d, ip, problems, hosts)
            last_data_hash = data_hash
            partial_count = 0  # full refresh resets counter
            print('Display updated:', len(problems), 'problems')
        else:
            print('No change, skipping display refresh')

        last_problems = problems
        last_hosts = hosts

        led.value(0)
        gc.collect()
        print('Free mem:', gc.mem_free())

        # Between polls: tick the clock every CLOCK_INTERVAL seconds.
        # After PARTIAL_LIMIT partial updates, force a full refresh.
        elapsed = 0
        while elapsed < POLL_INTERVAL:
            time.sleep(CLOCK_INTERVAL)
            elapsed += CLOCK_INTERVAL

            if partial_count >= PARTIAL_LIMIT:
                # Ghosting prevention: full redraw
                print('Full refresh (ghosting prevention)')
                if last_problems is not None:
                    draw_dashboard(d, ip, last_problems, last_hosts)
                else:
                    d.refresh(full=True)
                partial_count = 0
            else:
                update_clock(d)
                partial_count += 1


try:
    main()
except KeyboardInterrupt:
    Pin('LED', Pin.OUT).value(0)
    print('\nInterrupted – returning to REPL')
