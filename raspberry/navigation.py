"""
navigation.py — Controlo de movimento de baixo nível.

  angle_diff(target, current)          → diferença angular com sinal
  turn_to(target_cardinal, ...)        → rotação IMU com TURN_SLOW_ZONE + settled count
  move_forward(serial, imu, floor, cardinal) → avanço com heading-hold + rampa + preto
  move_to_direction(current, target, ...)    → turn + forward + drift check
"""

import time
from config import *


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITÁRIOS
# ═══════════════════════════════════════════════════════════════════════════════

def angle_diff(target: float, current: float) -> float:
    """
    Diferença angular com sinal no intervalo [-180, 180].
    Positivo = virar direita; negativo = virar esquerda.
    """
    return (target - current + 180.0) % 360.0 - 180.0


def _robust_distance(encoder_vals: list[float]) -> float:
    """
    Distância robusta usando mediana dos encoders com valor ≥ 0.
    Descarta rodas com slip negativo sem destruir a leitura total.
    """
    valid = sorted(v for v in encoder_vals if v >= -2.0)  # -2cm = tolerância de ruído
    if not valid:
        return 0.0
    n = len(valid)
    mid = n // 2
    print(f"Encoder: {(valid[mid - 1] + valid[mid]) / 2.0 if n % 2 == 0 else valid[mid]}")
    return (valid[mid - 1] + valid[mid]) / 2.0 if n % 2 == 0 else valid[mid]


def _parse_encoder(response: str) -> list[float] | None:
    """Faz parse de '10.0,10.0,10.0,10.0' → [10.0, 10.0, 10.0, 10.0]. Retorna None em erro."""
    if not response:
        return None
    try:
        # Aceita 4 ou 5 campos (ignora campo extra de ângulo, se presente)
        parts = response.split(",")
        return [float(v.strip()) for v in parts]
    except (ValueError, IndexError):
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# ROTAÇÃO — IMU-BASED (corrige a falha crítica do main.py original)
# ═══════════════════════════════════════════════════════════════════════════════

def turn_to(target_cardinal: int, serial, imu) -> bool:
    """
    Roda o robot para o cardinal absoluto usando a IMU como referência.

    Melhorias vs original:
    - TURN_SLOW_ZONE implementado (desacelera ao aproximar do alvo)
    - TURN_SETTLED_CYCLES: exige N leituras consecutivas dentro de tolerância
    - Deteção de overshoot: para se passa o alvo sem atingir tolerância
    - Timeout com mensagem diagnóstica

    Retorna True se concluiu OK, False se timeout.
    """
    target_angle = DIRECTION_ANGLE[target_cardinal]
    start        = time.time()
    settled      = 0
    last_sign    = None   # para detetar overshoot

    # Deteção de stub: se IMU não tem hardware, simula rotação instantânea
    heading_deg, _ = imu.get_heading()
    if heading_deg is None:
        print(f"  [TURN] IMU stub — rotação simulada para {DIRECTION_NAME[target_cardinal]}")
        time.sleep(0.1)
        return True

    while True:
        # ── Timeout ──────────────────────────────────────────────────────────
        if time.time() - start > TURN_TIMEOUT:
            serial.send("MC 0 0 0 0")
            print(f"  [TURN] Timeout → {DIRECTION_NAME[target_cardinal]}")
            return False

        # ── Leitura IMU ─────────────────────────── Nao usada ──────────────────────────
        heading_deg, _ = imu.get_heading()
        if heading_deg is None:
            time.sleep(0.05)
            continue

        # Leitura encoders
        mr = serial.send("MR")
        encoder_deg = mr[-1]


        diff = angle_diff(target_angle, encoder_deg)

        # ── Critério de chegada ───────────────────────────────────────────────
        if abs(diff) <= TURN_TOLERANCE:
            settled += 1
            serial.send("MC 0 0 0 0")
            if settled >= TURN_SETTLED_CYCLES:
                break
            time.sleep(0.02)
            continue
        else:
            settled = 0

        # ── Deteção de overshoot ──────────────────────────────────────────────
        sign = 1 if diff > 0 else -1
        if last_sign is not None and sign != last_sign:
            # Passou do alvo sem entrar em tolerância → para e aceita posição atual
            serial.send("MC 0 0 0 0")
            print(f"  [TURN] Overshoot detetado (diff={diff:.1f}°), a aceitar posição")
            break
        last_sign = sign

        # ── Velocidade proporcional com slow zone ─────────────────────────────
        speed = TURN_SPEED_SLOW if abs(diff) < TURN_SLOW_ZONE else TURN_SPEED_FAST

        if diff < 0:   # Virar direita
            serial.send(f"MC -{speed} {speed} -{speed} {speed}")
        else:          # Virar esquerda
            serial.send(f"MC {speed} -{speed} {speed} -{speed}")

        time.sleep(0.02)

    serial.send("MC 0 0 0 0")
    time.sleep(0.1)  # Deixa o robot estabilizar mecanicamente
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# AVANÇO — com heading-hold IMU, deteção de rampa e tile preto
# ═══════════════════════════════════════════════════════════════════════════════

def move_forward(serial, imu, floor_sensor, current_cardinal: int) -> str:
    """
    Avança uma célula (CELL_DISTANCE_CM) com:
      1. Reset de encoders (MZ) antes de ligar motores
      2. Correção de heading via IMU a cada HEADING_CORR_INTERVAL ciclos
      3. Deteção de tile preto → recuo + retorno "BLACK"
      4. Deteção de rampa → velocidade aumentada + retorno "RAMP"

    Retorna: "OK" | "BLACK" | "RAMP"
    """
    target_heading = DIRECTION_ANGLE[current_cardinal]

    # ── Reset encoders e arranque ─────────────────────────────────────────────
    serial.send("MZ")
    serial.send(f"MC {MOTOR_SPEED} {MOTOR_SPEED} {MOTOR_SPEED} {MOTOR_SPEED}")

    cycle   = 0
    distance = 0.0

    while True:
        # 1. Tile preto ────────────────────────────────────────────────────────
        if floor_sensor.is_preto():
            serial.send("MC 0 0 0 0")
            time.sleep(0.1)
            _reverse_by(serial, distance)
            return "BLACK"

        # 2. Rampa (a cada 3 ciclos — IMU é rápido mas não precisamos a 100 Hz) ─
        if cycle % 3 == 0:
            incl = imu.get_inclination()
            if incl is not None and incl <= RAMP_ENTER_DEG:
                return _traverse_ramp(serial, imu)

        # 3. Correção de heading ────────────────────────────────────────────────
        if cycle % HEADING_CORR_INTERVAL == 0:
            _apply_heading_correction(serial, imu, target_heading)

        cycle += 1

        # 4. Distância por encoders (valores absolutos desde MZ) ───────────────
        resp = serial.send("MR")
        vals = _parse_encoder(resp)
        if vals is not None:
            vals = vals[:4]
            distance = _robust_distance([abs(v) for v in vals])
            print(distance)

        if distance >= CELL_DISTANCE_CM:
            break

        time.sleep(DR_POLL_INTERVAL)

    serial.send("MC 0 0 0 0")
    return "OK"


# ═══════════════════════════════════════════════════════════════════════════════
# WRAPPER: TURN + FORWARD + DRIFT CHECK
# ═══════════════════════════════════════════════════════════════════════════════

def move_to_direction(current_dir: int, target_dir: int,
                      serial, imu, floor_sensor) -> tuple[int, str]:
    """
    Roda (se necessário) e avança uma célula.
    Após o avanço verifica drift de heading e corrige se > 10°.

    Retorna (novo_heading, resposta): heading é sempre target_dir.
    Respostas possíveis: "OK", "BLACK", "RAMP_UP", "RAMP_DOWN".
    """
    if current_dir != target_dir:
        print(f"  [NAV] Rodar {DIRECTION_NAME[current_dir]} → {DIRECTION_NAME[target_dir]}")
        turn_to(target_dir, serial, imu)

    print(f"  [NAV] Avançar → {DIRECTION_NAME[target_dir]}")
    response = move_forward(serial, imu, floor_sensor, target_dir)

    # Verifica drift após avanço normal (acumulado de vibração, skid, etc.)
    # Não faz drift check após rampa — a centralização pós-rampa já cuida do alinhamento
    if response == "OK":
        heading_deg, _ = imu.get_heading()
        if heading_deg is not None:
            drift = abs(angle_diff(DIRECTION_ANGLE[target_dir], heading_deg))
            if drift > 20.0:
                print(f"  [NAV] Drift após avanço: {drift:.1f}° — a corrigir")
                turn_to(target_dir, serial, imu)

    return target_dir, response


# ═══════════════════════════════════════════════════════════════════════════════
# FUNÇÕES AUXILIARES (internas)
# ═══════════════════════════════════════════════════════════════════════════════



def _apply_heading_correction(serial, imu, target_heading: float):
    """Aplica correção P de heading via diferença de velocidade nos motores."""
    heading_deg, _ = imu.get_heading()
    if heading_deg is None:
        return

    err  = angle_diff(target_heading, heading_deg)
    corr = int(HEADING_KP * err)
    corr = max(-MAX_HEADING_CORR, min(MAX_HEADING_CORR, corr))

    if abs(corr) < 2:  # Ignora correções insignificantes (evita jitter)
        return

    # v1,v3 = esquerda; v2,v4 = direita
    # diff > 0 (aponta muito à esq, precisa virar dir): esq mais lenta, dir mais rápida
    left  = MOTOR_SPEED - corr
    right = MOTOR_SPEED + corr
    serial.send(f"MC {left} {right} {left} {right}")


def _reverse_by(serial, distance: float):
    """
    Recua a distância indicada, com timeout de proteção de 5s.
    Reseta encoders (MZ) e usa valores absolutos.
    """
    if distance <= 1.0:
        return

    print(f"  [REV] Recuando {distance:.1f} cm")
    serial.send("MZ")
    serial.send(f"MC -{MOTOR_SPEED} -{MOTOR_SPEED} -{MOTOR_SPEED} -{MOTOR_SPEED}")
    start = time.time()

    while time.time() - start < 5.0:
        resp = serial.send("MR")
        vals = _parse_encoder(resp)
        if vals is not None:
            rev_dist = _robust_distance([abs(v) for v in vals])
            if rev_dist >= distance:
                break
        time.sleep(DR_POLL_INTERVAL)
    else:
        print("  [REV] Timeout no recuo!")

    serial.send("MC 0 0 0 0")


def _traverse_ramp(serial, imu) -> str:
    """
    Detecta se é subida ou descida via inclinação com sinal.
    Ajusta velocidade conforme a direção.
    Após nivelar, avança RAMP_CENTERING_CM para centrar no tile.

    Retorna "RAMP_UP" ou "RAMP_DOWN".
    """
    # ── 1. Determinar se é subida ou descida ──────────────────────────────────
    incl_abs = imu.get_inclination()
    incl_signed = imu.get_inclination_signed()

    if incl_signed is not None and incl_signed > 0:
        direction = "UP"
        ramp_speed = RAMP_SPEED
    else:
        direction = "DOWN"
        ramp_speed = RAMP_DOWN_SPEED

    print(f"  [RAMP] Detetada {direction} (abs={incl_abs:.1f}°, signed={incl_signed:.1f}°) — velocidade → {ramp_speed}")
    serial.send(f"MC {ramp_speed} {ramp_speed} {ramp_speed} {ramp_speed}")

    # ── 2. Aguardar até a inclinação normalizar (fim da rampa) ────────────────
    start = time.time()
    while time.time() - start < RAMP_TIMEOUT_S:
        inc = imu.get_inclination()
        if inc is not None and inc >= RAMP_EXIT_DEG:
            print(f"  [RAMP] Nivelou (incl={inc:.1f}°)")
            break
        time.sleep(0.05)
    else:
        print("  [RAMP] Timeout — a parar")

    serial.send("MC 0 0 0 0")
    time.sleep(0.1)  # Estabilizar mecanicamente

    # ── 3. Centralização pós-rampa: avançar até ao centro do tile ─────────────
    print(f"  [RAMP] Centrando no tile ({RAMP_CENTERING_CM:.0f}cm a {RAMP_CENTERING_SPEED})")
    serial.send("MZ")
    serial.send(f"MC {RAMP_CENTERING_SPEED} {RAMP_CENTERING_SPEED} {RAMP_CENTERING_SPEED} {RAMP_CENTERING_SPEED}")

    center_start = time.time()
    while time.time() - center_start < 5.0:  # timeout de segurança
        resp = serial.send("MR")
        vals = _parse_encoder(resp)
        if vals is not None:
            dist = _robust_distance([abs(v) for v in vals])
            if dist >= RAMP_CENTERING_CM:
                break
        time.sleep(DR_POLL_INTERVAL)
    else:
        print("  [RAMP] Timeout na centralização")

    serial.send("MC 0 0 0 0")

    result = f"RAMP_{direction}"
    print(f"  [RAMP] Concluída → {result}")
    return result
