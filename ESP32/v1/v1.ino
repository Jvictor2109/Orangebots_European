#include <Ultrasonic.h>
#include <ESP32Servo.h>

// ======================== MOTOR STATE ========================
int speeds[4] = {0, 0, 0, 0};

// ===================== UART (PI) =====================
HardwareSerial piSerial(2);
HardwareSerial* activeSerial;

// ===================== SERVO =====================
Servo vcServo;

// ===================== ULTRASONIC =====================
// Mapeamento físico: sonic1=ESQ, sonic2=FRENTE, sonic3=DIR, sonic4=TRÁS
Ultrasonic sonicLeft(21, 19);
Ultrasonic sonicFront(12, 13);
Ultrasonic sonicRight(23, 22);
Ultrasonic sonicBack(2, 15);

// ===================== MOTOR PINS =====================
// v1=FE(0)  v2=FD(1)  v3=TE(2)  v4=TD(3)
int speedpins[] = {5,18,19,21};
int dirpins[]   = {15,2,0,4};

// ===================== ENCODER =====================
volatile unsigned long pulseCount[4] = {0, 0, 0, 0};
int motorReadPin[] = {35, 34, 39, 36};

// ===================== COMPENSAÇÃO LATERAL =====================
float sideCompGain      = 1.5;
int   sideCompThreshold = 10;       // cm — ativa compensação abaixo disto
unsigned long lastCompTime = 0;
const int COMP_INTERVAL = 200;      // ms

// Valores em cache (evita ler sonics dentro do handler MC)
float cachedLeftComp  = 0;
float cachedRightComp = 0;

// ===================== INTERRUPTS =====================
void IRAM_ATTR countPulse1() { pulseCount[0]++; }
void IRAM_ATTR countPulse2() { pulseCount[1]++; }
void IRAM_ATTR countPulse3() { pulseCount[2]++; }
void IRAM_ATTR countPulse4() { pulseCount[3]++; }

// ===================== PROTOTYPES =====================
void setMotorSpeed(int[]);
void applyMotorsWithComp();
void updateCompensation();
bool isTranslating();

// ===================== SETUP =====================
void setup()
{
  Serial.begin(115200);
  piSerial.begin(115200, SERIAL_8N1, 16, 17);

  // Timeout curto para parseInt (evita bloqueio em dados parciais)
  piSerial.setTimeout(200);
  Serial.setTimeout(200);

  for (int i = 0; i < 4; i++)
    pinMode(motorReadPin[i], INPUT);

  attachInterrupt(digitalPinToInterrupt(motorReadPin[0]), countPulse1, RISING);
  attachInterrupt(digitalPinToInterrupt(motorReadPin[1]), countPulse2, RISING);
  attachInterrupt(digitalPinToInterrupt(motorReadPin[2]), countPulse3, RISING);
  attachInterrupt(digitalPinToInterrupt(motorReadPin[3]), countPulse4, RISING);

  vcServo.setPeriodHertz(50);
  vcServo.attach(27, 500, 2400);
  vcServo.write(0);

  for (int i = 0; i < 4; i++)
  {
    ledcAttach(speedpins[i], 25000, 8);
    pinMode(dirpins[i], OUTPUT);
  }

  int zero[4] = {0, 0, 0, 0};
  setMotorSpeed(zero);
}

// ===================== LOOP =====================
void loop()
{
  // ── Compensação lateral periódica ─────────────────────────────────────────
  if (millis() - lastCompTime >= COMP_INTERVAL)
  {
    updateCompensation();
    if (isTranslating())
      applyMotorsWithComp();
    lastCompTime = millis();
  }

  // ── Seleção de serial ─────────────────────────────────────────────────────
  if (piSerial.available())
    activeSerial = &piSerial;
  else if (Serial.available())
    activeSerial = (HardwareSerial*)&Serial;
  else
    return;

  // ── Leitura do comando (2 letras + separador) ─────────────────────────────
  String mode = "";
  mode += (char)activeSerial->read();
  mode += (char)activeSerial->read();
  activeSerial->read(); // descarta separador (espaço ou \n)

  Serial.print("CMD: ");
  Serial.println(mode);

  // ═══════════════════════════════════════════════════════════════════════════
  // COMANDOS
  // ═══════════════════════════════════════════════════════════════════════════

  // ── PG — Ping ─────────────────────────────────────────────────────────────
  if (mode == "PG")
  {
    activeSerial->println("OK");
  }

  // ── MC — Motor Control ────────────────────────────────────────────────────
  else if (mode == "MC")
  {
    for (int i = 0; i < 4; i++)
    {
      int speed = activeSerial->parseInt();
      activeSerial->read(); // descarta separador
      speeds[i] = constrain(speed, -100, 100);
    }

    // Aplica com compensação lateral se estiver em translação
    if (isTranslating())
      applyMotorsWithComp();
    else
      setMotorSpeed(speeds);

    activeSerial->println("OK");

    Serial.printf("  MC: [%d, %d, %d, %d]\n", speeds[0], speeds[1], speeds[2], speeds[3]);
  }

  // ── SR — Sensor Reading (ultrassónicos) ───────────────────────────────────
  else if (mode == "SR")
  {
    int left  = sonicLeft.read();
    int front = sonicFront.read();
    int right = sonicRight.read();

    // Resposta: esq,frente,dir (3 valores)
    activeSerial->print(left);
    activeSerial->print(",");
    activeSerial->print(front);
    activeSerial->print(",");
    activeSerial->println(right);

    Serial.printf("  SR: L=%d F=%d R=%d\n", left, front, right);
  }

  // ── MR — Motor Read (encoders) ────────────────────────────────────────────
  else if (mode == "MR")
  {
    float d[4];
    for (int i = 0; i < 4; i++)
      d[i] = pulseCount[i] * 0.756;

    // Resposta: e1,e2,e3,e4 (4 valores, sem ângulo)
    for (int i = 0; i < 4; i++)
    {
      activeSerial->print(d[i]);
      if (i < 3) activeSerial->print(",");
    }
    activeSerial->println();

    Serial.printf("  MR: %.1f, %.1f, %.1f, %.1f\n", d[0], d[1], d[2], d[3]);
  }

  // ── MZ — Motor/encoder Zero (reset) ───────────────────────────────────────
  else if (mode == "MZ")
  {
    for (int i = 0; i < 4; i++)
      pulseCount[i] = 0;

    activeSerial->println("OK");
    Serial.println("  MZ: encoders reset");
  }

  // ── VC — Victim Confirmed (kit de resgate) ────────────────────────────────
  else if (mode == "VC")
  {
    vcServo.write(90);
    delay(1000);
    vcServo.write(0);
    activeSerial->println("OK");
    Serial.println("  VC: servo ativado");
  }

  // ── Comando desconhecido — responde OK para não bloquear o Pi ─────────────
  else
  {
    activeSerial->println("OK");
    Serial.print("  CMD desconhecido: ");
    Serial.println(mode);
  }

  // ── Flush de bytes residuais (ex: \r\n do Serial Monitor) ─────────────────
  while (activeSerial->available())
  {
    if (activeSerial->read() == '\n') break;
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// COMPENSAÇÃO LATERAL
// ═════════════════════════════════════════════════════════════════════════════

bool isTranslating()
{
  // Translação = todos os motores no mesmo sentido (não parado, não a rodar)
  bool hasPos = false, hasNeg = false, allZero = true;
  for (int i = 0; i < 4; i++)
  {
    if (speeds[i] > 0) { hasPos = true; allZero = false; }
    if (speeds[i] < 0) { hasNeg = true; allZero = false; }
  }
  return !allZero && !(hasPos && hasNeg);
}

void updateCompensation()
{
  int leftDist  = sonicLeft.read();
  int rightDist = sonicRight.read();

  // Quanto mais perto da parede, MAIOR a compensação
  if (leftDist > 0 && leftDist <= sideCompThreshold)
    cachedLeftComp = (sideCompThreshold - leftDist) * sideCompGain;
  else
    cachedLeftComp = 0;

  if (rightDist > 0 && rightDist <= sideCompThreshold)
    cachedRightComp = (sideCompThreshold - rightDist) * sideCompGain;
  else
    cachedRightComp = 0;

  if (cachedLeftComp > 0 || cachedRightComp > 0)
    Serial.printf("  COMP: Ldist=%d(+%.1f) Rdist=%d(+%.1f)\n",
                  leftDist, cachedLeftComp, rightDist, cachedRightComp);
}

void applyMotorsWithComp()
{
  int compSpeeds[4];
  for (int i = 0; i < 4; i++)
  {
    float comp;
    // Motores esquerdos (0,2): compensação esquerda acelera → afasta da parede esq
    // Motores direitos  (1,3): compensação direita acelera → afasta da parede dir
    if (i == 0 || i == 2)
      comp = cachedLeftComp;
    else
      comp = cachedRightComp;

    // Inverte compensação se o motor está em marcha-atrás
    if (speeds[i] < 0)
      comp = -comp;

    compSpeeds[i] = constrain(speeds[i] + (int)comp, -100, 100);
  }
  setMotorSpeed(compSpeeds);
}

// ═════════════════════════════════════════════════════════════════════════════
// CONTROLO DE MOTORES
// ═════════════════════════════════════════════════════════════════════════════

void setMotorSpeed(int velocidades[])
{
  for (int i = 0; i < 4; i++)
  {
    int speed = velocidades[i];
    bool inv;

    // Motores do lado direito (1,3) têm lógica de direção invertida
    if (i == 1 || i == 3)
      inv = (speed <= 0);
    else
      inv = (speed > 0);

    int mappedSpeed = map(abs(speed), 0, 100, 255, 0);

    digitalWrite(dirpins[i], inv ? HIGH : LOW);
    ledcWrite(speedpins[i], mappedSpeed);
  }
}