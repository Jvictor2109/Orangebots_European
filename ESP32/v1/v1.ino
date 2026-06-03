void setup() {
  Serial.begin(115200);
  Serial2.begin(115200, SERIAL_8N1, 16, 17);
}

void loop() {
  Serial2.println("PING");
  delay(100);

  if(Serial2.available()){
    String resposta = Serial2.readStringUntil('\n');
    Serial.println(resposta);
  }
  else{
    Serial.println("Nada recebido");
  }
}