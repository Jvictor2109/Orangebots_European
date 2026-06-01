"""
dfs.py — Exploração DFS iterativa com:
  - Mapeamento 3D (x, y, z) para suporte a múltiplos andares
  - Timer de missão (para quando faltar ~30s e regressa a (0,0,0))
  - Backtracking físico correto (sem time.sleep arbitrário)
  - Tratamento de tiles pretos, azuis, rampas (subida e descida)
  - Heading inicial com múltiplas leituras IMU para estabilidade
"""

import time
from config import *
from navigation import move_to_direction


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS DE GEOMETRIA
# ═══════════════════════════════════════════════════════════════════════════════

def relative_to_absolute(heading: int, relative: str) -> int:
    offsets = {"front": 0, "right": 1, "back": 2, "left": -1}
    return (heading + offsets[relative]) % 4


def direction_between(from_pos: tuple, to_pos: tuple) -> int:
    """Retorna o cardinal de from_pos → to_pos.
    Usa apenas as coordenadas (x, y), ignorando z (andar).
    """
    dx = to_pos[0] - from_pos[0]
    dy = to_pos[1] - from_pos[1]
    delta = (dx, dy)
    if delta not in DELTA_TO_DIR:
        raise ValueError(f"direction_between: delta inválido {delta} de {from_pos} para {to_pos}")
    return DELTA_TO_DIR[delta]


# ═══════════════════════════════════════════════════════════════════════════════
# LEITURA DE PAREDES
# ═══════════════════════════════════════════════════════════════════════════════

def read_walls(heading: int, serial) -> dict | None:
    """
    Envia SR, faz parse, converte em dict absoluto {cardinal: bool}.
    'trás' é assumido livre — viemos de lá (ver análise para limitação).
    Retorna None em falha de comunicação.
    """
    response = serial.send("SR")
    if not response:
        return None

    try:
        parts      = response.split(",")
        left_dist  = float(parts[0].strip())
        front_dist = float(parts[1].strip())
        right_dist = float(parts[2].strip())
    except (ValueError, IndexError):
        print(f"  [SR] Parse inválido: '{response}'")
        return None

    print(f"  [SR] esq={left_dist:.0f}cm  frente={front_dist:.0f}cm  dir={right_dist:.0f}cm")

    return {
        relative_to_absolute(heading, "front"): front_dist <= WALL_THRESHOLD_CM,
        relative_to_absolute(heading, "left"):  left_dist  <= WALL_THRESHOLD_CM,
        relative_to_absolute(heading, "right"): right_dist <= WALL_THRESHOLD_CM,
        relative_to_absolute(heading, "back"):  False,  # viemos de lá
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DFS PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

def explorar_labirinto(
    serial,
    imu,
    floor_sensor,
    victim_manager=None,
    use_camera: bool = True,
    mission_deadline: float | None = None,
):
    """
    DFS iterativo sem recursão.

    victim_manager: instância de VictimManager (ou None se câmara desativada)
    mission_deadline: float = time.time() + MISSION_TIMEOUT_S
    Quando o deadline é atingido, para a exploração e regressa a (0,0,0).
    """

    # ── Heading inicial estável ───────────────────────────────────────────────
    heading = _calibrate_initial_heading(imu)

    # ── Estado do DFS ───────────────────────────────────────────────────────────
    # Posições são tuplas 3D: (x, y, z) onde z = andar (0 = térreo)
    stack      = [(0, 0, 0)]       # Pilha do caminho atual (para backtracking)
    visited    = {(0, 0, 0)}       # Células confirmadas (robot chegou lá com OK/RAMP)
    cell_map   = {}             # {pos: [opções restantes]} — memória do mapa
    blocked    = set()          # Tiles pretos (intransponíveis)
    blue_tiles = []             # Tiles azuis encontrados
    victims    = []             # [(pos, tipo, valor, ...)]

    print("\n" + "=" * 52)
    print("[DFS] EXPLORAÇÃO INICIADA")
    print(f"      Posição: (0,0,0)  Heading: {DIRECTION_NAME[heading]}")
    if mission_deadline:
        secs = mission_deadline - time.time()
        print(f"      Timer de missão: {secs:.0f}s")
    print("=" * 52)

    # ─────────────────────────────────────────────────────────────────────────
    while stack:

        # ── Verifica timer ───────────────────────────────────────────────────
        if mission_deadline and time.time() >= mission_deadline:
            print("\n[TIMER] Tempo esgotado! A regressar a (0,0,0).")
            heading = _return_to_start(stack, heading, serial, imu, floor_sensor)
            break

        pos = stack[-1]
        x, y, z = pos

        # ── FASE A: Sensoriamento (apenas na primeira visita) ─────────────────
        if pos not in cell_map:
            print(f"\n{'─' * 48}")
            print(f"[POS] ({x},{y},{z})  Heading: {DIRECTION_NAME[heading]}")

            # Leitura de paredes (até 3 tentativas em falha de comunicação)
            walls = _read_walls_reliable(heading, serial)
            if walls is None:
                print("[ERRO] Falha persistente de sensor. A abortar exploração.")
                break

            for d in [NORTH, EAST, SOUTH, WEST]:
                print(f"  {DIRECTION_NAME[d]:5s}: {'PAREDE' if walls[d] else 'livre'}")

            # Tile azul (sensor de chão) — verifica cor da célula atual
            cor = floor_sensor.get_cor()
            if cor == "azul":
                print(f"  [AZUL] Tile azul em {pos}")
                blue_tiles.append(pos)

            # Deteção de vítimas (câmara)
            if use_camera and victim_manager is not None:
                _check_victims(serial, victim_manager, pos, victims)

            # Monta opções: prioridade frente > direita > esquerda > trás
            # Opções guardam (cardinal, nx, ny) — z é resolvido após o movimento
            options = []
            for rel in ["front", "right", "left", "back"]:
                d = relative_to_absolute(heading, rel)
                if not walls[d]:
                    dx, dy = DIRECTION_DELTA[d]
                    options.append((d, x + dx, y + dy))

            cell_map[pos] = options

        # ── FASE B: Movimento DFS ─────────────────────────────────────────────
        moved = False
        while cell_map[pos]:
            direction, nx, ny = cell_map[pos].pop(0)

            # Verifica no andar atual primeiro
            next_pos = (nx, ny, z)
            if next_pos in blocked or next_pos in visited:
                if next_pos in visited:
                    print(f"  [!] {DIRECTION_NAME[direction]} → {next_pos} já visitado")
                continue

            print(f"\n  → {DIRECTION_NAME[direction]} → ({nx},{ny},?)")
            heading, resp = move_to_direction(heading, direction, serial, imu, floor_sensor)

            if resp == "BLACK":
                print(f"  [BLACK] Bloqueado: {next_pos}")
                blocked.add(next_pos)
                continue  # Robot já recuou — tenta próxima opção

            # Determinar a posição final com base na resposta
            if resp == "RAMP_UP":
                next_pos = (nx, ny, z + 1)
                print(f"  [RAMP] Subiu → andar {z + 1} → {next_pos}")
            elif resp == "RAMP_DOWN":
                next_pos = (nx, ny, z - 1)
                print(f"  [RAMP] Desceu → andar {z - 1} → {next_pos}")
            elif resp == "RAMP":
                # Retrocompatibilidade: trata como RAMP_UP
                next_pos = (nx, ny, z + 1)
                print(f"  [RAMP] (compat) Subiu → andar {z + 1} → {next_pos}")
            # else: resp == "OK" → next_pos já está correto com z atual

            visited.add(next_pos)
            stack.append(next_pos)
            moved = True
            break

        # ── FASE C: Backtracking ──────────────────────────────────────────────
        if not moved:
            stack.pop()
            if stack:
                prev = stack[-1]
                target_dir = direction_between(pos, prev)
                print(f"\n  ← Backtrack → {prev}")
                heading, _ = move_to_direction(heading, target_dir, serial, imu, floor_sensor)
                # Sem time.sleep(1) — a verificação de heading em move_to_direction é suficiente

    # ── Relatório final ───────────────────────────────────────────────────────
    _print_report(visited, blocked, blue_tiles, victims)


# ═══════════════════════════════════════════════════════════════════════════════
# FUNÇÕES AUXILIARES
# ═══════════════════════════════════════════════════════════════════════════════

def _calibrate_initial_heading(imu) -> int:
    """
    Lê IMU_CALIBRATION_SAMPLES vezes e usa a moda como heading inicial.
    Mais robusto que uma única leitura.
    """
    if not imu.calibrate_north():
        print("[IMU] Falha na calibração — Norte assumido")
        return NORTH

    readings = []
    for _ in range(IMU_CALIBRATION_SAMPLES):
        _, cardinal = imu.get_heading()
        if cardinal is not None:
            readings.append(cardinal)
        time.sleep(0.05)

    if not readings:
        print("[IMU] Sem leituras estáveis — Norte assumido")
        return NORTH

    heading = max(set(readings), key=readings.count)
    print(f"[IMU] Heading inicial: {DIRECTION_NAME[heading]} ({len(readings)}/{IMU_CALIBRATION_SAMPLES} leituras)")
    return heading


def _read_walls_reliable(heading: int, serial, retries: int = 3) -> dict | None:
    """Tenta ler paredes até `retries` vezes antes de desistir."""
    for i in range(retries):
        walls = read_walls(heading, serial)
        if walls is not None:
            return walls
        print(f"  [SR] Falha (tentativa {i + 1}/{retries})")
        time.sleep(0.1)
    return None


def _return_to_start(stack: list, heading: int, serial, imu, floor_sensor) -> int:
    """
    Percorre a pilha ao contrário até (0,0,0) dentro de BACKTRACK_TIMEOUT_S.
    Retorna o heading final.
    """
    deadline = time.time() + BACKTRACK_TIMEOUT_S

    while len(stack) > 1 and time.time() < deadline:
        pos  = stack.pop()
        prev = stack[-1]
        try:
            target_dir = direction_between(pos, prev)
        except ValueError:
            print(f"  [HOME] Erro de geometria {pos}→{prev}, a saltar")
            continue

        print(f"  [HOME] ← {prev}")
        heading, _ = move_to_direction(heading, target_dir, serial, imu, floor_sensor)

    if len(stack) <= 1:
        print("[HOME] Regressou a (0,0,0) com sucesso.")
    else:
        print("[HOME] Timeout — não chegou a (0,0,0).")

    return heading


def _check_victims(serial, victim_manager, pos: tuple, log: list):
    """
    Chama o VictimManager para detetar vítimas no tile atual.
    Usa múltiplos frames e votação internamente (via check_for_victims).
    Se já foi detetada uma vítima nesta posição, salta.
    """
    if victim_manager.was_detected_at(pos):
        return

    print(f"  [VIT] A capturar frames em {pos}...")
    result = victim_manager.check_for_victims(num_frames=3)

    if result is None:
        print(f"  [VIT] Nenhuma vítima em {pos}")
        return

    tipo   = result["type"]
    status = result["status"]
    kits   = result["kits"]
    conf   = result["confidence"]
    hits   = result["hits"]
    total  = result["total_frames"]

    if tipo == "letter":
        letra = result["letter"]
        print(f"  [VIT] Letra: {letra} ({status}) conf={conf:.3f} [{hits}/{total} frames]")
        serial.send(f"VICTIM LETTER {letra}")
    else:
        colors_str = ",".join(result.get("colors", []))
        print(f"  [VIT] Cognitive: {colors_str} sum={result.get('sum')} ({status}) conf={conf:.3f} [{hits}/{total} frames]")
        serial.send(f"VICTIM COGNITIVE {status}")

    # Sinaliza kit de resgate e aguarda depósito
    serial.send("VC")
    time.sleep(5)

    # Regista no manager e no log local
    victim_manager.log_detection(pos, result)
    log.append((pos, tipo, status, kits))


def _detect_victims(serial, camera, color_detector, letter_detector,
                    pos: tuple, log: list):
    """Legado — não usado. Mantido por compatibilidade."""
    pass


def _print_report(visited: set, blocked: set, blue_tiles: list, victims: list):
    print("\n" + "=" * 52)
    print("[FIM] EXPLORAÇÃO CONCLUÍDA")
    print(f"  Células visitadas : {len(visited)}")
    print(f"  Tiles bloqueados  : {len(blocked)}")
    print(f"  Tiles azuis       : {len(blue_tiles)}")
    print(f"  Vítimas           : {len(victims)}")
    for v in victims:
        pos, tipo, status, kits = v[0], v[1], v[2], v[3]
        kits_str = f" — {kits} kits" if kits else ""
        print(f"    {pos}: {tipo.upper()} → {status}{kits_str}")
    print("=" * 52)
