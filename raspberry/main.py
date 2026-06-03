"""
main.py — Entry point do robot maze rescue.

Uso:
  python main.py --simulate --no-camera          # desenvolvimento em PC
  python main.py --port /dev/ttyUSB0             # robot real com câmara (picamera)
  python main.py --port /dev/ttyUSB0 --webcam    # robot real com webcam USB
  python main.py --port /dev/ttyUSB0 --no-camera # sem câmara
  python main.py --port /dev/ttyUSB0 --no-floor  # sem sensor de chão TCS
"""

import argparse
import sys
import time

from config import *
from serial_comm import SerialComm
from tcs3200 import create_floor_sensor
from imu import IMU
from dfs import explorar_labirinto
from victim_detection.camera import Camera
from victim_detection.cognitive_target import CognitiveTargetDetector
from victim_detection.letter_detector import LetterDetector
from victim_detection.victim_manager import VictimManager


def main():
    parser = argparse.ArgumentParser(description="Robot Maze Rescue")
    parser.add_argument("--simulate",  action="store_true",
                        help="Modo simulação — responde pelo terminal")
    parser.add_argument("--port",      type=str, default=None,
                        help="Porta serial (ex: /dev/ttyUSB0, COM3)")
    parser.add_argument("--baudrate",  type=int, default=115200)
    parser.add_argument("--no-camera", action="store_true",
                        help="Desativa câmara")
    parser.add_argument("--webcam",    action="store_true",
                        help="Usa webcam USB em vez de picamera (para testes em PC)")
    parser.add_argument("--no-floor",  action="store_true",
                        help="Desativa sensor de chão TCS")
    args = parser.parse_args()

    if not args.simulate and not args.port:
        print("ERRO: Especifica --port ou usa --simulate")
        print("  Exemplos:")
        print("    python main.py --simulate --no-camera")
        print("    python main.py --port /dev/ttyUSB0")
        sys.exit(1)

    # ── Serial ────────────────────────────────────────────────────────────────
    serial = SerialComm(
        port=args.port,
        baudrate=args.baudrate,
        simulate=args.simulate,
    )

    # Para motores imediatamente — segurança se o script foi reiniciado com motores a andar
    serial.send("MC 0 0 0 0")
    time.sleep(3)

    if not serial.ping():
        print("[FATAL] Sem comunicação com ESP32.")
        serial.close()
        sys.exit(1)

    # ── IMU ───────────────────────────────────────────────────────────────────
    imu = IMU(mag_offset=MAG_OFFSET, mag_scale=MAG_SCALE)

    # ── Sensor de chão ────────────────────────────────────────────────────────
    # Desativado em simulação (sem hardware) e quando --no-floor é pedido
    floor = create_floor_sensor(enabled=not args.no_floor and not args.simulate)

    # ── Câmara + detetores ────────────────────────────────────────────────────
    camera = None
    victim_manager = None
    use_camera = not args.no_camera

    if use_camera:
        try:
            cam_source = "webcam" if args.webcam else "picamera"
            camera = Camera(source=cam_source, resolution=(640, 480))

            cognitive_det = CognitiveTargetDetector(confidence=0.45)

            # Templates de letras gerados automaticamente se não existirem
            import os
            templates_dir = os.path.join(
                os.path.dirname(__file__), "victim_detection", "templates"
            )
            letter_det = LetterDetector(templates_dir=templates_dir)

            victim_manager = VictimManager(
                camera=camera,
                letter_detector=letter_det,
                cognitive_detector=cognitive_det,
            )
            print("[CAM] Câmara e detetores inicializados.")
        except ImportError as e:
            print(f"[CAM] Módulo em falta ({e}) — câmara desativada.")
            use_camera = False
        except Exception as e:
            print(f"[CAM] Falha ({e}) — câmara desativada.")
            use_camera = False

    # ── Timer de missão ───────────────────────────────────────────────────────
    # Inicia o clock DEPOIS do setup, para não gastar tempo de competição em inicialização.
    mission_deadline = time.time() + MISSION_TIMEOUT_S
    print(f"\n[MISSÃO] Timer: {MISSION_TIMEOUT_S}s ({MISSION_TIMEOUT_S // 60}m{MISSION_TIMEOUT_S % 60}s)")
    print(f"[MISSÃO] Regresso automático a (0,0) após {MISSION_TIMEOUT_S}s\n")

    # ── Exploração ────────────────────────────────────────────────────────────
    try:
        explorar_labirinto(
            serial, imu, floor,
            victim_manager,
            use_camera, mission_deadline,
        )
    except KeyboardInterrupt:
        print("\n\n[!] Interrompido pelo utilizador (Ctrl+C)")
    except Exception as e:
        print(f"\n[CRASH] Exceção não tratada: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Garante paragem dos motores SEMPRE, mesmo em crash
        serial.send("MC 0 0 0 0")
        serial.close()
        floor.cleanup()
        if camera:
            camera.close()
            print("[CAM] Câmara parada.")


if __name__ == "__main__":
    main()
