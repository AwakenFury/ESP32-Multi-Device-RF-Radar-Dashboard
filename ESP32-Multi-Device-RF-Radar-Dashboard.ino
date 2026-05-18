#include <Wire.h>
#include <WiFi.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include "esp_bt_main.h"
#include "esp_bt_device.h"
#include "esp_gap_bt_api.h"
#include <MPU6050_light.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "DFRobot_BMM150.h"

// ---------------- CONFIG ----------------
#define MAX_NETWORKS 8
#define WIFI_SCAN_INTERVAL 15000
#define BLE_SCAN_INTERVAL 20000
#define BT_SCAN_INTERVAL 25000
#define BLE_SCAN_TIME 5
#define MOTION_PIN 23
#define ESP32_TX 17
#define ESP32_RX 16
#define UART_BAUD 115200
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define BAR_HEIGHT 4
#define BAR_SPACING 2
#define TEXT_HEIGHT 8
#define BMM150_ADDR 0x10

MPU6050 mpu(Wire);
BLEScan* pBLEScan;
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// ---------------- DEVICE STRUCT ----------------
struct Device {
  String name;
  int rssi;
  int txPower;
  bool hidden;
};

Device wifiList[MAX_NETWORKS];
Device bleList[MAX_NETWORKS];
Device btList[MAX_NETWORKS];

Device strongestWiFi = {"", -100, -50, false};
Device strongestBLE  = {"", -100, -50, false};
Device strongestBT   = {"", -100, -50, false};

int wifiCount = 0, bleCount = 0, btCount = 0;
bool motionDetected = false;

// ---------------- TIMERS ----------------
unsigned long lastWiFiScan = 0;
unsigned long lastBLEScan = 0;
unsigned long lastBTScan  = 0;
unsigned long lastIMU     = 0;
const unsigned long IMU_UPDATE_INTERVAL = 250;

// ---------------- BMM150 MAGNETOMETER ----------------
DFRobot_BMM150_I2C mag(&Wire, BMM150_ADDR);

struct MagnetometerData {
  int16_t x;
  int16_t y;
  int16_t z;
};

MagnetometerData magData;

// ---------------- BT CALLBACK ----------------
void btGapCallback(esp_bt_gap_cb_event_t event, esp_bt_gap_cb_param_t *param) {
  if (event == ESP_BT_GAP_DISC_RES_EVT) {
    if(btCount >= MAX_NETWORKS) return;

    char mac[18];
    sprintf(mac, "%02X:%02X:%02X:%02X:%02X:%02X",
            param->disc_res.bda[0], param->disc_res.bda[1], param->disc_res.bda[2],
            param->disc_res.bda[3], param->disc_res.bda[4], param->disc_res.bda[5]);
    String name = String(mac);

    int rssi = -60;
    int txPower = -50;
    for (int i = 0; i < param->disc_res.num_prop; i++) {
      if (param->disc_res.prop[i].type == ESP_BT_GAP_DEV_PROP_RSSI)
        rssi = *(int8_t*)param->disc_res.prop[i].val;
    }

    bool hidden = (name.length() == 0 || name.startsWith("00:00"));
    btList[btCount++] = {name, rssi, txPower, hidden};

    Serial1.printf("BT,%s,%s,%d,%d,%d\n", name.c_str(), mac, rssi, txPower, hidden?1:0);
    Serial.printf("BT,%s,%s,%d,%d,%d\n", name.c_str(), mac, rssi, txPower, hidden?1:0);

    if(rssi > strongestBT.rssi) strongestBT = {name, rssi, txPower, hidden};
  }
}

// ---------------- OLED ----------------
void drawBarLine(int y, const Device &dev, const char* label){
  display.setTextSize(1);
  display.setCursor(0, y);
  String name = dev.name.length() > 10 ? dev.name.substring(0,10) : dev.name;
  display.printf("%s:%s %d", label, name.c_str(), dev.rssi);
  int maxBarWidth = SCREEN_WIDTH - 20;
  int barWidth = map(dev.rssi, -100, -30, 0, maxBarWidth);
  barWidth = constrain(barWidth, 0, maxBarWidth);
  display.drawRect(0, y + TEXT_HEIGHT + 1, maxBarWidth, BAR_HEIGHT, SSD1306_WHITE);
  if(barWidth>0) display.fillRect(0, y + TEXT_HEIGHT + 1, barWidth, BAR_HEIGHT, SSD1306_WHITE);
}

void updateOLED() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(2);
  display.setCursor(0,0);
  display.println(motionDetected ? "NEARBY!" : "NO MOTION");

  int yStart = 18;
  drawBarLine(yStart, strongestWiFi, "WiFi");
  drawBarLine(yStart + TEXT_HEIGHT + BAR_HEIGHT + BAR_SPACING, strongestBLE, "BLE");
  drawBarLine(yStart + 2*(TEXT_HEIGHT+BAR_HEIGHT+BAR_SPACING), strongestBT, "BT");

  display.display();
}

// ---------------- BMM150 READ ----------------
void readBMM150Mag() {
  sBmm150MagData_t raw = mag.getGeomagneticData();
  magData.x = raw.x;
  magData.y = raw.y;
  magData.z = raw.z;
  Serial1.printf("MAG,X=%d,Y=%d,Z=%d\n", magData.x, magData.y, magData.z);
  Serial.printf("MAG,X=%d,Y=%d,Z=%d\n", magData.x, magData.y, magData.z);
}

// ---------------- SETUP ----------------
void setup() {
  Serial.begin(115200);
  Serial1.begin(UART_BAUD, SERIAL_8N1, ESP32_RX, ESP32_TX);

  pinMode(MOTION_PIN, INPUT);

  Wire.begin(21,22);
  mpu.begin();
  mpu.calcOffsets();

  if(!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) while(1) delay(1000);
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0,0);
  display.println("Init...");
  display.display();

  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);

  BLEDevice::init("");
  pBLEScan = BLEDevice::getScan();
  pBLEScan->setActiveScan(true);

  esp_bt_controller_config_t bt_cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
  esp_bt_controller_init(&bt_cfg);
  esp_bt_controller_enable(ESP_BT_MODE_CLASSIC_BT);
  esp_bluedroid_init();
  esp_bluedroid_enable();
  esp_bt_gap_register_callback(btGapCallback);

  // Initialize BMM150
  if(!mag.begin()) {
    Serial.println("BMM150 init failed!");
    while(1) delay(1000);
  }

  Serial1.println("TEST,ESP32 Ready,0");
  Serial.println("TEST,ESP32 Ready,0");
}

// ---------------- LOOP ----------------
void loop() {
  unsigned long now = millis();
  motionDetected = digitalRead(MOTION_PIN);

  // IMU
  if(now - lastIMU >= IMU_UPDATE_INTERVAL){
    lastIMU = now;
    mpu.update();
    float roll  = mpu.getAngleX();
    float pitch = mpu.getAngleY();
    float yaw   = mpu.getAngleZ();
    Serial1.printf("IMU,ROLL,%.2f,PITCH,%.2f,YAW,%.2f\n", roll,pitch,yaw);
    Serial.printf("IMU,ROLL,%.2f,PITCH,%.2f,YAW,%.2f\n", roll,pitch,yaw);
  }

  // Magnetometer
  readBMM150Mag();

  // Wi-Fi
  if(now - lastWiFiScan >= WIFI_SCAN_INTERVAL){
    lastWiFiScan = now;
    int n = WiFi.scanNetworks();
    wifiCount = n > MAX_NETWORKS ? MAX_NETWORKS : n;
    strongestWiFi = {"", -100, -50, false};
    for(int i=0;i<wifiCount;i++){
      String ssid = WiFi.SSID(i);
      int rssi = WiFi.RSSI(i);
      int tx = 20;
      bool hidden = (ssid=="");
      wifiList[i] = {ssid, rssi, tx, hidden};
      if(rssi > strongestWiFi.rssi) strongestWiFi = wifiList[i];
      Serial1.printf("WIFI,%s,%d\n", ssid.c_str(), rssi);
      Serial.printf("WIFI,%s,%d\n", ssid.c_str(), rssi);
    }
    WiFi.scanDelete();
  }

  // BLE
  if(now - lastBLEScan >= BLE_SCAN_INTERVAL){
    lastBLEScan = now;
    BLEScanResults found = pBLEScan->start(BLE_SCAN_TIME, false);
    bleCount = found.getCount() > MAX_NETWORKS ? MAX_NETWORKS : found.getCount();
    strongestBLE = {"", -100, -50, false};
    for(int i=0;i<bleCount;i++){
      BLEAdvertisedDevice d = found.getDevice(i);
      String name = d.getName().c_str();
      if(name=="") name = d.getAddress().toString().c_str();
      int rssi = d.getRSSI();
      int tx = 4;
      bool hidden = d.getName()==""; 
      bleList[i] = {name, rssi, tx, hidden};
      if(rssi > strongestBLE.rssi) strongestBLE = bleList[i];
      Serial1.printf("BLE,%s,%d\n", name.c_str(), rssi);
      Serial.printf("BLE,%s,%d\n", name.c_str(), rssi);
    }
    pBLEScan->clearResults();
  }

  // Classic BT
  if(now - lastBTScan >= BT_SCAN_INTERVAL){
    lastBTScan = now;
    btCount = 0;
    strongestBT = {"", -100, -50, false};
    esp_bt_gap_start_discovery(ESP_BT_INQ_MODE_GENERAL_INQUIRY, 10, 0);
  }

  // OLED
  updateOLED();

  delay(50);
}
