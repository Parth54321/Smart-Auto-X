# ============================================================
# esp32_controller.py  –  ESP32-WROOM Motor Command Sender
# ============================================================
#
# PURPOSE:
#   This module sends HTTP commands to the ESP32-WROOM board
#   which is connected to the Motor Driver + DC Motors.
#
# HOW IT WORKS:
#   1. The ESP32-WROOM runs a small web server (see ESP32 .ino file)
#   2. Flask sends a GET request: http://ESP32_WROOM_IP/FORWARD
#   3. The ESP32-WROOM receives the request and drives motors
#
# COMMANDS:
#   FORWARD  – Move vehicle forward (maintain lane)
#   LEFT     – Turn vehicle left
#   RIGHT    – Turn vehicle right
#   STOP     – Stop all motors
#   OVERTAKE – Execute overtake manoeuvre (LEFT then FORWARD)
#
# TEST MODE (no hardware):
#   Set TEST_MODE = True below to skip all HTTP requests.
#   Commands will only be printed to the terminal.
# ============================================================

import requests  # for sending HTTP requests to ESP32
import time      # for delays

# ─────────────────────────────────────────────────────────────
# CONFIGURATION  ← Edit these before running with real hardware
# ─────────────────────────────────────────────────────────────

# ── ESP32-WROOM IP ───────────────────────────────────────────
# Set this to the IP address shown in the Arduino Serial Monitor
# when the ESP32-WROOM boots (e.g. "192.168.x.x").
# ALL commands including sharp turns are sent to this address.
ESP32_WROOM_IP = "10.135.58.7"   # ← CHANGE THIS to your ESP32-WROOM IP

# ── Test Mode ────────────────────────────────────────────
# True  = print commands to terminal only, NO HTTP requests sent.
# False = send real HTTP requests to ESP32_WROOM_IP.
# ← Set this to False when your ESP32-WROOM is physically connected!
TEST_MODE = False  # ← Set True to simulate without hardware

# HTTP timeout in seconds (how long to wait for ESP32 reply)
HTTP_TIMEOUT = 2


# ─────────────────────────────────────────────────────────────
# ESP32Controller Class
# ─────────────────────────────────────────────────────────────
class ESP32Controller:
    """
    Sends movement commands to the ESP32-WROOM via HTTP GET requests.

    Example usage:
        controller = ESP32Controller()
        controller.send("FORWARD")
        controller.send("LEFT")
        controller.send("STOP")
    """

    def __init__(self):
        # Store the last command to avoid sending duplicates
        self.last_command = "NONE"

        print("[ESP32] Controller initialised.")
        if TEST_MODE:
            print("[ESP32] ⚠️  TEST MODE ON – No HTTP requests will be sent.")
            print(f"[ESP32]    Set TEST_MODE = False and set ESP32_WROOM_IP to use real hardware.")

    # ── Public method: send a command (with dedup) ────────────
    def send(self, command: str):
        """
        Sends a movement command to the ESP32-WROOM.
        Duplicate FORWARD commands are silently skipped to avoid
        flooding the ESP32 every frame when nothing has changed.

        For SHARP TURN commands, use send_turn_signal() instead –
        that method always sends regardless of dedup.

        Args:
            command (str): One of FORWARD, LEFT, RIGHT, STOP, OVERTAKE

        Returns:
            bool: True if successful, False on error
        """
        command = command.upper().strip()

        # Only skip duplicate FORWARD (not turn/stop commands)
        if command == self.last_command and command == "FORWARD":
            return True   # silently skip duplicate FORWARD commands

        self.last_command = command
        return self._http_send(command)

    # ── Public method: send a SHARP TURN signal (always fires) ─
    def send_turn_signal(self, command: str):
        """
        Sends a LEFT or RIGHT sharp-turn command to the ESP32-WROOM.

        Unlike send(), this method ALWAYS fires the HTTP request –
        it is NOT subject to the dedup filter. This guarantees the
        ESP32 receives every sharp-turn command even if the previous
        command happened to be the same direction.

        The URL sent is:  http://<ESP32_WROOM_IP>/LEFT
                      or  http://<ESP32_WROOM_IP>/RIGHT

        Args:
            command (str): "LEFT" or "RIGHT"

        Returns:
            bool: True if successful, False on error
        """
        command = command.upper().strip()
        print(f"[SHARP TURN] → Sending {command} to ESP32-WROOM at {ESP32_WROOM_IP}")
        self.last_command = command
        return self._http_send(command)

    # ── Internal: perform the actual HTTP GET request ──────────
    def _http_send(self, command: str):
        """
        Internal helper that builds the URL and sends the HTTP request.
        Handles TEST_MODE (print only) and real hardware mode.

        URL format:  http://<ESP32_WROOM_IP>/<COMMAND>
        Example:     http://192.168.1.101/LEFT

        Returns:
            bool: True if sent successfully (or in test mode), False on error
        """
        # Print to terminal always
        print(f"[COMMAND] → {command}")

        if TEST_MODE:
            # Just print – no actual HTTP request sent
            print(f"[ESP32] TEST MODE – skipped HTTP for: {command}")
            return True

        # Build the URL: e.g. http://192.168.1.101/LEFT
        url = f"http://{ESP32_WROOM_IP}/{command}"
        print(f"[ESP32] Sending: {url}")

        try:
            response = requests.get(url, timeout=HTTP_TIMEOUT)
            print(f"[ESP32] HTTP {response.status_code} ← {command}")
            return True

        except requests.exceptions.ConnectionError:
            print(f"[ESP32 ERROR] Cannot connect to {ESP32_WROOM_IP}. Is the ESP32-WROOM powered?")
            return False

        except requests.exceptions.Timeout:
            print(f"[ESP32 ERROR] Request timed out for command: {command}")
            return False

        except Exception as e:
            print(f"[ESP32 ERROR] Unexpected error: {e}")
            return False
