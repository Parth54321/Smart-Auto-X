# 🚗 AI-Based Smart Vehicle Lane Detection and Control System

A **beginner-friendly** AI project that uses a camera mounted on a vehicle to detect road lanes and automatically control the vehicle's direction using ESP32 microcontrollers.

---

## 📁 Project Structure

```
car_truck_2/
│
├── app.py                  ← Flask backend (main server)
├── lane_detection.py       ← OpenCV lane detection logic
├── esp32_controller.py     ← Sends commands to ESP32-WROOM
├── requirements.txt        ← Python packages to install
│
├── templates/
│   ├── index.html          ← Vehicle selection homepage
│   └── dashboard.html      ← Control dashboard
│
├── static/
│   ├── style.css           ← Dark theme styling
│   └── script.js           ← Dashboard JavaScript
│
└── esp32/
    ├── ESP32_WROOM/
    │   └── ESP32_WROOM.ino ← Motor controller firmware
    └── ESP32_CAM/
        └── ESP32_CAM.ino   ← Camera stream firmware
```

---

## 🧠 System Architecture

```
[ESP32-CAM]              [Computer]                  [ESP32-WROOM]
Mounted on car    →   Flask + OpenCV              →   Motor Driver
Streams video         Detects lane                    DC Motors
via IP address        Shows local window
                      Sends commands via HTTP
```

### Flow:
1. **ESP32-CAM** captures live road video → streams to computer via Wi-Fi  
2. **Flask + OpenCV** reads the stream, detects lanes, displays locally  
3. **Flask backend** decides direction (LEFT / RIGHT / FORWARD)  
4. **HTTP command** sent to **ESP32-WROOM** → drives motors  

---

## ⚙️ Hardware Required

| Component      | Purpose                          |
|----------------|----------------------------------|
| ESP32-CAM      | Camera mounted on vehicle        |
| ESP32-WROOM    | Connected to motor driver        |
| L298N Motor Driver | Controls DC motors          |
| 2× DC Motors   | Drive the vehicle wheels         |
| Power bank / battery | Power the vehicle          |
| USB cable      | Program the ESP32 boards         |

---

## 🔌 Hardware Connections

### L298N Motor Driver → ESP32-WROOM

| L298N Pin | ESP32-WROOM GPIO | Function          |
|-----------|-----------------|-------------------|
| IN1       | GPIO 14         | Motor A direction |
| IN2       | GPIO 27         | Motor A direction |
| ENA       | GPIO 12         | Motor A speed     |
| IN3       | GPIO 26         | Motor B direction |
| IN4       | GPIO 25         | Motor B direction |
| ENB       | GPIO 13         | Motor B speed     |
| GND       | GND             | Common ground     |
| 5V        | 5V              | Logic power       |

### DC Motors → L298N

| Motor          | L298N Terminals |
|----------------|-----------------|
| Left wheel     | OUT1, OUT2      |
| Right wheel    | OUT3, OUT4      |

---

## 🚀 Step-by-Step Setup

### STEP 1 – Install Python Packages

```bash
cd car_truck_2
pip install -r requirements.txt
```

### STEP 2 – Test Without Hardware First

In `esp32_controller.py`, make sure:
```python
TEST_MODE = True          # No real hardware needed
```

In `lane_detection.py`, make sure:
```python
USE_WEBCAM_FOR_TEST = True  # Uses your laptop camera
```

### STEP 3 – Run Flask Server

```bash
python app.py
```

Open in browser: **http://127.0.0.1:5000**

### STEP 4 – Use the Dashboard

1. Click **CAR** or **TRUCK** on the homepage
2. Click **START** on the dashboard
3. A **local OpenCV window** opens on your screen with lane detection
4. Watch the logs panel update in real time
5. Click **STOP** to stop

---

## 🔧 Setting Up Real Hardware

### A. Flash ESP32-CAM

1. Open `esp32/ESP32_CAM/ESP32_CAM.ino` in Arduino IDE
2. Set your Wi-Fi:
   ```cpp
   const char* WIFI_SSID     = "YOUR_WIFI_NAME";
   const char* WIFI_PASSWORD = "YOUR_PASSWORD";
   ```
3. Select Board: **AI-Thinker ESP32-CAM**
4. Upload the sketch
5. Open Serial Monitor at **115200 baud**
6. Press Reset → copy the IP address shown

7. In `lane_detection.py`, update:
   ```python
   ESP32_CAM_URL = "http://YOUR_CAM_IP/stream"
   USE_WEBCAM_FOR_TEST = False
   ```

### B. Flash ESP32-WROOM

1. Open `esp32/ESP32_WROOM/ESP32_WROOM.ino` in Arduino IDE
2. Set your Wi-Fi:
   ```cpp
   const char* WIFI_SSID     = "YOUR_WIFI_NAME";
   const char* WIFI_PASSWORD = "YOUR_PASSWORD";
   ```
3. Select Board: **ESP32 Dev Module**
4. Upload the sketch
5. Open Serial Monitor → copy the IP address shown

6. In `esp32_controller.py`, update:
   ```python
   ESP32_WROOM_IP = "YOUR_WROOM_IP"
   TEST_MODE = False
   ```

---

## 🛣️ Lane Detection Explained

The road is divided into **3 lanes**:

```
|   LEFT   |   MIDDLE   |   RIGHT   |
0         w/3          2w/3         w
```

### Detection Process:
1. **Crop** bottom 55% of frame (road area only)
2. **Convert to HSV** colour space
3. **Black mask** → detect dark lane markings (`cv2.inRange`)
4. **Gaussian Blur** → reduce noise
5. **Canny edges** → find line boundaries
6. **Trapezoid mask** → ignore sky and walls
7. **Hough Transform** → find lane lines
8. **Average lines** → one left boundary + one right boundary
9. **Midpoint** → calculate vehicle position
10. **Classify** → LEFT / MIDDLE / RIGHT

---

## 🚗 Vehicle Logic

### CAR (prefers RIGHT lane):
| Current Lane | Command Sent |
|-------------|--------------|
| LEFT        | RIGHT        |
| MIDDLE      | RIGHT        |
| RIGHT       | FORWARD      |

### TRUCK (prefers LEFT lane):
| Current Lane | Command Sent |
|-------------|--------------|
| RIGHT       | LEFT         |
| MIDDLE      | LEFT         |
| LEFT        | FORWARD      |

---

## 🖥️ Dashboard Features

| Feature         | Description                              |
|----------------|------------------------------------------|
| Vehicle Status | Shows RUNNING / STOPPED                  |
| Current Lane   | Shows LEFT / MIDDLE / RIGHT              |
| Direction      | Shows current command (← → ↑ ■)         |
| Signal Logs    | Live log of all events and commands      |
| START button   | Starts detection + opens OpenCV window   |
| STOP button    | Stops detection and motors               |
| OVERTAKE button| Sends OVERTAKE command to ESP32          |

> ⚠️ **Note**: The camera feed does NOT appear in the browser.  
> It opens as a **local OpenCV window** on your computer screen.

---

## 📋 Log Format

```
[INFO]    CAR STARTED
[INFO]    CAMERA CONNECTED
[INFO]    CAR is in LEFT lane
[COMMAND] RIGHT
[INFO]    CAR is in RIGHT lane – MAINTAIN
[COMMAND] FORWARD
[INFO]    CAR STOPPED
```

---

## 🧪 Testing Without Hardware

Set in `esp32_controller.py`:
```python
TEST_MODE = True
```

Set in `lane_detection.py`:
```python
USE_WEBCAM_FOR_TEST = True
```

Then run `python app.py` and test the full flow with your laptop webcam.  
All commands will be printed to the terminal only – no real motor movement.

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| `Camera could not be opened` | Check ESP32-CAM IP or set `USE_WEBCAM_FOR_TEST = True` |
| `Cannot connect to ESP32` | Check ESP32-WROOM IP or set `TEST_MODE = True` |
| Dashboard not loading | Make sure Flask is running with `python app.py` |
| No lanes detected | Improve lighting, adjust `BLACK_LOWER/UPPER` in lane_detection.py |
| OpenCV window not showing | Make sure you're not in a headless environment |

---

## 📦 Python Packages

```
flask       – web server and routing
opencv-python – camera capture + lane detection
numpy       – math and arrays
requests    – HTTP calls to ESP32
```

Install all:
```bash
pip install -r requirements.txt
```
