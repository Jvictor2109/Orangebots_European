import os
import cv2
import time
from victim_detection.camera import Camera
from victim_detection.cognitive_target import CognitiveTargetDetector
from victim_detection.letter_detector import LetterDetector
from victim_detection.victim_manager import VictimManager

def main():
    print("Inicializando a câmera (picamera)...")
    try:
        camera = Camera(source="picamera", resolution=(640, 480))
    except Exception as e:
        print(f"Erro ao abrir câmera: {e}")
        return

    print("Inicializando detectores...")
    cognitive_det = CognitiveTargetDetector(confidence=0.45)
    
    templates_dir = os.path.join(
        os.path.dirname(__file__), "victim_detection", "templates"
    )
    letter_det = LetterDetector(templates_dir=templates_dir)

    manager = VictimManager(
        camera=camera,
        letter_detector=letter_det,
        cognitive_detector=cognitive_det,
    )

    print("Capturando frame único para salvar imagem original...")
    # Deixa a câmara ajustar o brilho (exposure) antes de capturar
    time.sleep(1)
    
    try:
        frame = camera.capture()
        cv2.imwrite("camera_test_original.jpg", frame)
        print("Imagem salva como 'camera_test_original.jpg' na pasta atual.")
    except Exception as e:
        print(f"Erro ao capturar ou salvar frame: {e}")

    print("Procurando vítimas na imagem (análise)...")
    result = manager.check_for_victims(num_frames=3)
    
    if result:
        print("\n=== VÍTIMA DETECTADA ===")
        print(f"Tipo: {result.get('type')}")
        print(f"Status: {result.get('status')}")
        print(f"Confiança: {result.get('confidence')}")
        print(f"Kits a deixar: {result.get('kits')}")
        print(f"Detalhes brutos: {result.get('details')}")
        print("========================")
    else:
        print("\n=== NENHUMA VÍTIMA DETECTADA ===")

    camera.close()
    print("\nTeste concluído.")

if __name__ == "__main__":
    main()
