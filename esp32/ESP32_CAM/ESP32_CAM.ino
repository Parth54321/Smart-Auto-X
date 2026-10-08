/*
  ============================================================
  ESP32_CAM.ino  –  Camera Streaming Firmware
  ============================================================

  PURPOSE:
    This code runs on the ESP32-CAM module.
    It connects to Wi-Fi and streams live MJPEG video
    which Flask reads via cv2.VideoCapture().

  HOW IT WORKS:
    1. ESP32-CAM connects to your Wi-Fi
    2. Starts an MJPEG stream at: http://<IP>/stream
    3. Python (lane_detection.py) reads this stream

  PINOUT (AI-THINKER ESP32-CAM):
    No extra pins needed – camera is built-in.
    Just power it via 5V and GND.

  SETUP STEPS:
    1. In Arduino IDE, go to:
       Tools → Board → "AI Thinker ESP32-CAM"
    2. Set your Wi-Fi name and password below
    3. Upload (use a USB-to-TTL adapter or programmer)
    4. Open Serial Monitor at 115200 baud
    5. Press Reset button on the ESP32-CAM
    6. Copy the IP address shown → paste into lane_detection.py
       as ESP32_CAM_URL = "http://YOUR_IP/stream"

  IMPORTANT: Set USE_WEBCAM_FOR_TEST = False in lane_detection.py
             when using this camera.
  ============================================================
*/

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"

// ─────────────────────────────────────────────────────────────
// Wi-Fi Configuration  ← CHANGE THESE
// ─────────────────────────────────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_NAME";     // ← your Wi-Fi name
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"; // ← your Wi-Fi password

// ─────────────────────────────────────────────────────────────
// Camera Pins (AI-THINKER ESP32-CAM board)
// ─────────────────────────────────────────────────────────────
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ─────────────────────────────────────────────────────────────
// MJPEG Stream Handler
// ─────────────────────────────────────────────────────────────
#define PART_BOUNDARY "123456789000000000000987654321"
static const char* STREAM_CONTENT_TYPE =
    "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* STREAM_PART =
    "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t stream_httpd = NULL;

// Stream handler function
static esp_err_t stream_handler(httpd_req_t *req) {
    camera_fb_t * fb = NULL;
    esp_err_t res = ESP_OK;
    char part_buf[64];

    // Set response content type to MJPEG
    res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
    if (res != ESP_OK) return res;

    while (true) {
        // Capture a frame
        fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("[CAM ERROR] Frame capture failed");
            res = ESP_FAIL;
            break;
        }

        // Send boundary
        res = httpd_resp_send_chunk(req,
            STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
        if (res != ESP_OK) break;

        // Send part header
        size_t hlen = snprintf(part_buf, 64, STREAM_PART, fb->len);
        res = httpd_resp_send_chunk(req, part_buf, hlen);
        if (res != ESP_OK) break;

        // Send JPEG frame data
        res = httpd_resp_send_chunk(req,
            (const char *)fb->buf, fb->len);
        esp_camera_fb_return(fb);   // release frame buffer
        fb = NULL;
        if (res != ESP_OK) break;
    }

    if (fb) esp_camera_fb_return(fb);
    return res;
}

// ─────────────────────────────────────────────────────────────
// Setup
// ─────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    Serial.println("\n=== ESP32-CAM Stream ===");

    // Camera configuration
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer   = LEDC_TIMER_0;
    config.pin_d0       = Y2_GPIO_NUM;
    config.pin_d1       = Y3_GPIO_NUM;
    config.pin_d2       = Y4_GPIO_NUM;
    config.pin_d3       = Y5_GPIO_NUM;
    config.pin_d4       = Y6_GPIO_NUM;
    config.pin_d5       = Y7_GPIO_NUM;
    config.pin_d6       = Y8_GPIO_NUM;
    config.pin_d7       = Y9_GPIO_NUM;
    config.pin_xclk     = XCLK_GPIO_NUM;
    config.pin_pclk     = PCLK_GPIO_NUM;
    config.pin_vsync    = VSYNC_GPIO_NUM;
    config.pin_href     = HREF_GPIO_NUM;
    config.pin_sscb_sda = SIOD_GPIO_NUM;
    config.pin_sscb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn     = PWDN_GPIO_NUM;
    config.pin_reset    = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size   = FRAMESIZE_VGA;   // 640x480
    config.jpeg_quality = 12;              // 0-63 (lower = better)
    config.fb_count     = 2;

    // Init camera
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("[ERROR] Camera init failed: 0x%x\n", err);
        return;
    }
    Serial.println("[CAM] Camera initialised.");

    // Connect to Wi-Fi
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("Connecting to Wi-Fi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println("\n[WiFi] Connected!");
    Serial.print("[WiFi] IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.println("Set this in lane_detection.py:");
    Serial.print("  ESP32_CAM_URL = \"http://");
    Serial.print(WiFi.localIP());
    Serial.println("/stream\"");

    // Start stream server
    httpd_config_t server_config = HTTPD_DEFAULT_CONFIG();
    server_config.server_port = 80;

    if (httpd_start(&stream_httpd, &server_config) == ESP_OK) {
        httpd_uri_t stream_uri = {
            .uri      = "/stream",
            .method   = HTTP_GET,
            .handler  = stream_handler,
            .user_ctx = NULL
        };
        httpd_register_uri_handler(stream_httpd, &stream_uri);
        Serial.println("[SERVER] Stream server started at /stream");
    }
}

// ─────────────────────────────────────────────────────────────
// Loop – nothing needed, server handles requests automatically
// ─────────────────────────────────────────────────────────────
void loop() {
    delay(10);
}
