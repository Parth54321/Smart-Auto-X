/*
  ============================================================
  ESP32_WROOM.ino  –  Motor Controller Firmware
  ============================================================

  PURPOSE:
    This code runs on the ESP32-WROOM microcontroller.
    It connects to your Wi-Fi and starts a web server.
    When Flask sends an HTTP command like:
      http://192.168.1.101/FORWARD
    The ESP32-WROOM receives it and drives the motors.

  HARDWARE CONNECTIONS:
    Motor Driver (L298N) → ESP32-WROOM:
      IN1 → GPIO 14   (Motor A - direction pin 1)
      IN2 → GPIO 27   (Motor A - direction pin 2)
      IN3 → GPIO 26   (Motor B - direction pin 1)
      IN4 → GPIO 25   (Motor B - direction pin 2)
      ENA → GPIO 12   (Motor A - speed / PWM)
      ENB → GPIO 13   (Motor B - speed / PWM)
      GND → GND
      VCC → 5V or Battery

  COMMANDS RECEIVED:
    /FORWARD  → Both motors forward
    /LEFT     → Left motor slow, right motor fast (turn left)
    /RIGHT    → Left motor fast, right motor slow (turn right)
    /STOP     → All motors stop
    /OVERTAKE → Fast speed burst for 1.5 seconds, then stop

  HOW TO USE:
    1. Install ESP32 board package in Arduino IDE
    2. Set your Wi-Fi name and password below
    3. Upload this sketch to the ESP32-WROOM
    4. Open Serial Monitor (115200 baud) to see the IP address
    5. Copy that IP into esp32_controller.py as ESP32_WROOM_IP
  ============================================================
*/

#include <WiFi.h>           // Wi-Fi library
#include <WebServer.h>      // HTTP web server library

// ─────────────────────────────────────────────────────────────
// Wi-Fi Configuration  ← CHANGE THESE
// ─────────────────────────────────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_NAME";     // ← your Wi-Fi name
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"; // ← your Wi-Fi password

// ─────────────────────────────────────────────────────────────
// Motor Driver Pin Definitions
// ─────────────────────────────────────────────────────────────
// Motor A (Left wheel)
#define MOTOR_A_IN1  14    // Direction pin 1
#define MOTOR_A_IN2  27    // Direction pin 2
#define MOTOR_A_EN   12    // Speed (PWM)

// Motor B (Right wheel)
#define MOTOR_B_IN3  26    // Direction pin 1
#define MOTOR_B_IN4  25    // Direction pin 2
#define MOTOR_B_EN   13    // Speed (PWM)

// ─────────────────────────────────────────────────────────────
// Speed Settings (0 to 255)
// ─────────────────────────────────────────────────────────────
#define SPEED_NORMAL  180   // Normal forward speed
#define SPEED_TURN    120   // Inner wheel speed during turn
#define SPEED_FAST    220   // Fast speed for overtake

// ─────────────────────────────────────────────────────────────
// Web Server on port 80
// ─────────────────────────────────────────────────────────────
WebServer server(80);

// ─────────────────────────────────────────────────────────────
// Setup – runs once at boot
// ─────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    Serial.println("\n=== ESP32 WROOM Motor Controller ===");

    // Set motor driver pins as outputs
    pinMode(MOTOR_A_IN1, OUTPUT);
    pinMode(MOTOR_A_IN2, OUTPUT);
    pinMode(MOTOR_A_EN,  OUTPUT);
    pinMode(MOTOR_B_IN3, OUTPUT);
    pinMode(MOTOR_B_IN4, OUTPUT);
    pinMode(MOTOR_B_EN,  OUTPUT);

    // Start with motors stopped
    stopMotors();

    // Connect to Wi-Fi
    Serial.print("Connecting to Wi-Fi: ");
    Serial.println(WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println("\n[WiFi] Connected!");
    Serial.print("[WiFi] IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.println("Copy this IP into esp32_controller.py as ESP32_WROOM_IP");

    // Register URL routes
    server.on("/FORWARD",     handleForward);
    server.on("/LEFT",        handleLeft);
    server.on("/RIGHT",       handleRight);
    server.on("/STOP",        handleStop);
    server.on("/OVERTAKE",    handleOvertake);
    server.on("/START",       handleStart);       // sent by Flask on boot
    server.on("/SHARP_LEFT",  handleSharpLeft);   // sharp turn alias
    server.on("/SHARP_RIGHT", handleSharpRight);  // sharp turn alias
    server.on("/",            handleRoot);

    server.begin();
    Serial.println("[SERVER] HTTP server started.");
    Serial.println("Routes: /FORWARD /LEFT /RIGHT /STOP /OVERTAKE /START /SHARP_LEFT /SHARP_RIGHT");
}

// ─────────────────────────────────────────────────────────────
// Loop – handles incoming HTTP requests continuously
// ─────────────────────────────────────────────────────────────
void loop() {
    server.handleClient();
}

// ─────────────────────────────────────────────────────────────
// Route Handlers
// ─────────────────────────────────────────────────────────────

// Root page – shows ESP32 is alive
void handleRoot() {
    server.send(200, "text/plain", "ESP32 WROOM Motor Controller is ONLINE");
}

// FORWARD – both motors run forward
void handleForward() {
    Serial.println("[CMD] FORWARD");
    moveForward(SPEED_NORMAL);
    server.send(200, "text/plain", "FORWARD OK");
}

// LEFT – left motor slow, right motor fast
void handleLeft() {
    Serial.println("[CMD] LEFT");
    turnLeft();
    server.send(200, "text/plain", "LEFT OK");
}

// RIGHT – right motor slow, left motor fast
void handleRight() {
    Serial.println("[CMD] RIGHT");
    turnRight();
    server.send(200, "text/plain", "RIGHT OK");
}

// STOP – all motors off
void handleStop() {
    Serial.println("[CMD] STOP");
    stopMotors();
    server.send(200, "text/plain", "STOP OK");
}

// OVERTAKE – fast forward burst, then stop
void handleOvertake() {
    Serial.println("[CMD] OVERTAKE");
    moveForward(SPEED_FAST);   // Go at fast speed
    delay(1500);               // Hold for 1.5 seconds
    stopMotors();              // Then stop
    server.send(200, "text/plain", "OVERTAKE OK");
}

// START – motors begin at normal forward speed
void handleStart() {
    Serial.println("[CMD] START");
    moveForward(SPEED_NORMAL);
    server.send(200, "text/plain", "START OK");
}

// SHARP_LEFT – sharp left turn (same as LEFT but explicit)
void handleSharpLeft() {
    Serial.println("[CMD] SHARP_LEFT");
    turnLeft();
    server.send(200, "text/plain", "SHARP_LEFT OK");
}

// SHARP_RIGHT – sharp right turn (same as RIGHT but explicit)
void handleSharpRight() {
    Serial.println("[CMD] SHARP_RIGHT");
    turnRight();
    server.send(200, "text/plain", "SHARP_RIGHT OK");
}

// ─────────────────────────────────────────────────────────────
// Motor Control Functions
// ─────────────────────────────────────────────────────────────

// Move both motors forward at given speed
void moveForward(int speed) {
    // Motor A (left) – forward
    digitalWrite(MOTOR_A_IN1, HIGH);
    digitalWrite(MOTOR_A_IN2, LOW);
    analogWrite(MOTOR_A_EN, speed);

    // Motor B (right) – forward
    digitalWrite(MOTOR_B_IN3, HIGH);
    digitalWrite(MOTOR_B_IN4, LOW);
    analogWrite(MOTOR_B_EN, speed);
}

// Turn left: slow left motor, fast right motor
void turnLeft() {
    digitalWrite(MOTOR_A_IN1, HIGH);
    digitalWrite(MOTOR_A_IN2, LOW);
    analogWrite(MOTOR_A_EN, SPEED_TURN);   // Left wheel: slow

    digitalWrite(MOTOR_B_IN3, HIGH);
    digitalWrite(MOTOR_B_IN4, LOW);
    analogWrite(MOTOR_B_EN, SPEED_NORMAL); // Right wheel: normal
}

// Turn right: fast left motor, slow right motor
void turnRight() {
    digitalWrite(MOTOR_A_IN1, HIGH);
    digitalWrite(MOTOR_A_IN2, LOW);
    analogWrite(MOTOR_A_EN, SPEED_NORMAL); // Left wheel: normal

    digitalWrite(MOTOR_B_IN3, HIGH);
    digitalWrite(MOTOR_B_IN4, LOW);
    analogWrite(MOTOR_B_EN, SPEED_TURN);   // Right wheel: slow
}

// Stop all motors
void stopMotors() {
    digitalWrite(MOTOR_A_IN1, LOW);
    digitalWrite(MOTOR_A_IN2, LOW);
    analogWrite(MOTOR_A_EN, 0);

    digitalWrite(MOTOR_B_IN3, LOW);
    digitalWrite(MOTOR_B_IN4, LOW);
    analogWrite(MOTOR_B_EN, 0);
}
