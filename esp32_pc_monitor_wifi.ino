// ESP32 + SH1106 (128x64, I2C) PC stats monitor over WiFi (UDP)
// Library needed: U8g2 (Arduino Library Manager)
// Wiring: SH1106 VCC->3V3, GND->GND, SDA->GPIO21, SCL->GPIO22
//
// Receives UDP packets like:  C:23,R:45,G:12,T:65

#include <Arduino.h>
#include <U8g2lib.h>
#include <Wire.h>
#include <WiFi.h>
#include <WiFiUdp.h>

const char *WIFI_SSID = "YOUR_WIFI_SSID";
const char *WIFI_PASS = "YOUR_WIFI_PASSWORD";
const uint16_t UDP_PORT = 4210;

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);
WiFiUDP udp;

int cpu = 0, ram = 0, gpu = 0, gtemp = -1;
unsigned long lastData = 0;

void drawRow(int y, const char *label, int pct, const char *txt) {
  pct = constrain(pct, 0, 100);
  u8g2.setFont(u8g2_font_6x10_tr);
  u8g2.drawStr(0, y + 9, label);

  const int bx = 26, bw = 74, bh = 12;
  u8g2.drawFrame(bx, y, bw, bh);
  u8g2.drawBox(bx + 2, y + 2, ((bw - 4) * pct) / 100, bh - 4);

  u8g2.drawStr(104, y + 9, txt);
}

void showMessage(const char *l1, const char *l2) {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_7x13B_tr);
  u8g2.drawStr(4, 26, l1);
  u8g2.setFont(u8g2_font_6x10_tr);
  u8g2.drawStr(4, 46, l2);
  u8g2.sendBuffer();
}

void render() {
  if (WiFi.status() != WL_CONNECTED) {
    showMessage("WiFi lost...", "Reconnecting");
    return;
  }
  if (millis() - lastData > 3000) {
    String ip = "IP: " + WiFi.localIP().toString();
    showMessage("Waiting for PC", ip.c_str());
    return;
  }

  char t[8];
  u8g2.clearBuffer();

  snprintf(t, sizeof(t), "%3d%%", cpu);
  drawRow(1, "CPU", cpu, t);

  snprintf(t, sizeof(t), "%3d%%", ram);
  drawRow(17, "RAM", ram, t);

  snprintf(t, sizeof(t), "%3d%%", gpu);
  drawRow(33, "GPU", gpu, t);

  if (gtemp >= 0) snprintf(t, sizeof(t), "%3dC", gtemp);
  else            snprintf(t, sizeof(t), " -- ");
  drawRow(49, "TMP", gtemp >= 0 ? gtemp : 0, t);  // bar = 0-100 C

  u8g2.sendBuffer();
}

void connectWifi() {
  showMessage("Connecting WiFi", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // lower latency
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long t = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t < 15000) delay(200);
}

void setup() {
  Serial.begin(115200);
  u8g2.begin();
  u8g2.setBusClock(400000);
  connectWifi();
  udp.begin(UDP_PORT);
  Serial.println(WiFi.localIP());
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    static unsigned long lastTry = 0;
    if (millis() - lastTry > 5000) {
      lastTry = millis();
      WiFi.reconnect();
    }
  }

  bool updated = false;
  int size = udp.parsePacket();
  if (size > 0) {
    char pkt[64];
    int n = udp.read(pkt, sizeof(pkt) - 1);
    pkt[n > 0 ? n : 0] = 0;
    int c, r, g, t;
    int got = sscanf(pkt, "C:%d,R:%d,G:%d,T:%d", &c, &r, &g, &t);
    if (got >= 3) {
      cpu = c; ram = r; gpu = g;
      gtemp = (got == 4) ? t : -1;
      lastData = millis();
      updated = true;
    }
  }

  static unsigned long lastDraw = 0;
  if (updated || millis() - lastDraw > 500) {
    render();
    lastDraw = millis();
  }
}
