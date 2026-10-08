# ============================================================
# lane_detection.py  –  AI Lane Detection using OpenCV
# ============================================================
#
# PURPOSE:
#   Reads frames from the ESP32-CAM (or webcam in test mode) and
#   performs THREE levels of detection (in priority order):
#
#   1. RED STOP DETECTION  (highest priority)
#      If the camera sees a large red area → send STOP immediately.
#
#   2. SHARP TURN SIGN DETECTION  (medium priority)
#      Template-matching against signs/sharp_left.jpg and
#      signs/sharp_right.jpg.  Match above threshold → LEFT / RIGHT.
#
#   3. BLACK LANE DETECTION  (normal priority)
#      Counts black pixels in LEFT vs RIGHT half of the frame.
#      CAR  → black on RIGHT means drifted left → turn RIGHT
#      TRUCK → black on LEFT  means drifted right → turn LEFT
#
# SIGN TEMPLATES:
#   Place your sign photos in the signs/ folder:
#     signs/sharp_left.jpg   – photo of your sharp-left card
#     signs/sharp_right.jpg  – photo of your sharp-right card
#   See signs/README.txt for tips on taking good template photos.
# ============================================================

import cv2        # OpenCV – camera and image processing
import numpy as np  # for numeric operations
import time       # for the 3-second turn delay
import os         # for loading sign template files

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────

# ESP32-CAM stream URL  ← set this to your camera's IP
# Example: "http://192.168.1.100/stream"
# For test mode (laptop webcam): use integer 0
ESP32_CAM_URL = "http://10.135.58.165/stream"

# Set this to True to use the laptop webcam instead of ESP32-CAM
USE_WEBCAM_FOR_TEST = False  # ← Set True to use laptop webcam for testing


# ─────────────────────────────────────────────────────────────
# BLACK LANE COLOUR RANGE (HSV)
# ─────────────────────────────────────────────────────────────
# Black objects have very low "Value" (brightness) in HSV.
# ↑ Increase BLACK_UPPER[2] (e.g. 120) if tape looks dark-grey
# ↓ Decrease if too much non-black background gets detected

BLACK_LOWER = np.array([0,   0,   0  ])   # HSV lower bound for black
BLACK_UPPER = np.array([180, 255, 100])   # HSV upper bound for black

# Morphological kernel – fills gaps in the black tape mask
MORPH_KERNEL = np.ones((5, 5), np.uint8)

# Show a small debug popup with the binary black mask.
# White pixels = detected as black lane. Set False to hide.
SHOW_DEBUG_MASK = True

# Minimum black pixel count before we trust the result.
MIN_LANE_PIXELS = 300

# Seconds to wait after a TURN command (motor completion time)
TURN_DELAY_SECONDS = 3.0


# ─────────────────────────────────────────────────────────────
# RED STOP COLOUR RANGE (HSV)
# ─────────────────────────────────────────────────────────────
# Red wraps around the HSV hue circle, so we need TWO ranges.
# Range 1 catches hues near 0°, Range 2 catches hues near 180°.
# ↑ Decrease MIN_RED_PIXELS if the red card is small in frame
# ↑ Increase if random red objects trigger false stops

RED_LOWER1 = np.array([0,   120,  70])   # hue  0°-10°
RED_UPPER1 = np.array([10,  255, 255])
RED_LOWER2 = np.array([170, 120,  70])   # hue 170°-180°
RED_UPPER2 = np.array([180, 255, 255])

MIN_RED_PIXELS = 2000   # minimum red pixel count to trigger STOP


# ─────────────────────────────────────────────────────────────
# SIGN DETECTION CONFIG
# ─────────────────────────────────────────────────────────────
# Path to the sign image folder (relative to this script)
SIGNS_DIR = os.path.join(os.path.dirname(__file__), "signs")

# ── Template Matching (Method 1) ──────────────────────────────
# Confidence threshold: 0.0 (any match) → 1.0 (perfect match)
# Lowered to 0.40 so real-world card variations are still caught.
# Raise to 0.55+ if you get false positives.
SIGN_MATCH_THRESHOLD = 0.40

# More scales = handles sign appearing at different distances.
SIGN_SCALES = [0.3, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0, 1.2, 1.5]

# ── Color Contour Detection (Method 2 – primary, more robust) ─
# Detects the YELLOW/ORANGE colored sign card by HSV range.
# This works even when template matching fails due to angle/light.
#
# SHARP LEFT card color range (HSV)
SIGN_LEFT_LOWER  = np.array([20,  80,  80])   # yellow-orange lower
SIGN_LEFT_UPPER  = np.array([40, 255, 255])   # yellow-orange upper
#
# SHARP RIGHT card color range (HSV)
# If your left/right cards are DIFFERENT colors, tune these:
SIGN_RIGHT_LOWER = np.array([100, 80,  80])   # blue-ish lower
SIGN_RIGHT_UPPER = np.array([130, 255, 255])  # blue-ish upper
#
# Minimum contour area (pixels²) to count as a real sign card.
# Increase if small colored objects trigger false detections.
SIGN_MIN_AREA = 3000

# ── Shared ────────────────────────────────────────────────────
# Seconds to wait after sending a TURN command
SIGN_TURN_DELAY    = 3.0
TURN_DELAY_SECONDS = 3.0


# ─────────────────────────────────────────────────────────────
# LaneDetector Class
# ─────────────────────────────────────────────────────────────
class LaneDetector:
    """
    Opens the camera, detects which side the black lane marker is on,
    and returns the result + an annotated frame.

    Usage:
        detector = LaneDetector()
        cap = detector.open_camera()
        ret, frame = cap.read()
        lane_side, annotated_frame = detector.detect_lane(frame)
        # lane_side is "LEFT", "RIGHT", or "NONE"
    """

    def __init__(self):
        # Store the most recent lane result (used by Flask /api/status)
        self.last_lane = "NONE"

        # Timestamp of the last turn command sent.
        # Used to enforce the 3-second cooldown between turn commands.
        self._last_turn_time = 0.0

        # ── Load sign templates ────────────────────────────────
        # Try to load sharp_left.jpg and sharp_right.jpg from signs/
        # If a file is missing, that sign type is simply disabled.
        self.sign_templates = {}   # dict: {"SHARP_LEFT": img, "SHARP_RIGHT": img}

        for sign_name, filename in [("SHARP_LEFT",  "sharp_left.jpg"),
                                    ("SHARP_RIGHT", "sharp_right.jpg")]:
            path = os.path.join(SIGNS_DIR, filename)
            if os.path.exists(path):
                img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)  # load in greyscale
                if img is not None:
                    self.sign_templates[sign_name] = img
                    print(f"[SIGN] Loaded template: {filename}")
                else:
                    print(f"[SIGN] WARNING: Could not read {filename} – check the file.")
            else:
                print(f"[SIGN] WARNING: {filename} not found in signs/ folder.")
                print(f"       → Add signs/{filename} to enable {sign_name} detection.")

        if not self.sign_templates:
            print("[SIGN] No sign templates loaded – sign detection disabled.")
        else:
            print(f"[SIGN] {len(self.sign_templates)} sign(s) ready for detection.")

    # ── Open the camera source ────────────────────────────────
    def open_camera(self):
        """
        Opens the ESP32-CAM stream or the laptop webcam.
        Returns a cv2.VideoCapture object.
        """
        if USE_WEBCAM_FOR_TEST:
            source = 0   # 0 = default laptop webcam
            print("[CAM] Test mode → using laptop webcam (source=0)")
        else:
            source = ESP32_CAM_URL
            print(f"[CAM] Connecting to ESP32-CAM at: {source}")

        cap = cv2.VideoCapture(source)

        if not cap.isOpened():
            print("[CAM ERROR] Could not open camera! Check IP or USB.")
        else:
            print("[CAM] Camera opened successfully.")

        return cap

    # ── Check if we are allowed to send a turn command ────────
    def can_turn(self):
        """
        Returns True if at least TURN_DELAY_SECONDS have passed
        since the last turn command was sent.

        The 3-second cooldown prevents the motor being spammed
        with commands while it is still physically completing
        the previous turn.
        """
        elapsed = time.time() - self._last_turn_time
        return elapsed >= TURN_DELAY_SECONDS

    # ── Record that a turn command was just sent ───────────────
    def record_turn(self):
        """
        Call this immediately after sending a LEFT or RIGHT command.
        Starts the 3-second cooldown timer.
        """
        self._last_turn_time = time.time()

    # ── Main detection function ───────────────────────────────
    def detect_lane(self, frame):
        """
        Analyses a single video frame and finds which side the
        black lane marker appears on.

        Args:
            frame: A BGR image (numpy array) from cap.read()

        Returns:
            lane_side (str) : "LEFT", "RIGHT", or "NONE"
                              – "LEFT"  = black marker is in the LEFT half
                              – "RIGHT" = black marker is in the RIGHT half
                              – "NONE"  = no black marker detected clearly
            annotated (img) : Frame with coloured overlays drawn on it
        """
        height, width = frame.shape[:2]

        # Step 1: Work on a copy so we don't modify the original
        annotated = frame.copy()

        # Step 2: Crop the bottom 60% of the frame (road / floor area).
        #         The top portion is usually background, walls, or sky.
        roi_top = int(height * 0.40)
        roi = frame[roi_top:height, 0:width]

        # ── Step 3: BLACK colour masking (HSV) ───────────────
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        black_mask = cv2.inRange(hsv, BLACK_LOWER, BLACK_UPPER)

        # ── Step 3b: Morphological cleanup ────────────────────
        # Dilation: fills small holes / gaps inside the tape area
        # Erosion:  removes isolated noise pixels outside the tape
        black_mask = cv2.dilate(black_mask, MORPH_KERNEL, iterations=2)
        black_mask = cv2.erode (black_mask, MORPH_KERNEL, iterations=1)

        # ── Step 3c: Optional debug mask window ───────────────
        # White pixels = the camera sees these as "black lane".
        if SHOW_DEBUG_MASK:
            debug_mask = cv2.resize(black_mask, (320, 120))
            cv2.imshow("[DEBUG] Black Mask (white = lane detected)", debug_mask)

        # ── Step 4: Count black pixels in each half ───────────
        # Split the mask down the centre of the frame.
        half = width // 2
        left_half_mask  = black_mask[:, 0:half]      # left  50% of frame
        right_half_mask = black_mask[:, half:width]  # right 50% of frame

        # Count white (255) pixels in each half
        # More white pixels on one side = black tape is there
        left_pixels  = cv2.countNonZero(left_half_mask)
        right_pixels = cv2.countNonZero(right_half_mask)

        # ── Step 5: Decide which side the lane marker is on ───
        lane_side = self._classify_lane_side(left_pixels, right_pixels)
        self.last_lane = lane_side   # save for Flask /api/status

        # ── Step 6: Draw overlays on annotated frame ──────────
        annotated = self._draw_overlay(
            annotated, lane_side,
            left_pixels, right_pixels,
            roi_top, width, height
        )

        return lane_side, annotated

    # ── Helper: Decide which side has the black lane ──────────
    def _classify_lane_side(self, left_pixels, right_pixels):
        """
        Compares the number of black pixels in the left vs right half.

        Rules:
          – A side must have at least MIN_LANE_PIXELS to count.
          – The side with significantly more pixels is the lane side.
          – If both sides are similar or too low → return "NONE".

        Returns: "LEFT", "RIGHT", or "NONE"
        """
        total = left_pixels + right_pixels

        if total < MIN_LANE_PIXELS:
            return "NONE"   # not enough black detected anywhere

        # Which half has more black pixels?
        if left_pixels > right_pixels * 1.3:
            return "LEFT"    # clearly more black on the left
        elif right_pixels > left_pixels * 1.3:
            return "RIGHT"   # clearly more black on the right
        else:
            return "NONE"    # roughly equal on both sides – ambiguous

    # ── RED STOP Detection ────────────────────────────────────
    def detect_red_overlay(self, frame, annotated):
        """
        Checks if a large RED area is visible in the camera frame.
        Red = STOP signal (highest priority, overrides everything).

        HOW IT WORKS:
          1. Convert frame to HSV
          2. Apply TWO red masks (red wraps around the HSV circle)
          3. Count total red pixels
          4. If count > MIN_RED_PIXELS → STOP detected

        Args:
            frame    : original BGR frame from camera
            annotated: annotated frame to draw overlay on

        Returns:
            is_red (bool): True if STOP should be triggered
            annotated    : frame with red overlay drawn on it
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Build combined red mask from both hue ranges
        mask1 = cv2.inRange(hsv, RED_LOWER1, RED_UPPER1)
        mask2 = cv2.inRange(hsv, RED_LOWER2, RED_UPPER2)
        red_mask = cv2.bitwise_or(mask1, mask2)

        red_pixels = cv2.countNonZero(red_mask)
        is_red = red_pixels >= MIN_RED_PIXELS

        if is_red:
            # ── Flash a bright red STOP banner across the top ──
            h, w = annotated.shape[:2]
            # Red semi-transparent overlay on top 80px
            flash = annotated.copy()
            cv2.rectangle(flash, (0, 0), (w, 80), (0, 0, 220), -1)
            annotated = cv2.addWeighted(flash, 0.6, annotated, 0.4, 0)
            cv2.putText(annotated, "  🔴  RED DETECTED – STOP!",
                        (10, 55), cv2.FONT_HERSHEY_SIMPLEX,
                        1.2, (255, 255, 255), 3)
            cv2.putText(annotated, f"red px: {red_pixels}",
                        (w - 160, 55), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (200, 200, 200), 1)

        return is_red, annotated

    # ── SHARP TURN SIGN Detection (Template + Color dual method) ──
    def detect_sign_overlay(self, frame, annotated):
        """
        Detects SHARP LEFT or SHARP RIGHT sign cards using TWO methods:

        METHOD 1 – Multi-Scale Template Matching  (PRIMARY)
        ─────────────────────────────────────────────────────────────────
        Slides each template (sharp_left.jpg / sharp_right.jpg) over the
        frame at multiple scales and picks the highest-confidence match.

        WHY THIS IS PRIMARY:
          Template matching reads the actual SHAPE/IMAGE on the card, so
          it correctly tells LEFT from RIGHT even when both cards share
          the same physical color. Color-only detection would always pick
          whichever color range fires first.

        METHOD 2 – HSV Color + Contour Detection  (FALLBACK)
        ─────────────────────────────────────────────────────────────────
        Used only when no template images are loaded (signs/ folder empty).
        Detects a distinctively colored card by HSV range.
        Requires each card to be a DIFFERENT color to work correctly.

        Args:
            frame    : original BGR frame from camera
            annotated: annotated frame to draw match box on

        Returns:
            sign (str or None): "SHARP_LEFT", "SHARP_RIGHT", or None
            annotated         : frame with match box drawn on it
        """
        # ══ METHOD 1: Multi-Scale Template Matching (PRIMARY) ══════
        if self.sign_templates:
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            fh, fw    = frame_gray.shape

            best_sign  = None
            best_score = 0.0
            best_box   = None   # (x, y, w, h)

            for sign_name, template in self.sign_templates.items():
                th, tw = template.shape

                for scale in SIGN_SCALES:
                    new_w = max(1, int(tw * scale))
                    new_h = max(1, int(th * scale))

                    # Skip if scaled template is larger than the frame
                    if new_h >= fh or new_w >= fw:
                        continue

                    tpl_scaled = cv2.resize(template, (new_w, new_h))

                    # Normalised cross-correlation template matching
                    result = cv2.matchTemplate(
                        frame_gray, tpl_scaled, cv2.TM_CCOEFF_NORMED
                    )
                    _, max_val, _, max_loc = cv2.minMaxLoc(result)

                    if max_val > best_score:
                        best_score = max_val
                        best_sign  = sign_name
                        best_box   = (max_loc[0], max_loc[1], new_w, new_h)

            # Accept if above the confidence threshold
            if best_score >= SIGN_MATCH_THRESHOLD and best_box:
                annotated = self._draw_sign_overlay(
                    annotated, best_sign, best_box, score=best_score
                )
                return best_sign, annotated

        # ══ METHOD 2: HSV Color + Contour Detection (FALLBACK) ════
        # Only used when no template images are loaded.
        # NOTE: Requires LEFT and RIGHT cards to be DIFFERENT colors.
        #       If both cards are the same color, this will always
        #       detect SHARP_LEFT. Use template images for reliability.
        detected_sign, detected_box = self._detect_sign_by_color(frame)

        if detected_sign:
            annotated = self._draw_sign_overlay(
                annotated, detected_sign, detected_box, score=None
            )
            return detected_sign, annotated

        return None, annotated   # neither method detected a sign

    # ── Helper: HSV Color + Contour sign detection ────────────────
    def _detect_sign_by_color(self, frame):
        """
        Detects a sign card by its distinctive color using HSV masking
        and contour area filtering.

        Uses:
          - SIGN_LEFT_LOWER / SIGN_LEFT_UPPER  → yellow/orange card
          - SIGN_RIGHT_LOWER / SIGN_RIGHT_UPPER → blue card
          - SIGN_MIN_AREA                       → minimum card area

        Returns:
            (sign_name, bounding_box) or (None, None) if not found
            bounding_box is (x, y, w, h)
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        results = []   # list of (sign_name, area, bounding_box)

        # ── Check each sign color ──────────────────────────────────
        sign_color_map = [
            ("SHARP_LEFT",  SIGN_LEFT_LOWER,  SIGN_LEFT_UPPER),
            ("SHARP_RIGHT", SIGN_RIGHT_LOWER, SIGN_RIGHT_UPPER),
        ]

        for sign_name, lower, upper in sign_color_map:
            mask = cv2.inRange(hsv, lower, upper)

            # Morphological cleanup to remove noise
            kernel = np.ones((7, 7), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)

            # Find contours of colored blobs
            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area >= SIGN_MIN_AREA:
                    x, y, w, h = cv2.boundingRect(cnt)
                    results.append((sign_name, area, (x, y, w, h)))

        if not results:
            return None, None

        # Pick the largest detected colored region
        results.sort(key=lambda r: r[1], reverse=True)
        best_sign, _, best_box = results[0]
        return best_sign, best_box

    # ── Helper: Draw sign detection overlay on frame ──────────────
    def _draw_sign_overlay(self, annotated, sign_name, box, score=None):
        """
        Draws a bounding box and banner on the annotated frame
        when a sharp turn sign has been detected.

        Args:
            annotated : annotated frame to draw on
            sign_name : "SHARP_LEFT" or "SHARP_RIGHT"
            box       : (x, y, w, h) bounding box of the sign
            score     : confidence score (float) or None for color method
        """
        if box:
            x, y, bw, bh = box
            # Green box around detected sign
            cv2.rectangle(annotated, (x, y), (x + bw, y + bh),
                          (0, 255, 0), 3)
            # Label
            score_str = f"({score:.2f})" if score is not None else "(color)"
            label = f"{sign_name} {score_str}"
            cv2.putText(annotated, label,
                        (x, max(0, y - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        # Green banner at top of frame
        h, w = annotated.shape[:2]
        flash = annotated.copy()
        cv2.rectangle(flash, (0, 0), (w, 60), (0, 120, 0), -1)
        annotated = cv2.addWeighted(flash, 0.65, annotated, 0.35, 0)

        arrow = "<< SHARP LEFT" if sign_name == "SHARP_LEFT" else "SHARP RIGHT >>"
        cv2.putText(annotated,
                    f"  {arrow}  – SENDING TURN SIGNAL",
                    (10, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    0.85, (255, 255, 255), 2)

        return annotated

    # ── Helper: Draw all overlays on the frame ────────────────
    def _draw_overlay(self, frame, lane_side,
                      left_pixels, right_pixels,
                      roi_top, width, height):
        """
        Draws on the annotated frame:
          - Centre divider line (splits LEFT / RIGHT halves)
          - Coloured highlight on whichever half has the black lane
          - Pixel count readout (so you can see the raw numbers)
          - Status banner at top showing which side the lane is on
          - Direction arrow (what action should happen)
        """
        overlay = frame.copy()
        half    = width // 2

        # ── Highlight the side where black lane was detected ───
        if lane_side == "LEFT":
            # Blue tint on the left half (where the lane marker is)
            cv2.rectangle(overlay, (0, roi_top), (half, height),
                          (255, 100, 0), -1)   # blue fill
        elif lane_side == "RIGHT":
            # Red tint on the right half
            cv2.rectangle(overlay, (half, roi_top), (width, height),
                          (0, 60, 200), -1)    # red fill

        # Blend the highlight semi-transparently
        overlay = cv2.addWeighted(overlay, 0.25, frame, 0.75, 0)

        # ── Centre divider line ────────────────────────────────
        cv2.line(overlay, (half, roi_top), (half, height), (255, 220, 0), 2)

        # ── Lane labels ────────────────────────────────────────
        label_y = roi_top + 35
        cv2.putText(overlay, "LEFT",  (15,        label_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 220, 0), 2)
        cv2.putText(overlay, "RIGHT", (half + 15, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 220, 0), 2)

        # ── Pixel count readout ────────────────────────────────
        count_y = height - 15
        cv2.putText(overlay, f"L:{left_pixels}",
                    (10, count_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.putText(overlay, f"R:{right_pixels}",
                    (half + 10, count_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        # ── Direction arrow ────────────────────────────────────
        arrow_x = width  // 2
        arrow_y = height - 70
        if lane_side == "LEFT":
            # Lane is on LEFT  → arrow points LEFT
            cv2.arrowedLine(overlay, (arrow_x + 50, arrow_y),
                            (arrow_x - 50, arrow_y), (0, 165, 255), 4,
                            tipLength=0.4)
        elif lane_side == "RIGHT":
            # Lane is on RIGHT → arrow points RIGHT
            cv2.arrowedLine(overlay, (arrow_x - 50, arrow_y),
                            (arrow_x + 50, arrow_y), (0, 165, 255), 4,
                            tipLength=0.4)
        else:
            # No lane detected → UP arrow (go straight)
            cv2.arrowedLine(overlay, (arrow_x, arrow_y + 40),
                            (arrow_x, arrow_y - 40), (0, 165, 255), 4,
                            tipLength=0.4)

        # ── Status banner at the very top ─────────────────────
        colour_map = {
            "LEFT":  (0, 165, 255),   # Orange
            "RIGHT": (0, 200, 50),    # Green
            "NONE":  (180, 180, 180), # Grey
        }
        banner_colour = colour_map.get(lane_side, (180, 180, 180))

        cv2.rectangle(overlay, (0, 0), (width, 50), (0, 0, 0), -1)
        cv2.putText(overlay, f"  Black Lane: {lane_side}",
                    (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                    banner_colour, 2)
        cv2.putText(overlay, "AI Lane Detection",
                    (width - 230, 35), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (150, 150, 150), 1)

        return overlay
