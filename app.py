# ============================================================
# app.py  –  Main Flask Backend
# ============================================================
#
# PURPOSE:
#   This is the main server file. It:
#     1. Serves the web dashboard (HTML pages)
#     2. Handles API requests from the dashboard buttons
#     3. Starts/stops the lane detection background thread
#     4. Sends motor commands to ESP32-WROOM
#     5. Opens the OpenCV window LOCALLY (not in the browser)
#
# API ENDPOINTS:
#   POST /api/select    – choose CAR or TRUCK
#   POST /api/start     – start lane detection
#   POST /api/stop      – stop lane detection
#   POST /api/overtake  – send OVERTAKE command
#   GET  /api/status    – get current status (for dashboard polling)
#   GET  /api/logs      – get log entries for the dashboard log panel
#
# RUNNING:
#   python app.py
#   Then open: http://127.0.0.1:5000
# ============================================================

from flask import Flask, render_template, jsonify, request
import threading   # to run lane detection in background
import time        # for sleep/delays
import cv2         # OpenCV – for camera + display window

# Import our custom modules
from lane_detection  import LaneDetector
from esp32_controller import ESP32Controller

# ─────────────────────────────────────────────────────────────
# Flask App Setup
# ─────────────────────────────────────────────────────────────
app = Flask(__name__)

# ─────────────────────────────────────────────────────────────
# Global State Variables
# ─────────────────────────────────────────────────────────────
current_vehicle = None    # "CAR" or "TRUCK"
system_running  = False   # True while lane detection is active
current_lane    = "NONE"  # "LEFT", "RIGHT", or "NONE"
current_command = "NONE"  # last motor command sent

# Shared log list – dashboard reads this
# Each entry is a dict: {"type": "INFO"/"COMMAND"/"WARN", "msg": "..."}
log_entries = []

# Thread lock for safe access to logs
log_lock = threading.Lock()

# Instantiate helper objects
lane_detector = LaneDetector()
esp32         = ESP32Controller()


# ─────────────────────────────────────────────────────────────
# Helper: Add log entry
# ─────────────────────────────────────────────────────────────
def add_log(log_type: str, message: str):
    """
    Adds a log entry to the shared log list.
    Also prints it to the terminal.

    Args:
        log_type (str): "INFO", "COMMAND", "WARN", or "ERROR"
        message  (str): The log message text
    """
    entry = {
        "type": log_type,
        "msg":  message,
        "time": time.strftime("%H:%M:%S")   # current time HH:MM:SS
    }

    with log_lock:
        log_entries.append(entry)
        # Keep only the last 100 entries to avoid memory growth
        if len(log_entries) > 100:
            log_entries.pop(0)

    # Also print to terminal
    print(f"[{log_type}] {message}")


# ─────────────────────────────────────────────────────────────
# Motor Command Decision Logic
# ─────────────────────────────────────────────────────────────
def decide_command(lane_side: str) -> str:
    """
    Decides the motor command based on WHERE the black lane marker
    appears in the camera frame (LEFT half or RIGHT half).

    ┌─────────────────────────────────────────────────────────┐
    │  CAR  → wants to be in the RIGHT lane                   │
    │    Black lane on RIGHT → car drifted LEFT → turn RIGHT  │
    │    Black lane on LEFT  → car is on right side → FORWARD │
    │    No lane detected    → go FORWARD (no change)         │
    ├─────────────────────────────────────────────────────────┤
    │  TRUCK → wants to be in the LEFT lane                   │
    │    Black lane on LEFT  → truck drifted RIGHT → LEFT     │
    │    Black lane on RIGHT → truck is on left side→ FORWARD │
    │    No lane detected    → go FORWARD (no change)         │
    └─────────────────────────────────────────────────────────┘

    NOTE: This function only returns the DESIRED command.
          The 3-second turn delay is enforced in lane_detection_loop().

    Returns: "FORWARD", "LEFT", "RIGHT", or "STOP"
    """
    global current_command

    # ── Compute the intended new command ──────────────────────
    if current_vehicle == "CAR":
        if lane_side == "RIGHT":
            new_command = "RIGHT"    # car drifted left → correct right
        else:
            new_command = "FORWARD"  # correct side or no lane → go straight

    elif current_vehicle == "TRUCK":
        if lane_side == "LEFT":
            new_command = "LEFT"     # truck drifted right → correct left
        else:
            new_command = "FORWARD"  # correct side or no lane → go straight

    else:
        new_command = "STOP"

    # ── De-duplication: only act if command has CHANGED ───────
    # This prevents FORWARD (and other commands) from being
    # logged and sent on every single frame when nothing changes.
    if new_command == current_command:
        return current_command   # ← silent return, no log, no send

    # ── Command changed → log it and update state ─────────────
    current_command = new_command

    if current_vehicle == "CAR":
        if new_command == "RIGHT":
            add_log("INFO",    "CAR – black lane on RIGHT → turning RIGHT")
        elif lane_side == "LEFT":
            add_log("INFO",    "CAR – black lane on LEFT  → correct lane – FORWARD")
        else:
            add_log("INFO",    "CAR – no lane detected → FORWARD")

    elif current_vehicle == "TRUCK":
        if new_command == "LEFT":
            add_log("INFO",    "TRUCK – black lane on LEFT  → turning LEFT")
        elif lane_side == "RIGHT":
            add_log("INFO",    "TRUCK – black lane on RIGHT → correct lane – FORWARD")
        else:
            add_log("INFO",    "TRUCK – no lane detected → FORWARD")

    add_log("COMMAND", new_command)

    return current_command


# ─────────────────────────────────────────────────────────────
# Background Thread: Lane Detection Loop
# ─────────────────────────────────────────────────────────────
def lane_detection_loop():
    """
    Runs in a background thread when START is pressed.

    Steps:
      1. Open camera (ESP32-CAM or webcam)
      2. Read frame continuously
      3. Detect which side the black lane marker is on
      4. Decide the correct motor command (CAR / TRUCK logic)
      5. Enforce 3-second delay after every TURN command
         (gives the motor enough time to complete the turn)
      6. Show annotated frame in LOCAL OpenCV window
      7. Repeat until STOP is pressed or Q is pressed

    3-SECOND TURN DELAY:
      After sending a LEFT or RIGHT command the loop skips
      sending any new commands for 3 seconds, then resumes.
      This prevents the motor being spammed during a turn.
    """
    global system_running, current_lane, current_command

    add_log("INFO", f"{current_vehicle} STARTED")
    add_log("INFO", "Opening camera...")

    # Open the camera
    cap = lane_detector.open_camera()

    if not cap.isOpened():
        add_log("ERROR", "Camera could not be opened! Check IP or USB.")
        system_running = False
        return

    add_log("INFO", "CAMERA CONNECTED")
    print("\n[OPENCV] Lane detection window opened on your screen.")
    print("         Press 'Q' in the OpenCV window to stop.\n")

    # ── Main detection loop ────────────────────────────────────
    while system_running:
        ret, frame = cap.read()

        if not ret:
            add_log("WARN", "Camera read failed – retrying...")
            time.sleep(0.5)
            continue

        # ══ STEP 1: Run base lane detection (always) ══════════
        # Gets which side the black lane marker is on + annotated frame
        lane_side, annotated_frame = lane_detector.detect_lane(frame)
        current_lane = lane_side

        # ══ STEP 2: RED STOP CHECK (HIGHEST PRIORITY) ══════════
        # If a red object is seen → STOP immediately, skip all else
        is_red, annotated_frame = lane_detector.detect_red_overlay(
            frame, annotated_frame
        )
        if is_red:
            if current_command != "STOP":
                add_log("INFO",    "🔴 RED detected → STOP")
                add_log("COMMAND", "STOP")
                esp32.send("STOP")
                current_command = "STOP"
            # Show frame and continue reading (don't send other commands)
            cv2.imshow(f"AI Lane Detection – {current_vehicle}", annotated_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                add_log("INFO", "OpenCV window closed by user (Q key)")
                system_running = False
                break
            time.sleep(0.05)
            continue   # ← skip sign and lane logic

        # ══ STEP 3: SHARP TURN SIGN CHECK (MEDIUM PRIORITY) ════
        # If a sharp-turn sign is visible → execute that turn
        sign, annotated_frame = lane_detector.detect_sign_overlay(
            frame, annotated_frame
        )
        if sign:
            turn_cmd = "LEFT" if sign == "SHARP_LEFT" else "RIGHT"

            if lane_detector.can_turn():
                if current_command != turn_cmd:
                    add_log("INFO",    f"🪧 Sharp turn sign: {sign} → {turn_cmd}")
                    add_log("COMMAND", turn_cmd)
                    # Use send_turn_signal() so it ALWAYS fires to the ESP32
                    # (not subject to the FORWARD dedup filter)
                    esp32.send_turn_signal(turn_cmd)
                    current_command = turn_cmd
                    lane_detector.record_turn()
                    add_log("INFO", f"[DELAY] Waiting 3 s after sign turn: {turn_cmd}")
            else:
                # Still in cooldown – show countdown
                remaining = lane_detector._last_turn_time + 3.0 - time.time()
                cv2.putText(annotated_frame,
                            f"TURNING... ({remaining:.1f}s)",
                            (10, annotated_frame.shape[0] - 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 100, 255), 2)

            cv2.imshow(f"AI Lane Detection – {current_vehicle}", annotated_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                add_log("INFO", "OpenCV window closed by user (Q key)")
                system_running = False
                break
            time.sleep(0.05)
            continue   # ← skip lane logic

        # ══ STEP 4: BLACK LANE LOGIC (NORMAL PRIORITY) ══════════
        # No red, no sign → use the lane position to decide direction
        if not lane_detector.can_turn():
            # Still in turn cooldown – show countdown, no new command
            remaining = lane_detector._last_turn_time + 3.0 - time.time()
            cv2.putText(annotated_frame,
                        f"TURNING... ({remaining:.1f}s)",
                        (10, annotated_frame.shape[0] - 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 100, 255), 2)
        else:
            # Cooldown done → decide command (dedup: only sends on change)
            command = decide_command(lane_side)
            esp32.send(command)

            if command in ("LEFT", "RIGHT"):
                lane_detector.record_turn()
                add_log("INFO", f"[DELAY] Waiting 3 s for motor to complete {command} turn")

        # ── Show annotated frame in LOCAL window ───────────────
        cv2.imshow(f"AI Lane Detection – {current_vehicle}", annotated_frame)

        # Press 'Q' to quit the OpenCV window and stop the system
        if cv2.waitKey(1) & 0xFF == ord('q'):
            add_log("INFO", "OpenCV window closed by user (Q key)")
            system_running = False
            break

        time.sleep(0.05)   # ~20 FPS (gives CPU some breathing room)

    # ── Cleanup ────────────────────────────────────────────────
    cap.release()
    cv2.destroyAllWindows()
    esp32.send("STOP")
    add_log("INFO", f"{current_vehicle} STOPPED")
    print("\n[THREAD] Lane detection loop ended.\n")


# ─────────────────────────────────────────────────────────────
# Flask Routes (Web Pages)
# ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """
    Homepage – shows CAR and TRUCK selection buttons.
    """
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    """
    Dashboard page – shown after vehicle is selected.
    Accepts ?vehicle=CAR or ?vehicle=TRUCK in URL.
    """
    vehicle = request.args.get("vehicle", "CAR").upper()
    return render_template("dashboard.html", vehicle=vehicle)


# ─────────────────────────────────────────────────────────────
# Flask API Endpoints (called by JavaScript fetch() requests)
# ─────────────────────────────────────────────────────────────

@app.route("/api/select", methods=["POST"])
def api_select():
    """
    Called when user clicks CAR or TRUCK button.
    Saves the selected vehicle to global state.
    """
    global current_vehicle
    data = request.get_json()
    current_vehicle = data.get("vehicle", "CAR").upper()

    add_log("INFO", f"Vehicle selected: {current_vehicle}")
    return jsonify({"status": "ok", "vehicle": current_vehicle})


@app.route("/api/start", methods=["POST"])
def api_start():
    """
    Called when START button is pressed on the dashboard.
    Starts the lane detection loop in a background thread.
    Opens the local OpenCV window.
    """
    global system_running

    if system_running:
        return jsonify({"status": "already running"})

    if not current_vehicle:
        return jsonify({"status": "error", "msg": "No vehicle selected!"})

    # Mark system as running
    system_running = True

    # Print startup message to terminal
    print(f"\n{'='*45}")
    print(f"   {current_vehicle} STARTED")
    print(f"{'='*45}\n")

    esp32.send("START")

    # Start lane detection in a background thread
    # daemon=True → thread will stop when main program stops
    thread = threading.Thread(target=lane_detection_loop, daemon=True)
    thread.start()

    return jsonify({"status": "started", "vehicle": current_vehicle})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """
    Called when STOP button is pressed.
    Stops the lane detection loop.
    Sends STOP command to ESP32.
    """
    global system_running
    system_running = False

    esp32.send("STOP")
    add_log("INFO", f"{current_vehicle} STOPPED")

    return jsonify({"status": "stopped"})


@app.route("/api/overtake", methods=["POST"])
def api_overtake():
    """
    Called when OVERTAKE button is pressed.
    Sends OVERTAKE command directly to ESP32-WROOM via HTTP:
      http://<ESP32_WROOM_IP>/OVERTAKE
    """
    add_log("INFO",    "OVERTAKE requested")
    add_log("COMMAND", "OVERTAKE")
    esp32.send("OVERTAKE")

    return jsonify({"status": "overtake sent"})


@app.route("/api/status")
def api_status():
    """
    Returns current system status as JSON.
    The dashboard polls this every second to update the UI.
    """
    return jsonify({
        "vehicle": current_vehicle,
        "running": system_running,
        "lane":    current_lane,
        "command": current_command,
    })


@app.route("/api/logs")
def api_logs():
    """
    Returns the recent log entries as JSON.
    The dashboard polls this every second to update the log panel.
    """
    with log_lock:
        # Return a copy of the last 50 entries
        recent = list(log_entries[-50:])

    return jsonify({"logs": recent})


# ─────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*50)
    print("  🚗  Smart Vehicle Lane Control System")
    print("  Open: http://127.0.0.1:5000")
    print("="*50 + "\n")
    print("  Tip: Press Q in the OpenCV window to stop lane detection.\n")

    # Start Flask server
    # use_reloader=False prevents the background thread from doubling
    app.run(debug=True, threaded=True, use_reloader=False)
