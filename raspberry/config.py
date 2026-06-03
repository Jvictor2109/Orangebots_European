"""
config.py — Fonte única de verdade para todas as constantes.
Edita aqui; todos os módulos importam daqui.
"""

# ── Heading ───────────────────────────────────────────────────────────────────
NORTH, EAST, SOUTH, WEST = 0, 1, 2, 3

DIRECTION_NAME  = {NORTH: "Norte", EAST: "Leste", SOUTH: "Sul", WEST: "Oeste"}
DIRECTION_DELTA = {NORTH: (0, 1), EAST: (1, 0), SOUTH: (0, -1), WEST: (-1, 0)}
DELTA_TO_DIR    = {v: k for k, v in DIRECTION_DELTA.items()}
DIRECTION_ANGLE = {NORTH: 0.0, EAST: 90.0, SOUTH: 180.0, WEST: 270.0}

# ── Geometria e sensoriamento ─────────────────────────────────────────────────
CELL_DISTANCE_CM  = 30.0    # Comprimento de uma célula (cm)
WALL_THRESHOLD_CM = 15.0    # Dist. <= threshold → parede detetada (cm)
DR_POLL_INTERVAL  = 0.20    # Intervalo entre leituras de encoder (s)

# ── Velocidades ───────────────────────────────────────────────────────────────
MOTOR_SPEED       = 35      # Velocidade base de avanço (0-100)
RAMP_SPEED        = 60      # Velocidade ao subir/descer rampa

# ── Correção de heading durante avanço (P-controller IMU) ─────────────────────
HEADING_KP       = 0.5      # Ganho proporcional — ajustar em campo
MAX_HEADING_CORR = 15       # Correção máxima por lado (unidades de velocidade)
HEADING_CORR_INTERVAL = 5   # Corrige a cada N ciclos de encoder

# ── Rotação (IMU-based) ───────────────────────────────────────────────────────
TURN_TOLERANCE   = 10.0      # graus — critério de paragem
TURN_SLOW_ZONE   = 50.0     # graus — zona de desaceleração
TURN_SPEED_FAST  = 25
TURN_SPEED_SLOW  = 20
TURN_SETTLED_CYCLES = 5     # Ciclos consecutivos dentro de tolerância para confirmar
TURN_TIMEOUT     = 8.0      # s — proteção contra rotação infinita

# ── Rampa ─────────────────────────────────────────────────────────────────────
RAMP_ENTER_DEG   = 172.0    # Inclinação abaixo desta → em rampa
RAMP_EXIT_DEG    = 177.0    # Inclinação acima desta → rampa concluída
RAMP_TIMEOUT_S   = 6.0      # s — timeout máximo na rampa
RAMP_DOWN_SPEED  = 30       # Velocidade controlada ao descer rampa
RAMP_CENTERING_CM    = 15.0 # cm — distância a avançar após nivelar para centrar no tile
RAMP_CENTERING_SPEED = 30   # Velocidade lenta para centralização pós-rampa

# ── Timer de missão ───────────────────────────────────────────────────────────
MISSION_TIMEOUT_S   = 7 * 60 + 30  # 7m30 → para exploração e regressa
BACKTRACK_TIMEOUT_S = 45           # s — timeout do regresso a (0,0)

# ── Serial ────────────────────────────────────────────────────────────────────
SERIAL_RETRIES    = 3
SERIAL_RETRY_WAIT = 0.05    # s entre tentativas

# ── IMU ───────────────────────────────────────────────────────────────────────
MAG_OFFSET = (-7.3500, 4.5750)
MAG_SCALE  = (0.9841, 1.0164)
IMU_CALIBRATION_SAMPLES = 5  # Leituras iniciais para confirmar heading estável
