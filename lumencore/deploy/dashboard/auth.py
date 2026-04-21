"""PIN authentication for Lumencore Dashboard.

Stores a hashed PIN in auth_config.json (never plain text).
Rate limits login attempts — lockout after 5 failures.
Sessions are in-memory tokens valid for 8 hours.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

AUTH_CONFIG_PATH = Path(__file__).parent / "auth_config.json"
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300       # 5 minutes lockout after max attempts
SESSION_TTL = 8 * 3600      # 8 hours

# In-memory state (single process)
_sessions: dict[str, float] = {}           # token → expiry timestamp
_failed_attempts: list[float] = []         # timestamps of failed attempts


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 200_000).hex()


def _load_config() -> dict:
    if AUTH_CONFIG_PATH.exists():
        try:
            return json.loads(AUTH_CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_config(cfg: dict) -> None:
    AUTH_CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def is_pin_configured() -> bool:
    cfg = _load_config()
    return bool(cfg.get("pin_hash") and cfg.get("salt"))


def set_pin(pin: str) -> None:
    """Hash and store a new PIN."""
    if not pin.isdigit() or len(pin) != 4:
        raise ValueError("PIN must be exactly 4 digits")
    salt = secrets.token_hex(16)
    pin_hash = _hash_pin(pin, salt)
    _save_config({"pin_hash": pin_hash, "salt": salt})


def is_locked_out() -> tuple[bool, int]:
    """Returns (locked, seconds_remaining)."""
    now = time.time()
    # Keep only recent failures within lockout window
    recent = [t for t in _failed_attempts if now - t < LOCKOUT_SECONDS]
    _failed_attempts.clear()
    _failed_attempts.extend(recent)
    if len(recent) >= MAX_ATTEMPTS:
        oldest = min(recent)
        remaining = int(LOCKOUT_SECONDS - (now - oldest))
        return True, max(0, remaining)
    return False, 0


def verify_pin(pin: str) -> str | None:
    """Verify PIN. Returns session token on success, None on failure."""
    locked, remaining = is_locked_out()
    if locked:
        return None

    cfg = _load_config()
    if not cfg.get("pin_hash") or not cfg.get("salt"):
        return None

    expected = _hash_pin(pin, cfg["salt"])
    if hmac.compare_digest(expected, cfg["pin_hash"]):
        # Success — create session
        token = secrets.token_urlsafe(32)
        _sessions[token] = time.time() + SESSION_TTL
        return token
    else:
        _failed_attempts.append(time.time())
        return None


def is_valid_session(token: str | None) -> bool:
    if not token:
        return False
    expiry = _sessions.get(token)
    if expiry is None:
        return False
    if time.time() > expiry:
        del _sessions[token]
        return False
    return True


def logout(token: str) -> None:
    _sessions.pop(token, None)


def get_session_from_cookie(cookie_header: str | None) -> str | None:
    if not cookie_header:
        return None
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("lc_session="):
            return part[len("lc_session="):]
    return None


PIN_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Lumencore — Login</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Inter', sans-serif;
  background: #08090d;
  color: #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
}
.card {
  background: #0d0f17;
  border: 1px solid rgba(0,212,255,0.15);
  border-radius: 16px;
  padding: 48px 40px;
  width: 340px;
  text-align: center;
}
.logo {
  width: 52px; height: 52px;
  background: linear-gradient(135deg, #00d4ff, #7c3aed);
  border-radius: 12px;
  margin: 0 auto 20px;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px;
}
h1 { font-size: 22px; font-weight: 700; margin-bottom: 6px; }
p { color: #56627a; font-size: 13px; margin-bottom: 32px; }
.pin-row {
  display: flex; gap: 12px; justify-content: center; margin-bottom: 28px;
}
.pin-digit {
  width: 56px; height: 64px;
  background: #131620;
  border: 2px solid rgba(255,255,255,0.07);
  border-radius: 10px;
  font-size: 28px;
  font-weight: 700;
  color: #00d4ff;
  text-align: center;
  outline: none;
  transition: border-color 0.2s;
}
.pin-digit:focus { border-color: #00d4ff; }
button {
  width: 100%;
  padding: 14px;
  background: linear-gradient(135deg, #00d4ff, #7c3aed);
  border: none;
  border-radius: 10px;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}
button:hover { opacity: 0.9; }
.error { color: #ff4444; font-size: 13px; margin-top: 16px; min-height: 20px; }
.lockout { color: #ffd740; font-size: 13px; margin-top: 16px; }
</style>
</head>
<body>
<div class="card">
  <div class="logo">⚡</div>
  <h1>Lumencore</h1>
  <p>Enter your 4-digit PIN to access the control plane</p>
  <form method="POST" action="/auth/login" id="pinForm">
    <div class="pin-row">
      <input class="pin-digit" type="password" maxlength="1" inputmode="numeric" pattern="[0-9]" id="p1" name="p1" autofocus/>
      <input class="pin-digit" type="password" maxlength="1" inputmode="numeric" pattern="[0-9]" id="p2" name="p2"/>
      <input class="pin-digit" type="password" maxlength="1" inputmode="numeric" pattern="[0-9]" id="p3" name="p3"/>
      <input class="pin-digit" type="password" maxlength="1" inputmode="numeric" pattern="[0-9]" id="p4" name="p4"/>
    </div>
    <input type="hidden" name="pin" id="pinFull"/>
    <button type="submit">Unlock</button>
  </form>
  <div class="error" id="errMsg">__ERROR__</div>
</div>
<script>
const digits = ['p1','p2','p3','p4'];
digits.forEach((id, i) => {
  const el = document.getElementById(id);
  el.addEventListener('input', () => {
    if (el.value && i < 3) document.getElementById(digits[i+1]).focus();
  });
  el.addEventListener('keydown', e => {
    if (e.key === 'Backspace' && !el.value && i > 0) document.getElementById(digits[i-1]).focus();
  });
});
document.getElementById('pinForm').addEventListener('submit', e => {
  const pin = digits.map(id => document.getElementById(id).value).join('');
  document.getElementById('pinFull').value = pin;
});
</script>
</body>
</html>
"""

PIN_SETUP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Lumencore — Set PIN</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family:'Inter',sans-serif; background:#08090d; color:#e2e8f0; display:flex; align-items:center; justify-content:center; min-height:100vh; }
.card { background:#0d0f17; border:1px solid rgba(0,212,255,0.15); border-radius:16px; padding:48px 40px; width:360px; text-align:center; }
.logo { width:52px;height:52px;background:linear-gradient(135deg,#00d4ff,#7c3aed);border-radius:12px;margin:0 auto 20px;display:flex;align-items:center;justify-content:center;font-size:24px; }
h1 { font-size:22px;font-weight:700;margin-bottom:6px; }
p { color:#56627a;font-size:13px;margin-bottom:32px; }
.pin-row { display:flex;gap:12px;justify-content:center;margin-bottom:20px; }
.pin-digit { width:56px;height:64px;background:#131620;border:2px solid rgba(255,255,255,0.07);border-radius:10px;font-size:28px;font-weight:700;color:#00d4ff;text-align:center;outline:none;transition:border-color 0.2s; }
.pin-digit:focus { border-color:#00d4ff; }
label { display:block;color:#8897b0;font-size:12px;margin-bottom:8px;text-align:left; }
button { width:100%;padding:14px;background:linear-gradient(135deg,#00d4ff,#7c3aed);border:none;border-radius:10px;color:#fff;font-size:15px;font-weight:600;cursor:pointer; }
.warn { color:#ffd740;font-size:12px;margin-bottom:20px; }
</style>
</head>
<body>
<div class="card">
  <div class="logo">⚡</div>
  <h1>Set your PIN</h1>
  <p>Choose a 4-digit PIN to protect the Lumencore control plane</p>
  <p class="warn">⚠ This PIN cannot be recovered. Store it safely.</p>
  <form method="POST" action="/auth/setup">
    <label>Choose PIN</label>
    <div class="pin-row">
      <input class="pin-digit" type="password" maxlength="1" inputmode="numeric" id="p1" autofocus/>
      <input class="pin-digit" type="password" maxlength="1" inputmode="numeric" id="p2"/>
      <input class="pin-digit" type="password" maxlength="1" inputmode="numeric" id="p3"/>
      <input class="pin-digit" type="password" maxlength="1" inputmode="numeric" id="p4"/>
    </div>
    <label>Confirm PIN</label>
    <div class="pin-row">
      <input class="pin-digit" type="password" maxlength="1" inputmode="numeric" id="c1"/>
      <input class="pin-digit" type="password" maxlength="1" inputmode="numeric" id="c2"/>
      <input class="pin-digit" type="password" maxlength="1" inputmode="numeric" id="c3"/>
      <input class="pin-digit" type="password" maxlength="1" inputmode="numeric" id="c4"/>
    </div>
    <input type="hidden" name="pin" id="pinFull"/>
    <input type="hidden" name="confirm" id="confirmFull"/>
    <button type="submit">Set PIN & Enter</button>
  </form>
</div>
<script>
function wireDigits(ids, nextGroup) {
  ids.forEach((id,i) => {
    const el = document.getElementById(id);
    el.addEventListener('input', () => { if(el.value && i < ids.length-1) document.getElementById(ids[i+1]).focus(); else if(el.value && nextGroup) document.getElementById(nextGroup).focus(); });
    el.addEventListener('keydown', e => { if(e.key==='Backspace' && !el.value && i>0) document.getElementById(ids[i-1]).focus(); });
  });
}
wireDigits(['p1','p2','p3','p4'], 'c1');
wireDigits(['c1','c2','c3','c4'], null);
document.querySelector('form').addEventListener('submit', e => {
  const pin = ['p1','p2','p3','p4'].map(id=>document.getElementById(id).value).join('');
  const confirm = ['c1','c2','c3','c4'].map(id=>document.getElementById(id).value).join('');
  document.getElementById('pinFull').value = pin;
  document.getElementById('confirmFull').value = confirm;
});
</script>
</body>
</html>
"""
