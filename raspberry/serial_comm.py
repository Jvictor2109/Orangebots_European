"""
serial_comm.py — Abstração serial com retry automático e simulação corrigida.

Protocolo ESP32 (ver ESP32_SPEC.md para detalhes completos):
  PG           → "OK"
  SR           → "esq,frente,dir"   (cm, 3 valores)
  MZ           → "OK"               (reset de encoders a zero)
  MR           → "e1,e2,e3,e4"      (cm acumulados desde último MRZ)
  MC v1 v2 v3 v4 → "OK"            (motor speeds, -100 a 100)
  VC           → "OK"               (trigger kit de resgate)
"""

import time
from config import SERIAL_RETRIES, SERIAL_RETRY_WAIT


class SerialComm:

    def __init__(self, port=None, baudrate=115200, simulate=False):
        self.simulate = simulate
        self.serial   = None

        # Estado interno da simulação
        self._sim_enc     = 0.0     # Distância acumulada (cm)
        self._sim_moving  = False   # Motores ligados?
        self._sim_reverse = False   # Em marcha-atrás?

        if not simulate:
            import serial as pyserial
            self.serial = pyserial.Serial(port, baudrate, timeout=2)
            time.sleep(2)
            print(f"[SERIAL] Conectado: {port} @ {baudrate}")
        else:
            print("[SERIAL] Modo SIMULAÇÃO ativo")

    # ── API pública ───────────────────────────────────────────────────────────

    def ping(self, max_tries=15, interval=2):
        if self.simulate:
            print("[PING] Simulação — OK")
            return True

        print("[PING] A verificar ESP32...")
        for i in range(1, max_tries + 1):
            resp = self._raw_send("PG")
            if resp == "OK":
                print(f"[PING] OK (tentativa {i})")
                return True
            print(f"[PING] {i}/{max_tries}: '{resp}'")
            time.sleep(interval)

        print("[PING] FALHA — ESP32 não responde")
        return False

    def send(self, command: str) -> str:
        if self.simulate:
            return self._simulate_send(command)
        return self._serial_send(command)

    def close(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
            print("[SERIAL] Porta fechada")

    # ── Serial com retry ──────────────────────────────────────────────────────

    def _serial_send(self, command: str) -> str:
        for attempt in range(SERIAL_RETRIES):
            resp = self._raw_send(command)
            if resp:
                return resp
            print(f"[SERIAL] Retry {attempt + 1}/{SERIAL_RETRIES}: '{command}'")
            time.sleep(SERIAL_RETRY_WAIT)

        print(f"[SERIAL] FALHA TOTAL: '{command}'")
        return ""

    def _raw_send(self, command: str) -> str:
        try:
            self.serial.reset_input_buffer()
            self.serial.write((command + "\n").encode())
            self.serial.flush()
            return self.serial.readline().decode("utf-8", errors="replace").strip()
        except Exception as e:
            print(f"[SERIAL] Exceção: {e}")
            return ""

    # ── Simulação ─────────────────────────────────────────────────────────────
    # Distingue translação de rotação. MRZ reseta encoder. MR incrementa
    # apenas em translação; rotação não afeta o contador de distância.

    def _simulate_send(self, command: str) -> str:
        cmd = command.strip()

        # ── Ping ──
        if cmd == "PG":
            return "OK"

        # ── Ultrassónicos ──
        elif cmd == "SR":
            raw = input("  [SIM SR] esq,frente,dir (cm, ex: 35,5,40): ").strip()
            return raw if raw else "35,35,35"

        # ── Reset encoder ──
        elif cmd == "MZ":
            self._sim_enc = 0.0
            return "OK"

        # ── Leitura de encoder ──
        elif cmd == "MR":
            if self._sim_moving and not self._sim_reverse:
                # Translação: +10 cm por chamada (simula ~10ms a MOTOR_SPEED)
                self._sim_enc += 10.0
            elif self._sim_moving and self._sim_reverse:
                # Marcha-atrás: decrementa (mas retorna abs para consistência)
                self._sim_enc -= 10.0
            e = self._sim_enc
            return f"{e},{e},{e},{e}"

        # ── Motor control ──
        elif cmd.startswith("MC "):
            parts = cmd.split()
            try:
                speeds = [int(p) for p in parts[1:5]]
            except (ValueError, IndexError):
                return "OK"

            all_zero    = all(s == 0 for s in speeds)
            all_forward = all(s > 0  for s in speeds)
            all_reverse = all(s < 0  for s in speeds)

            if all_zero:
                self._sim_moving  = False
                self._sim_reverse = False
            elif all_forward:
                self._sim_moving  = True
                self._sim_reverse = False
            elif all_reverse:
                self._sim_moving  = True
                self._sim_reverse = True
            else:
                # Rotação (motores em sentidos opostos) — não afeta encoder de translação
                self._sim_moving  = False

            return "OK"

        # ── Kit de resgate ──
        elif cmd == "VC":
            print("  [SIM VC] Kit de resgate ativado")
            return "OK"

        # ── Outros ──
        else:
            return "OK"
