# ⚡ ORIVON — Python Desktop Monitor

Detects the **active window** on your computer in real time. Works across all apps and browsers — not just Chrome. If you open YouTube in Firefox, Edge, or any browser, Orivon sees it.

---

## Install Dependencies

### All platforms
```bash
pip install plyer psutil
```

### Windows (extra)
```bash
pip install pywin32
```

### macOS
No extra install — uses built-in `osascript`.

### Linux
```bash
sudo apt install xdotool
```

---

## Run It

```bash
python orivon_monitor.py
```

Then just use your computer normally. Orivon watches in the background.

---

## What It Detects

Matches window titles and app names containing:

| App | Keywords watched |
|-----|-----------------|
| YouTube | `youtube`, `youtube.com` |
| Instagram | `instagram`, `instagram.com` |
| Facebook | `facebook`, `fb.com` |
| TikTok | `tiktok`, `tiktok.com` |
| Twitter/X | `twitter`, `x.com` |
| Reddit | `reddit`, `reddit.com` |
| Twitch | `twitch`, `twitch.tv` |
| Netflix | `netflix`, `netflix.com` |
| Games | `steam`, `roblox`, `minecraft`, etc. |

---

## Example Output

```
========================================================
  ⚡ ORIVON — Real-Time Addiction Monitor
  Platform: Linux
  Thresholds: Reminder=30s  Warning=50s  Block=60s
========================================================

  ▶  Detected: ▶  YouTube
  ▶  YouTube      00:28  ████████████░░░░░░░░  🟢 Normal
  ▶  YouTube      00:30  ████████████░░░░░░░░  🟡 Moderate

  🔔 Orivon Reminder: You've been on YouTube for 30s...

  ▶  YouTube      00:51  ████████████████████  🟠 High
  🚨 Orivon Warning: Excessive YouTube usage detected!

  🚫 BLOCKED — YouTube locked for 5 minutes
```

---

## How Blocking Works

The Python app **cannot forcibly close your browser** (OS security restriction), but it:
1. Sends a **desktop notification** telling you to stop
2. **Logs** the violation
3. **Tracks the lock** — if you switch back, it re-warns immediately

For forcible blocking on Linux, you can extend the script to use `pkill` or network-level blocking via `/etc/hosts`.

---

*Orivon — OS-level awareness, zero permissions needed.*
