"""
Openclaw Desktop Agent — voert commando's uit op deze machine voor Lumencore.

Installatie:
    pip install requests

Starten:
    python agent.py

Automatisch starten bij Windows opstart:
    Voeg een snelkoppeling toe aan: shell:startup
    Of voer uit: python agent.py --install-startup
"""
from __future__ import annotations

import argparse
import logging
import os
import platform
import subprocess
import sys
import time

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("openclaw_agent.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("openclaw.desktop")

LUMENCORE_API_URL = os.environ.get("LUMENCORE_API_URL", "http://187.77.172.140")
POLL_INTERVAL = 2       # seconden tussen polls
COMMAND_TIMEOUT = 60    # max seconden per commando
IS_WINDOWS = platform.system() == "Windows"


def _run_command(command: str) -> tuple[str, int]:
    """Voer een shell commando uit en geef (output, returncode) terug."""
    try:
        if IS_WINDOWS:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT,
                encoding="utf-8",
                errors="replace",
            )
        else:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT,
                encoding="utf-8",
                errors="replace",
            )

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += "\n[STDERR]\n" + result.stderr
        return output.strip() or "(geen output)", result.returncode

    except subprocess.TimeoutExpired:
        return f"TIMEOUT: commando duurde langer dan {COMMAND_TIMEOUT}s", 1
    except Exception as exc:
        return f"FOUT bij uitvoeren: {exc}", 1


def _poll_next() -> dict | None:
    try:
        resp = requests.get(f"{LUMENCORE_API_URL}/api/desktop/queue/next", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data  # None als er niets is
    except Exception as exc:
        logger.warning("Poll fout: %s", exc)
    return None


def _submit_result(task_id: str, result: str, status: str) -> None:
    try:
        requests.post(
            f"{LUMENCORE_API_URL}/api/desktop/queue/{task_id}/result",
            json={"result": result, "status": status},
            timeout=10,
        )
    except Exception as exc:
        logger.warning("Submit result fout: %s", exc)


def _install_startup() -> None:
    """Voeg agent toe aan Windows opstart."""
    if not IS_WINDOWS:
        print("Automatisch opstarten is alleen ondersteund op Windows.")
        return

    import winreg
    script_path = os.path.abspath(__file__)
    python_path = sys.executable
    cmd = f'"{python_path}" "{script_path}"'

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "OpenclawDesktopAgent", 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        print(f"Succesvol toegevoegd aan opstarten: {cmd}")
    except Exception as exc:
        print(f"Fout bij toevoegen aan opstarten: {exc}")


def run_agent() -> None:
    logger.info("Openclaw Desktop Agent gestart")
    logger.info("Platform: %s | Lumencore: %s", platform.system(), LUMENCORE_API_URL)
    logger.info("Wachten op commando's...")

    while True:
        try:
            task = _poll_next()
            if task and task.get("id"):
                task_id = task["id"]
                command = task["command"]
                logger.info("Commando ontvangen [%s]: %s", task_id[:8], command)

                output, returncode = _run_command(command)
                status = "done" if returncode == 0 else "failed"

                logger.info("Klaar [%s] status=%s output=%s", task_id[:8], status, output[:80])
                _submit_result(task_id, output, status)
            else:
                time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Agent gestopt.")
            break
        except Exception as exc:
            logger.error("Onverwachte fout: %s", exc)
            time.sleep(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Openclaw Desktop Agent")
    parser.add_argument("--install-startup", action="store_true", help="Voeg toe aan Windows opstart")
    args = parser.parse_args()

    if args.install_startup:
        _install_startup()
    else:
        run_agent()
