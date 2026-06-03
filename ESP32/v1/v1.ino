void setup() {
  Serial2.begin(115200);
}

void loop() {
  if (Serial2.available()) {
    String msg = Serial2.readStringUntil('\n');
    Serial2.println("ECHO: " + msg);
  }
}