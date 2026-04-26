#define BLYNK_TEMPLATE_ID "TMPL3KfNiPygD"
#define BLYNK_TEMPLATE_NAME "SMART IRRIGATION"
#define BLYNK_AUTH_TOKEN "U6gJFDLGSpdC8Vu3awW4Yd9RC0eNt5rG"

#define BLYNK_PRINT Serial
#include <WiFi.h>
#include <BlynkSimpleEsp32.h>
#include <DHT.h>

// ==== BLYNK AUTH TOKEN ====
char auth[] = "U6gJFDLGSpdC8Vu3awW4Yd9RC0eNt5rG";  // Paste your token from Blynk app

// ==== WIFI CREDENTIALS ====
const char* ssid = "Daharath";        // WiFi name
const char* pass = "1234567890";      // WiFi password

// ==== SENSOR PINS ====
#define SOIL_PIN 34     // Soil Moisture Sensor (Analog)
#define RAIN_PIN 32     // Rain Sensor (Analog)
#define LDR_PIN 35      // LDR Sensor (Analog)
#define DHT_PIN 4       // DHT11 Sensor
#define RELAY_PIN 27    // Relay controlling water pump

#define DHTTYPE DHT11
DHT dht(DHT_PIN, DHTTYPE);
BlynkTimer timer;

// ==== BLYNK VIRTUAL PINS ====
#define V_SOIL  V1
#define V_TEMP  V2
#define V_HUM   V3
#define V_RAIN  V4
#define V_LDR   V5
#define V_PUMP  V6

// ==== READ ANALOG STABLE ====
int readADCavg(int pin, int samples = 10) {
  long sum = 0;
  for (int i = 0; i < samples; i++) {
    sum += analogRead(pin);
    delay(5);
  }
  return sum / samples;
}

// ==== SEND SENSOR DATA TO BLYNK ====
void sendData() {
  int soilADC = readADCavg(SOIL_PIN);
  int rainADC = readADCavg(RAIN_PIN);
  int ldrADC  = readADCavg(LDR_PIN);
  float temp = dht.readTemperature();
  float hum  = dht.readHumidity();

  // Print in Serial Monitor
  Serial.print("Soil: "); Serial.print(soilADC);
  Serial.print(" | Rain: "); Serial.print(rainADC);
  Serial.print(" | LDR: "); Serial.print(ldrADC);
  Serial.print(" | Temp: "); Serial.print(temp);
  Serial.print("°C | Hum: "); Serial.println(hum);

  // Send to Blynk
  Blynk.virtualWrite(V_SOIL, soilADC);
  Blynk.virtualWrite(V_RAIN, rainADC);
  Blynk.virtualWrite(V_LDR, ldrADC);
  Blynk.virtualWrite(V_TEMP, temp);
  Blynk.virtualWrite(V_HUM, hum);
}

// ==== MANUAL PUMP CONTROL ONLY ====
BLYNK_WRITE(V_PUMP) {
  int val = param.asInt();
  digitalWrite(RELAY_PIN, val ? LOW : HIGH); // Active LOW relay
  Serial.println(val ? "Pump ON (Manual)" : "Pump OFF (Manual)");
}

// ==== SETUP ====
void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, HIGH); // Relay OFF initially
  dht.begin();

  Serial.println("Connecting to WiFi...");
  Blynk.begin(auth, ssid, pass);
  timer.setInterval(5000L, sendData); // Send sensor data every 5 seconds
}

// ==== LOOP ====
void loop() {
  Blynk.run();
  timer.run();
}
