"""
test_letter.py — Teste independente do detetor de letras gregas.

Uso:
  python -m victim_detection.test_letter --webcam         # Webcam ao vivo
  python -m victim_detection.test_letter --image foto.jpg  # Imagem estática
  python -m victim_detection.test_letter --generate        # Gera templates e testa com eles

Teclas (modo webcam/imagem):
  q / ESC : sair
  s       : salvar frame atual
  d       : mostrar/esconder debug info
"""

import argparse
import os
import sys
import numpy as np
import cv2

# Adiciona o directório pai ao path para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from victim_detection.letter_detector import LetterDetector, generate_templates, LETTERS


def test_with_webcam(detector: LetterDetector):
    """Teste ao vivo com webcam."""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERRO: Não foi possível abrir a webcam")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print("\n=== TESTE DE LETRAS (WEBCAM) ===")
    print("Aponta a câmara para uma letra Φ, Ψ ou Ω")
    print("Teclas: q=sair, s=salvar frame")
    print("================================\n")

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        result, debug = detector.detect_debug(frame)

        if result:
            status = result["status"]
            conf = result["confidence"]
            letter = result["letter"]
            print(f"[{frame_count:4d}] Detetado: {letter} ({status}) — confiança: {conf:.3f}")

        cv2.imshow("Letter Detector", debug)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):
            break
        elif key == ord('s'):
            path = f"letter_capture_{frame_count:04d}.png"
            cv2.imwrite(path, frame)
            print(f"  Salvo: {path}")

        frame_count += 1

    cap.release()
    cv2.destroyAllWindows()


def test_with_image(detector: LetterDetector, image_path: str):
    """Teste com imagem estática."""
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"ERRO: Não foi possível carregar: {image_path}")
        return

    print(f"\n=== TESTE DE LETRAS (IMAGEM: {image_path}) ===")

    result, debug = detector.detect_debug(frame)

    if result:
        print(f"Resultado: {result['letter']} ({result['status']})")
        print(f"  Confiança: {result['confidence']}")
        print(f"  Rotação:   {result['rotation']}°")
        print(f"  BBox:      {result['bbox']}")
    else:
        print("Nenhuma letra detetada.")

    cv2.imshow("Letter Detector", debug)
    print("\nPrime qualquer tecla para fechar...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def test_with_synthetic(detector: LetterDetector):
    """Testa com imagens sintéticas geradas internamente."""
    from PIL import Image, ImageDraw, ImageFont

    print("\n=== TESTE SINTÉTICO DE LETRAS ===\n")

    # Tenta carregar fonte
    font = None
    for fp in ["arial.ttf", "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        try:
            font = ImageFont.truetype(fp, 80)
            break
        except (OSError, IOError):
            continue
    if font is None:
        font = ImageFont.load_default()

    results = []
    for letter in ["Φ", "Ψ", "Ω"]:
        for angle in [0, 90, 180, 270]:
            # Gera imagem sintética: letra preta sobre fundo branco
            img = Image.new("RGB", (300, 300), (230, 230, 230))
            draw = ImageDraw.Draw(img)

            bbox = draw.textbbox((0, 0), letter, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            x = (300 - tw) // 2 - bbox[0]
            y = (300 - th) // 2 - bbox[1]

            draw.text((x, y), letter, fill=(10, 10, 10), font=font)

            # Roda
            if angle != 0:
                img = img.rotate(-angle, expand=False, fillcolor=(230, 230, 230))

            # Converte para OpenCV
            frame = np.array(img)
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            # Deteta
            result = detector.detect(frame)
            status = "✓" if (result and result["letter"] == letter) else "✗"
            conf = result["confidence"] if result else 0.0
            detected = result["letter"] if result else "—"

            results.append((letter, angle, detected, conf, status))
            print(f"  {letter} rot={angle:3d}° → {detected} conf={conf:.3f} {status}")

    # Resumo
    total = len(results)
    correct = sum(1 for r in results if r[4] == "✓")
    print(f"\nResultado: {correct}/{total} corretos ({correct/total*100:.0f}%)")

    return correct, total


def main():
    parser = argparse.ArgumentParser(description="Teste do detetor de letras gregas")
    parser.add_argument("--webcam", action="store_true", help="Usar webcam")
    parser.add_argument("--image", type=str, help="Caminho para imagem")
    parser.add_argument("--generate", action="store_true",
                        help="Gerar templates e testar com imagens sintéticas")
    parser.add_argument("--confidence", type=float, default=0.55,
                        help="Threshold de confiança (default: 0.55)")
    parser.add_argument("--templates-dir", type=str, default=None,
                        help="Directório dos templates")
    args = parser.parse_args()

    # Garante que templates existem
    templates_dir = args.templates_dir or os.path.join(os.path.dirname(__file__), "templates")
    if not os.path.isdir(templates_dir) or args.generate:
        print("A gerar templates...")
        generate_templates(templates_dir)

    detector = LetterDetector(templates_dir=templates_dir, confidence=args.confidence)

    if args.generate:
        test_with_synthetic(detector)
    elif args.image:
        test_with_image(detector, args.image)
    elif args.webcam:
        test_with_webcam(detector)
    else:
        # Default: gera e testa sinteticamente
        test_with_synthetic(detector)


if __name__ == "__main__":
    main()
