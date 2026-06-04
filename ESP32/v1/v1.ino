// Merged ESP32 sketch
// Priority given to second code logic/features
// Pin assignments and motor direction logic kept from first code

#include <Ultrasonic.h>
#include <ESP32Servo.h>

//========================= COMP DEBUG ==================
bool compReport = false;
int SCompDistance = 10;
float gain = 5;

// ======================== FDS ========================
int speeds[4] = {};
bool mcActive = false;

// ===================== UART (PI) =====================
HardwareSerial piSerial(2);
HardwareSerial* activeSerial;

// ===================== SERVO =====================
Servo lcservo;

// ===================== ULTRASONIC =====================
Ultrasonic sonic1(33,32);
Ultrasonic sonic2(26,25);
Ultrasonic sonic3(22,23);

int sonicDistances[4] = {0,0,0,0};

// ===================== MOTOR PINS =====================
int speedpins[] = {5,18,19,21};
int dirpins[]   = {15,2,0,4};

// ===================== ENCODER =====================
volatile unsigned long pulseCount[4] = {0,0,0,0};
float motorDistance[4] = {0,0,0,0};
int motorReadPin[] = {35,34,39,36};

// ===================== ROBOT STATE =====================
float robotAngleRad = 0;
float robotAngleDeg = 0;

// ===================== TIMERS =====================
unsigned long lastcomp = 0;

// ===================== INTERRUPTS =====================
void countPulse1(){ pulseCount[0]++; }
void countPulse2(){ pulseCount[1]++; }
void countPulse3(){ pulseCount[2]++; }
void countPulse4(){ pulseCount[3]++; }

void setMotorSpeed(int[]);
void updateMotorDistance();

void setup()
{
  Serial.begin(115200);
  piSerial.begin(115200, SERIAL_8N1, 16, 17);

  // added robustness
  Serial.setTimeout(200);
  piSerial.setTimeout(200);

  Serial.println("ESP32 Started");
  Serial.println("UART2 RX=16 TX=17");

  for(int i=0;i<4;i++)
    pinMode(motorReadPin[i], INPUT);

  attachInterrupt(digitalPinToInterrupt(motorReadPin[0]), countPulse1, RISING);
  attachInterrupt(digitalPinToInterrupt(motorReadPin[1]), countPulse2, RISING);
  attachInterrupt(digitalPinToInterrupt(motorReadPin[2]), countPulse3, RISING);
  attachInterrupt(digitalPinToInterrupt(motorReadPin[3]), countPulse4, RISING);

  lcservo.setPeriodHertz(50);
  lcservo.attach(27, 500, 2400);

  for(int i=0;i<4;i++)
  {
    ledcAttach(speedpins[i], 25000, 8);
    pinMode(dirpins[i], OUTPUT);
  }

  int zero[4]={0,0,0,0};
  setMotorSpeed(zero);
}

void loop()
{
  // ================= COMPENSATION =================
  if(millis() - lastcomp >= 200)
{
  bool allForward = true;

  for(int i = 0; i < 4; i++)
  {
    if(speeds[i] <= 0)
    {
      allForward = false;
      break;
    }
  }

  if(allForward)
  {
    float lc = sonic1.read();
    float rc = sonic3.read();

    if(lc < 10 && lc > 0) lc = lc * gain;
    else lc = 0;

    if(rc < 10 && rc > 0) rc = rc * gain;
    else rc = 0;

    int compSpeeds[4];

    for(int i=0;i<4;i++)
    {
      int base = speeds[i];

      if(i == 0 || i == 2)
        compSpeeds[i] = base + lc;
      else
        compSpeeds[i] = base + rc;
    }

    if(compReport)
    {
      Serial.println("---- COMP UPDATE ----");
      Serial.print("LC: "); Serial.println(lc);
      Serial.print("RC: "); Serial.println(rc);
    }

    setMotorSpeed(compSpeeds);
  }

  lastcomp = millis();
}
  // ================= SERIAL SELECTION =================
  if(piSerial.available())
    activeSerial = &piSerial;
  else if(Serial.available())
    activeSerial = (HardwareSerial*)&Serial;
  else
    return;

  if(activeSerial->available() < 3)
    return;

  String mode="";
  mode += (char)activeSerial->read();
  mode += (char)activeSerial->read();
  activeSerial->read();

  Serial.print("[RX ");
  Serial.print(activeSerial == &piSerial ? "PI" : "USB");
  Serial.print("] Command: ");
  Serial.println(mode);

  // ================= COMMANDS =================

  if(mode == "MC")
  {
    for(int i=0;i<4;i++)
    {
      int speed = activeSerial->parseInt();
      activeSerial->read();

      speed = constrain(speed,-100,100);
      speeds[i] = speed;

      Serial.print("Motor ");
      Serial.print(i);
      Serial.print(": ");
      Serial.println(speed);
    }

    setMotorSpeed(speeds);
    activeSerial->println("OK");   // ADDED
  }

  else if(mode == "CR")
  {
    compReport = !compReport;

    Serial.println(compReport ? "COMP ON" : "COMP OFF");
    piSerial.println(compReport ? "COMP ON" : "COMP OFF");
  }

  else if(mode == "SR")
  {
    int raw[4];

    raw[0]=sonic1.read(); delay(50);
    raw[1]=sonic2.read(); delay(50);
    raw[2]=sonic3.read(); delay(50);

    sonicDistances[3]=0;

    for(int i=0;i<3;i++)
    {
      int d=raw[i];

      if(d==0) d=10;
      else if(d<3) d=3;
      else if(d>100) d=10;

      sonicDistances[i]=d;
    }

    Serial.print("SR -> ");

    for(int i=0;i<4;i++)
    {
      Serial.print(sonicDistances[i]);
      if(i<3) Serial.print(",");

      piSerial.print(sonicDistances[i]);
      if(i<3) piSerial.print(",");
    }

    Serial.println();
    piSerial.println();
  }

else if(mode == "LC")
{
  int kits = activeSerial->parseInt();
  activeSerial->read();
  kits = constrain(kits, 1, 4);


  if(kits <= 0)
    kits = 1;

  Serial.print("Launching ");
  Serial.print(kits);
  Serial.println(" kit(s)...");

  for(int i = 0; i < kits; i++)
  {
    lcservo.write(60);
    delay(1000);

    lcservo.write(0);
    delay(1000);
  }

  activeSerial->println("OK");
}

 else if(mode == "MR")
{
  updateMotorDistance();

  Serial.print("MR -> ");

  for(int i = 0; i < 4; i++)
  {
    Serial.print(motorDistance[i], 2);
    Serial.print(",");

    piSerial.print(motorDistance[i], 2);
    piSerial.print(",");
  }

  // angle at the end
  Serial.print(robotAngleDeg, 2);
  piSerial.print(robotAngleDeg, 2);

  Serial.println();
  piSerial.println();
}
  else if(mode == "PG")
  {
    Serial.println("Ping received -> OK");
    piSerial.println("OK");
  }

  else if(mode == "MZ")   // ADDED
  {
    for(int i=0;i<4;i++)
      pulseCount[i] = 0;

    Serial.println("Encoders Reset");
    activeSerial->println("OK");
  }

  else
  {
    Serial.print("Unknown CMD: ");
    Serial.println(mode);

    activeSerial->println("OK");
  }
}

// ================= MOTOR CONTROL =================

void setMotorSpeed(int velocidades[])
{
  bool inv;

  for(int i=0;i<4;i++)
  {
    int speed = velocidades[i];

    if(i == 0 || i == 2)
      inv = (speed <= 0);
    else
      inv = (speed > 0);

    speed = map(abs(speed),0,100,255,0);

    digitalWrite(dirpins[i], inv ? HIGH : LOW);
    ledcWrite(speedpins[i], speed);
  }
}

void updateMotorDistance()
{
  for(int i=0;i<4;i++)
    motorDistance[i] = (pulseCount[i] * 0.756)/10;

  float leftDist  = (motorDistance[0] + motorDistance[2]) / 2.0;
  float rightDist = (motorDistance[1] + motorDistance[3]) / 2.0;

  float delta = rightDist - leftDist;

  robotAngleRad = delta / 13 ;
  robotAngleDeg = (robotAngleRad * 57.2958);
}