============================================================
  SIGN TEMPLATES – How to add your own sign images
============================================================

Put YOUR sign photos in this folder with these EXACT names:

  sharp_left.jpg    ← photo of your "sharp left" sign/card
  sharp_right.jpg   ← photo of your "sharp right" sign/card

HOW TO TAKE GOOD TEMPLATE PHOTOS:
  1. Hold the sign flat, facing the camera directly
  2. Good lighting – avoid shadows on the sign
  3. Crop the photo to show ONLY the sign (no background)
  4. Save as JPG (any size – the code resizes automatically)

HOW TEMPLATE MATCHING WORKS:
  The system slides your template image over every part of the
  camera frame and looks for a match above a confidence score.
  If confidence > SIGN_MATCH_THRESHOLD (default 0.55) → detected.

TUNING:
  If the sign is detected too easily (false positives):
    → increase SIGN_MATCH_THRESHOLD in lane_detection.py (e.g. 0.65)
  If the sign is NOT being detected (misses):
    → decrease SIGN_MATCH_THRESHOLD (e.g. 0.45)
    → retake the template photo with better lighting

SIGN SIZES TESTED AT:
  The template is matched at 3 scales (50%, 75%, 100% of template)
  so the sign works even if it is closer or farther from camera.

============================================================
