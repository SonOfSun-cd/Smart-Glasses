#include <WiFi.h>
#include <HTTPClient.h>
#include <esp_camera.h>
#include <WebServer.h>
#include <SD_MMC.h>
#include <FS.h>
#include <ArduinoJson.h>

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

const char *AP_ssid = "ESP32_";
const char *AP_password = "pfur0651";

const char *ssid;
const char *password;
const char *ip;

IPAddress local_ip(192,168,1,1);
IPAddress gateway(192,168,1,1);
IPAddress subnet(255,255,255,0);

WebServer server(3000);

void camera_setup(){
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_UXGA; // High res; reduce if PSRAM issues
  config.jpeg_quality = 10;
  config.fb_count = 3;

  esp_err_t error = esp_camera_init(&config);
  if (error!=ESP_OK)
  {
    Serial.print("Error ");
    Serial.println(error);
  }
}

void setup() {
  //pinMode(4, INPUT_PULLUP);
  Serial.begin(115200);
  Serial.println(SD_MMC.begin());
  File db = SD_MMC.open("/data.json");
  JsonDocument data;
  deserializeJson(data, db);
  const char* IP_check = data["IP"];
  Serial.println(IP_check);
  Serial.println(String(IP_check).length());
  if (String(IP_check).length()==3)
  {
    StartAP();
    CheckConnection();
  }
  else 
  {
    ip = data["IP"];
    StartConnection(data["ssid"], data["password"]);
    CheckConnection();
  }
  db.close();
  camera_setup();
  server.on("/img", handle_imgPOST);
  server.begin();
  Serial.println("Started the server");
}

void StartConnection(const char* SSID, const char* PASSWORD)
{
  WiFi.mode(WIFI_STA);
  WiFi.begin(SSID, PASSWORD);
  int count = 0;
  while (WiFi.status() != WL_CONNECTED)
  {
    if (count>=20)
    {
      Serial.println("Невозможно установить подключение. Введите другие данные или попробуйте снова");
      break;
    }
    delay(500);
    Serial.print('.');
    count++;
  }
  Serial.println(WiFi.status());
  Serial.println(WiFi.localIP());
  Serial.println(String(WiFi.localIP()));
}

void CheckConnection()
{
  HTTPClient http;
  http.begin("https://jsonplaceholder.typicode.com/todos/1");
  Serial.println(http.GET());
}

void handle_imgPOST()
{
  camera_fb_t *frame = esp_camera_fb_get();
  if (!frame)
  {
    Serial.println("couldnt capture frame");
    return;
  }
  else
  {
    Serial.println("Captured frame and exchanged it");
  }
  server.sendHeader("Content-Type", "image/jpeg");
  //server.sendHeader("Content-Length", String(frame->len));
  server.send_P(200, "image/jpeg", (const char *)frame->buf, frame->len);
  esp_camera_fb_return(frame);
}
void StartAP()
{
  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_ssid, AP_password);
  //WiFi.softAPConfig(local_ip, gateway, subnet);
  String IP = WiFi.softAPIP().toString();
  Serial.println(WiFi.softAPIP());
  while (WiFi.softAPgetStationNum()==0)
  {
    Serial.print(".");
    delay(1000);
  }
  Serial.println("Connected");
  char *ip = "192.168.4.2";
  GetAPdata(ip); 
}

void GetAPdata(char *IP)
{
  HTTPClient http;
  http.begin("http://" + String(IP) + ":3000");
  int get = http.GET();
  while (get==-1)
  {
    get = http.GET();
    Serial.println(get);
    delay(1000);
  } 
  if (get==200)
  {
    String payload = http.getString();
    char doc[500];
    payload.replace("\n", "");
    payload.trim();
    payload.toCharArray(doc, 500);
    Serial.println("Fetched");
    JsonDocument json;
    deserializeJson(json, doc);
    ssid = json[0]["ssid"];
    password = json[0]["password"];
    ip = json[0]["IP"];
    const char* abs =json[0]["ssid"];
    const char* sba =json[0]["password"];

    File db = SD_MMC.open("/data.json", FILE_WRITE);
    JsonDocument db_write;
    db_write["IP"] = ip;
    db_write["ssid"] = ssid;
    db_write["password"] = password;
    serializeJson(db_write, db);
    db.close();
    http.end();
    StartConnection(ssid,password);
    HTTPClient http2;
    http2.begin("http://" + String(ip) + ":3000/IP");
    Serial.println("http://" + String(ip) + ":3000/IP");
    http2.addHeader("Content-Type", "application/json");
    int x = http2.POST("{\"IP\":\"" + String(WiFi.localIP()) + "\"}");
    String ip = IpAddress2String(WiFi.localIP());
    Serial.println(ip);
    Serial.println(x);
    while (x!=200)
    {
      //http2.addHeader("Content-Type", "application/json");
      x = http2.POST("{\"IP\":\"" + ip + "\"}");
      Serial.println(x);
      if (x==200)
      {
        break;
      }
    }
    http2.end();
  }
}
String IpAddress2String(const IPAddress& ipAddress)
{
  return String(ipAddress[0]) + String(".") +\
  String(ipAddress[1]) + String(".") +\
  String(ipAddress[2]) + String(".") +\
  String(ipAddress[3])  ; 
}
void loop() {
  //put your main code here, to run repeatedly:
  server.handleClient();
}