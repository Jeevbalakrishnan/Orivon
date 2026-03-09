#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║   ORIVON — AI Digital Addiction Early Warning System     ║
║   Python Desktop App — Real Detection + Force Close      ║
╚══════════════════════════════════════════════════════════╝

When time limit hits, Orivon ACTUALLY closes the window:
  • Windows  — PostMessage(WM_CLOSE) via win32gui
  • macOS    — AppleScript: close current tab in browser
  • Linux    — xdotool windowclose <window_id>

If window close fails → kills browser process via psutil.

Run:  python orivon_monitor.py
Deps: pip install plyer psutil
      Windows extra: pip install pywin32
      Linux extra:   sudo apt install xdotool
"""

import sys, os, time, threading, subprocess, platform
from datetime import datetime

# ── Optional imports ──────────────────────────────────────
try:
    from plyer import notification
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

PLATFORM = platform.system()   # 'Windows' | 'Darwin' | 'Linux'

# ── Configuration ─────────────────────────────────────────
THRESHOLDS    = {'reminder': 30, 'warning': 50, 'block': 60}
LOCK_DURATION = 300   # 5 minutes

WATCHED_APPS = [
    {'id': 'youtube',   'name': 'YouTube',   'icon': '▶ ',
     'patterns': ['youtube.com', '- youtube', '– youtube']},
    {'id': 'instagram', 'name': 'Instagram', 'icon': '📸',
     'patterns': ['instagram.com', 'instagram']},
    {'id': 'facebook',  'name': 'Facebook',  'icon': '👥',
     'patterns': ['facebook.com', 'facebook']},
    {'id': 'tiktok',    'name': 'TikTok',    'icon': '🎵',
     'patterns': ['tiktok.com', 'tiktok']},
    {'id': 'twitter',   'name': 'Twitter/X', 'icon': '🐦',
     'patterns': ['twitter.com', 'x.com']},
    {'id': 'reddit',    'name': 'Reddit',    'icon': '🤖',
     'patterns': ['reddit.com', 'reddit']},
    {'id': 'twitch',    'name': 'Twitch',    'icon': '🎮',
     'patterns': ['twitch.tv', 'twitch']},
    {'id': 'netflix',   'name': 'Netflix',   'icon': '🎬',
     'patterns': ['netflix.com', 'netflix']},
]

SITE_DOMAINS = {
    'youtube':   'youtube.com',
    'instagram': 'instagram.com',
    'facebook':  'facebook.com',
    'tiktok':    'tiktok.com',
    'twitter':   'twitter.com',
    'reddit':    'reddit.com',
    'twitch':    'twitch.tv',
    'netflix':   'netflix.com',
}

BROWSER_PROCESS_NAMES = ['chrome', 'chromium', 'firefox', 'firefox-esr',
                          'brave', 'msedge', 'opera', 'safari', 'vivaldi']

# ── State ─────────────────────────────────────────────────
class OrivonState:
    def __init__(self):
        self.sessions   = {}
        self.locks      = {}
        self.active_app = None
        self.log        = []
        self.running    = True
        self._lock      = threading.Lock()

    def session(self, app_id):
        if app_id not in self.sessions:
            self.sessions[app_id] = {'elapsed': 0, 'warn_state': 'normal'}
        return self.sessions[app_id]

    def is_locked(self, app_id):
        exp = self.locks.get(app_id)
        if not exp: return False
        if time.time() < exp: return True
        del self.locks[app_id]
        return False

    def lock_app(self, app_id):
        self.locks[app_id] = time.time() + LOCK_DURATION

    def remaining(self, app_id):
        return max(0, int(self.locks.get(app_id, 0) - time.time()))

    def add_log(self, text, level='info'):
        self.log.insert(0, {
            'time':  datetime.now().strftime('%H:%M:%S'),
            'text':  text,
            'level': level
        })
        if len(self.log) > 200:
            self.log = self.log[:200]

S = OrivonState()

# ══════════════════════════════════════════════════════════
#  WINDOW DETECTION
# ══════════════════════════════════════════════════════════

def get_active_window():
    """Returns (title_lowercase, handle_or_id)."""
    try:
        if PLATFORM == 'Windows':
            import win32gui
            hwnd  = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd).lower()
            return title, hwnd

        elif PLATFORM == 'Darwin':
            script = '''
tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
    set winTitle to ""
    try
        set winTitle to name of front window of process frontApp
    end try
    return frontApp & "|||" & winTitle
end tell'''
            out   = subprocess.run(['osascript', '-e', script],
                                   capture_output=True, text=True, timeout=3)
            parts = out.stdout.strip().split('|||')
            app_n = parts[0].strip() if parts else ''
            win_t = parts[1].strip() if len(parts) > 1 else ''
            return (app_n + ' ' + win_t).lower(), app_n

        elif PLATFORM == 'Linux':
            wid = subprocess.run(['xdotool', 'getactivewindow'],
                                 capture_output=True, text=True, timeout=2).stdout.strip()
            if not wid: return '', None
            title = subprocess.run(['xdotool', 'getwindowname', wid],
                                   capture_output=True, text=True, timeout=2).stdout.strip().lower()
            return title, wid

    except Exception:
        pass
    return '', None


def match_app(title):
    for app in WATCHED_APPS:
        for pat in app['patterns']:
            if pat in title:
                return app
    return None


# ══════════════════════════════════════════════════════════
#  FORCE CLOSE  ← THE MAIN FIX
# ══════════════════════════════════════════════════════════

def force_close_window(app, handle):
    """
    Closes the browser window/tab using platform-specific methods.
    Falls back to killing the browser process if needed.
    """
    print(f"\n  💥 FORCE CLOSING {app['name']}...")
    closed = False

    # ── WINDOWS ──────────────────────────────────────────
    if PLATFORM == 'Windows':
        # Method 1: Send WM_CLOSE to window handle
        try:
            import win32gui, win32con
            if handle:
                win32gui.PostMessage(handle, win32con.WM_CLOSE, 0, 0)
                time.sleep(0.5)
                # Check if window still exists
                if not win32gui.IsWindow(handle):
                    closed = True
                    print(f"  ✅ Window closed via WM_CLOSE")
        except Exception as e:
            print(f"  ⚠ WM_CLOSE failed: {e}")

        # Method 2: Ctrl+W to close current tab
        if not closed:
            try:
                import pyautogui
                pyautogui.hotkey('ctrl', 'w')
                closed = True
                print("  ✅ Tab closed via Ctrl+W")
            except Exception:
                pass

    # ── macOS ─────────────────────────────────────────────
    elif PLATFORM == 'Darwin':
        browser_app = handle or 'Google Chrome'

        # Method 1: AppleScript close tab for known browsers
        close_scripts = {
            'Google Chrome':    'tell application "Google Chrome" to close active tab of front window',
            'Chromium':         'tell application "Chromium" to close active tab of front window',
            'Brave Browser':    'tell application "Brave Browser" to close active tab of front window',
            'Microsoft Edge':   'tell application "Microsoft Edge" to close active tab of front window',
            'Safari':           'tell application "Safari" to close current tab of front window',
            'Firefox':          'tell application "System Events" to keystroke "w" using command down',
        }

        script = close_scripts.get(browser_app)
        if not script:
            # Generic: try Cmd+W
            script = 'tell application "System Events" to keystroke "w" using command down'

        try:
            result = subprocess.run(['osascript', '-e', script],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                closed = True
                print(f"  ✅ Tab closed via AppleScript ({browser_app})")
        except Exception as e:
            print(f"  ⚠ AppleScript failed: {e}")

        # Method 2: Cmd+W keystroke fallback
        if not closed:
            try:
                subprocess.run(['osascript', '-e',
                    'tell application "System Events" to keystroke "w" using command down'],
                    timeout=3)
                closed = True
                print("  ✅ Tab closed via Cmd+W")
            except Exception:
                pass

    # ── LINUX ─────────────────────────────────────────────
    elif PLATFORM == 'Linux':
        wid = handle

        # Method 1: xdotool windowclose (graceful ICCCM close)
        if wid:
            try:
                r = subprocess.run(['xdotool', 'windowclose', wid],
                                   capture_output=True, timeout=3)
                if r.returncode == 0:
                    closed = True
                    print(f"  ✅ Window {wid} closed via xdotool windowclose")
            except Exception as e:
                print(f"  ⚠ xdotool windowclose failed: {e}")

        # Method 2: Ctrl+W to close tab
        if not closed and wid:
            try:
                subprocess.run(['xdotool', 'key', '--window', wid, 'ctrl+w'], timeout=3)
                closed = True
                print("  ✅ Tab closed via xdotool Ctrl+W")
            except Exception as e:
                print(f"  ⚠ Ctrl+W failed: {e}")

        # Method 3: wmctrl
        if not closed and wid:
            try:
                subprocess.run(['wmctrl', '-ic', wid], timeout=3)
                closed = True
                print("  ✅ Window closed via wmctrl -ic")
            except Exception as e:
                print(f"  ⚠ wmctrl failed: {e}")

    # ── NUCLEAR FALLBACK: kill browser process ─────────────
    if not closed:
        print(f"  ⚡ Falling back to process kill...")
        _kill_browser_process(app)


def _kill_browser_process(app):
    """
    Finds browser processes whose command-line arguments contain
    the site's domain and kills them.
    """
    if not HAS_PSUTIL:
        print(f"  ⚠ psutil not installed — cannot kill process.")
        print(f"    Install with: pip install psutil")
        return

    domain  = SITE_DOMAINS.get(app['id'], '')
    killed  = 0

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name    = (proc.info['name'] or '').lower()
            cmdline = ' '.join(proc.info['cmdline'] or []).lower()
            is_browser = any(b in name for b in BROWSER_PROCESS_NAMES)
            has_site   = domain in cmdline if domain else False

            if is_browser and has_site:
                proc.kill()
                killed += 1
                print(f"  💀 Killed: {proc.info['name']} PID {proc.info['pid']}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if killed:
        print(f"  ✅ Killed {killed} browser process(es) for {app['name']}")
    else:
        # Last resort: just kill ALL browser windows
        print(f"  ⚠ No domain-specific process found.")
        print(f"    Sending close to ALL browser windows with '{app['name']}' in title...")
        _close_all_matching_windows(app)


def _close_all_matching_windows(app):
    """Linux/macOS: close every window whose title matches the app."""
    if PLATFORM == 'Linux':
        try:
            # List all windows
            out = subprocess.run(['xdotool', 'search', '--name', app['patterns'][0]],
                                 capture_output=True, text=True, timeout=3)
            for wid in out.stdout.strip().splitlines():
                try:
                    subprocess.run(['xdotool', 'windowclose', wid], timeout=2)
                    print(f"  💀 Closed window {wid}")
                except Exception:
                    pass
        except Exception:
            pass
    elif PLATFORM == 'Darwin':
        try:
            script = f'''
tell application "System Events"
    set procs to every application process whose name contains "Chrome" or name contains "Firefox" or name contains "Safari"
    repeat with p in procs
        repeat with w in (every window of p)
            if name of w contains "{app['name']}" then
                tell p to close w
            end if
        end repeat
    end repeat
end tell'''
            subprocess.run(['osascript', '-e', script], timeout=5)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════
#  LOCK ENFORCEMENT THREAD
#  Re-closes the window every 2s if user tries to reopen
# ══════════════════════════════════════════════════════════

def lock_enforcement_loop(app_id):
    """
    Background thread: while app_id is locked, continuously
    checks if the user opened it again and closes it immediately.
    """
    app = next((a for a in WATCHED_APPS if a['id'] == app_id), None)
    if not app:
        return

    print(f"\n  🛡  Lock enforcement active for {app['name']}")

    while S.is_locked(app_id):
        time.sleep(2)
        title, handle = get_active_window()
        matched = match_app(title)
        if matched and matched['id'] == app_id:
            rem = S.remaining(app_id)
            print(f"\n  🚫 {app['name']} re-opened while locked! "
                  f"Force closing again... ({fmt(rem)} remaining)")
            S.add_log(f"Re-open blocked: {app['name']} — force closed again", 'danger')
            notify('🚫 Orivon — Still Locked!',
                   f"{app['name']} closed again. {fmt(rem)} remaining.",
                   urgency='critical')
            force_close_window(app, handle)

    # Lock expired — reset session
    sess = S.session(app_id)
    sess['elapsed']    = 0
    sess['warn_state'] = 'normal'
    S.add_log(f"{app['name']} unlocked — session reset", 'success')
    print(f"\n  ✅ {app['name']} is now UNLOCKED. Timer reset.")


# ══════════════════════════════════════════════════════════
#  NOTIFICATIONS
# ══════════════════════════════════════════════════════════

def notify(title, message, urgency='normal'):
    symbol = '🔔' if urgency == 'normal' else '🚨'
    print(f"\n  {symbol} {title}\n     {message}")
    if HAS_PLYER:
        try:
            notification.notify(title=title, message=message,
                                 app_name='Orivon', timeout=8)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════
#  WARNING HANDLERS
# ══════════════════════════════════════════════════════════

def on_reminder(app):
    notify('⏰ Orivon Reminder',
           f"You've been on {app['name']} for 30s. Consider a break.")
    S.add_log(f"Reminder — {app['name']} (30s)", 'warn')

def on_warning(app):
    notify('⚠️ Orivon Warning',
           f"Excessive {app['name']} usage! Closing in 10 seconds.",
           urgency='critical')
    S.add_log(f"Warning — {app['name']} (50s) closing in 10s", 'danger')

def on_blocked(app, handle):
    S.lock_app(app['id'])
    sess = S.session(app['id'])
    sess['elapsed']    = 0
    sess['warn_state'] = 'blocked'
    S.active_app       = None

    notify('🚫 Orivon — Closing Now',
           f"{app['name']} exceeded limit. Closing window NOW.",
           urgency='critical')
    S.add_log(f"BLOCKED — {app['name']} force closed + locked 5 min", 'locked')

    # Close the window immediately
    force_close_window(app, handle)

    # Start enforcement thread to prevent re-opening
    t = threading.Thread(target=lock_enforcement_loop,
                         args=(app['id'],), daemon=True)
    t.start()


# ══════════════════════════════════════════════════════════
#  MAIN MONITORING LOOP
# ══════════════════════════════════════════════════════════

def monitor_loop():
    print(f"\n{'='*58}")
    print(f"  ⚡ ORIVON — Real-Time Digital Addiction Monitor")
    print(f"  Platform : {PLATFORM}")
    print(f"  Reminder : {THRESHOLDS['reminder']}s  |  "
          f"Warning  : {THRESHOLDS['warning']}s  |  "
          f"Block    : {THRESHOLDS['block']}s")
    print(f"  Lock     : {LOCK_DURATION // 60} minutes")
    print(f"{'='*58}\n")
    print("  Monitoring active. Open YouTube, Instagram, etc.")
    print("  Window will be FORCE CLOSED when time is up.")
    print("  Press Ctrl+C to stop.\n")

    last_app_id = None

    while S.running:
        time.sleep(1)

        with S._lock:
            title, handle = get_active_window()
            matched       = match_app(title)
            current_id    = matched['id'] if matched else None

            # ── App switch detection ──────────────────────
            if current_id != last_app_id:
                last_app_id  = current_id
                S.active_app = current_id

                if current_id:
                    if S.is_locked(current_id):
                        rem = S.remaining(current_id)
                        print(f"\n  🚫 {matched['name']} is LOCKED — "
                              f"force closing immediately! ({fmt(rem)} remaining)")
                        S.add_log(f"Re-open blocked: {matched['name']}", 'danger')
                        notify('🚫 Orivon — App Locked',
                               f"{matched['name']} is locked. Closing it now.",
                               urgency='critical')
                        force_close_window(matched, handle)
                    else:
                        sess = S.session(current_id)
                        if sess['elapsed'] == 0:
                            S.add_log(f"Opened: {matched['name']}", 'info')
                            print(f"\n  ▶  Detected: {matched['icon']} {matched['name']}")
                        else:
                            S.add_log(f"Resumed: {matched['name']} "
                                      f"({fmt(sess['elapsed'])} elapsed)", 'info')
                            print(f"\n  ▶  Resumed: {matched['icon']} {matched['name']} "
                                  f"({fmt(sess['elapsed'])})")
                else:
                    print(f"\r  🔍 Watching for activity...{' '*30}", end='')

            # ── Tick the active unlocked app ──────────────
            if current_id and not S.is_locked(current_id):
                sess = S.session(current_id)
                sess['elapsed'] += 1
                e  = sess['elapsed']
                ws = sess['warn_state']

                if e >= THRESHOLDS['block'] and ws != 'blocked':
                    sess['warn_state'] = 'blocked'
                    on_blocked(matched, handle)

                elif e >= THRESHOLDS['warning'] and ws == 'reminder':
                    sess['warn_state'] = 'warning'
                    on_warning(matched)

                elif e >= THRESHOLDS['reminder'] and ws == 'normal':
                    sess['warn_state'] = 'reminder'
                    on_reminder(matched)

                bar  = progress_bar(e, THRESHOLDS['block'])
                risk = risk_label(e)
                print(f"\r  {matched['icon']} {matched['name']:<12} "
                      f"{fmt(e)}  {bar}  {risk}   ", end='', flush=True)

            elif current_id and S.is_locked(current_id):
                rem = S.remaining(current_id)
                print(f"\r  🔒 {matched['name']:<12} LOCKED — "
                      f"closing... {fmt(rem)} remaining   ",
                      end='', flush=True)


# ══════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════

def fmt(s):
    s = int(s)
    return f"{s//60:02d}:{s%60:02d}"

def progress_bar(elapsed, total, width=20):
    filled = min(int(elapsed / total * width), width)
    return '▓' * filled + '░' * (width - filled)

def risk_label(e):
    if e < 30: return '🟢 Normal  '
    if e < 50: return '🟡 Moderate'
    if e < 60: return '🟠 High    '
    return             '🔴 CRITICAL'

def print_dashboard():
    print(f"\n\n{'─'*58}")
    print(f"  📊 ORIVON  [{datetime.now().strftime('%H:%M:%S')}]")
    print(f"{'─'*58}")
    if not S.sessions:
        print("  No sessions yet.")
    for aid, sess in S.sessions.items():
        app    = next((a for a in WATCHED_APPS if a['id'] == aid), None)
        if not app: continue
        locked = S.is_locked(aid)
        status = (f"🔒 LOCKED {fmt(S.remaining(aid))}" if locked
                  else ('▶ ACTIVE' if S.active_app == aid else '  paused'))
        print(f"  {app['icon']} {app['name']:<12} "
              f"{fmt(sess['elapsed']):<8} {sess['warn_state']:<10}  {status}")
    print(f"{'─'*58}")
    for entry in S.log[:6]:
        print(f"  {entry['time']}  {entry['text']}")
    print()

def dashboard_loop():
    while S.running:
        time.sleep(30)
        with S._lock:
            print_dashboard()


# ══════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════

if __name__ == '__main__':
    missing = []
    if PLATFORM == 'Windows':
        try:
            import win32gui
        except ImportError:
            missing.append('pywin32     →  pip install pywin32')
    elif PLATFORM == 'Linux':
        if subprocess.run(['which', 'xdotool'], capture_output=True).returncode != 0:
            missing.append('xdotool     →  sudo apt install xdotool')

    if missing:
        print("\n⚠️  Missing dependencies:")
        for m in missing:
            print(f"   • {m}")
        print()

    if not HAS_PLYER:
        print("ℹ️  Desktop popups: pip install plyer\n")
    if not HAS_PSUTIL:
        print("ℹ️  Process kill fallback: pip install psutil\n")

    threading.Thread(target=dashboard_loop, daemon=True).start()

    try:
        monitor_loop()
    except KeyboardInterrupt:
        S.running = False
        print("\n\n  Orivon stopped.")
        print_dashboard()
