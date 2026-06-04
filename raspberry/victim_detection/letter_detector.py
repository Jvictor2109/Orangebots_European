"""
letter_detector.py — Deteção de letras gregas Φ, Ψ, Ω em paredes.

Regras 2026:
  - Letras pretas, sans-serif (Arial), 4cm de altura
  - Podem estar rotadas (0°, 90°, 180°, 270°)
  - Sobre parede branca/clara

Abordagem:
  1. Pré-processamento: grayscale → threshold adaptativo → limpeza morfológica
  2. Deteção de contornos: filtra candidatos por área e aspect ratio
  3. Template matching: multi-escala, multi-rotação (0°, 90°, 180°, 270°)
  4. Threshold de confiança para evitar falsos positivos (penalidade −5pts)

Testável no PC:
  python -m victim_detection.test_letter --webcam
  python -m victim_detection.test_letter --image foto.jpg
"""

import os
import math
import numpy as np
import cv2


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════════════════════

LETTERS = {
    "Φ": {"status": "harmed",   "kits": 2, "file": "phi.png"},
    "Ψ": {"status": "stable",   "kits": 1, "file": "psi.png"},
    "Ω": {"status": "unharmed", "kits": 0, "file": "omega.png"},
}

# Rotações a testar (graus)
ROTATIONS = [0, 90, 180, 270]

# Escalas relativas para template matching multi-escala
SCALES = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4, 1.6]

# Área mínima e máxima de contornos candidatos (pixels²)
# Para 640x480 a ~15cm de distância, a letra de 4cm ocupa ~80-200px de lado
MIN_CONTOUR_AREA = 400    # ~20x20 px
MAX_CONTOUR_AREA = 1000000 # Permitir deteção mesmo quando muito perto da câmara

# Threshold de confiança para template matching
DEFAULT_CONFIDENCE = 0.55


# ═══════════════════════════════════════════════════════════════════════════════
# GERAÇÃO DE TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════

def generate_templates(output_dir: str, size: int = 120):
    """
    Gera imagens de template para Φ, Ψ, Ω usando Pillow (suporta Unicode).

    Args:
        output_dir: directório onde guardar os PNGs
        size: tamanho do canvas (quadrado)
    """
    from PIL import Image, ImageDraw, ImageFont

    os.makedirs(output_dir, exist_ok=True)

    # Tenta usar uma fonte sans-serif; fallback para default
    font = None
    font_size = int(size * 0.75)

    # Lista de fontes sans-serif comuns
    font_candidates = [
        "arial.ttf", "Arial.ttf",
        "DejaVuSans.ttf",
        "LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]

    for font_path in font_candidates:
        try:
            font = ImageFont.truetype(font_path, font_size)
            break
        except (OSError, IOError):
            continue

    if font is None:
        print("[TEMPLATE] Aviso: nenhuma fonte TrueType encontrada, a usar fonte default")
        font = ImageFont.load_default()

    for letter, info in LETTERS.items():
        # Canvas branco
        img = Image.new("L", (size, size), 255)
        draw = ImageDraw.Draw(img)

        # Calcula posição para centrar a letra
        bbox = draw.textbbox((0, 0), letter, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (size - text_w) // 2 - bbox[0]
        y = (size - text_h) // 2 - bbox[1]

        # Desenha letra preta em fundo branco
        draw.text((x, y), letter, fill=0, font=font)

        # Converte para numpy, aplica threshold para obter binário limpo
        arr = np.array(img)
        _, binary = cv2.threshold(arr, 128, 255, cv2.THRESH_BINARY_INV)

        # Recorta à bounding box do conteúdo com margem
        coords = cv2.findNonZero(binary)
        if coords is not None:
            rx, ry, rw, rh = cv2.boundingRect(coords)
            margin = max(4, int(min(rw, rh) * 0.1))
            rx = max(0, rx - margin)
            ry = max(0, ry - margin)
            rw = min(size - rx, rw + 2 * margin)
            rh = min(size - ry, rh + 2 * margin)
            binary = binary[ry:ry+rh, rx:rx+rw]

        # Inverte de volta: letra preta (0) em fundo branco (255) — como na realidade
        template = cv2.bitwise_not(binary)

        out_path = os.path.join(output_dir, info["file"])
        cv2.imwrite(out_path, template)
        name = info["file"].replace(".png", "").upper()
        print(f"[TEMPLATE] {name} -> {out_path} ({template.shape[1]}x{template.shape[0]})")


# ═══════════════════════════════════════════════════════════════════════════════
# DETETOR
# ═══════════════════════════════════════════════════════════════════════════════

class LetterDetector:
    """
    Deteta letras gregas Φ, Ψ, Ω em frames de câmara.
    """

    def __init__(self, templates_dir: str = None, confidence: float = DEFAULT_CONFIDENCE):
        """
        Args:
            templates_dir: directório com phi.png, psi.png, omega.png.
                          Se None, usa o subdiretório 'templates/' relativo a este ficheiro.
            confidence: threshold mínimo de confiança (0.0 a 1.0)
        """
        self.confidence = confidence

        if templates_dir is None:
            templates_dir = os.path.join(os.path.dirname(__file__), "templates")

        # Gera templates se não existirem
        if not os.path.isdir(templates_dir):
            print(f"[LETTER] Templates não encontrados em {templates_dir}, a gerar...")
            generate_templates(templates_dir)

        # Carrega templates e pré-computa rotações
        self.templates = {}  # {"Φ": [array_0, array_90, array_180, array_270], ...}

        for letter, info in LETTERS.items():
            path = os.path.join(templates_dir, info["file"])
            if not os.path.isfile(path):
                print(f"[LETTER] Template em falta: {path}, a gerar...")
                generate_templates(templates_dir)

            tmpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if tmpl is None:
                raise FileNotFoundError(f"Falha ao carregar template: {path}")

            # Pré-computa rotações
            rotated = []
            for angle in ROTATIONS:
                if angle == 0:
                    rotated.append(tmpl)
                else:
                    rotated.append(self._rotate_template(tmpl, angle))

            self.templates[letter] = rotated

        print(f"[LETTER] Detetor inicializado ({len(self.templates)} letras, "
              f"{len(ROTATIONS)} rotações, {len(SCALES)} escalas)")

    @staticmethod
    def _rotate_template(img: np.ndarray, angle: float) -> np.ndarray:
        """Roda um template mantendo todo o conteúdo visível."""
        h, w = img.shape[:2]
        center = (w / 2, h / 2)

        M = cv2.getRotationMatrix2D(center, -angle, 1.0)

        # Calcula novo tamanho para acomodar a rotação
        cos = abs(M[0, 0])
        sin = abs(M[0, 1])
        new_w = int(h * sin + w * cos)
        new_h = int(h * cos + w * sin)

        M[0, 2] += (new_w - w) / 2
        M[1, 2] += (new_h - h) / 2

        return cv2.warpAffine(img, M, (new_w, new_h),
                              borderMode=cv2.BORDER_CONSTANT,
                              borderValue=255)

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """
        Converte frame para binário otimizado para deteção de letras pretas.
        """
        # Grayscale
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame.copy()

        # Reduz ruído
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        # Threshold adaptativo — lida com iluminação variável
        # blockSize grande para evitar que traços grossos de letras grandes fiquem ocos
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=101,
            C=10,
        )

        # Limpeza morfológica
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

        return binary

    def _find_candidates(self, binary: np.ndarray) -> list:
        """
        Encontra regiões candidatas que podem conter uma letra.

        Returns:
            Lista de (x, y, w, h) bounding boxes
        """
        # Inverte para findContours (letras pretas → brancas)
        inverted = cv2.bitwise_not(binary)

        contours, _ = cv2.findContours(inverted, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < MIN_CONTOUR_AREA or area > MAX_CONTOUR_AREA:
                continue

            x, y, w, h = cv2.boundingRect(cnt)

            # Aspect ratio: letras não devem ser excessivamente alongadas
            aspect = max(w, h) / (min(w, h) + 1e-6)
            if aspect > 3.0:
                continue

            # Adiciona margem
            margin = max(5, int(min(w, h) * 0.15))
            x = max(0, x - margin)
            y = max(0, y - margin)
            w = min(binary.shape[1] - x, w + 2 * margin)
            h = min(binary.shape[0] - y, h + 2 * margin)

            candidates.append((x, y, w, h))

        # OTIMIZAÇÃO: Testar apenas os 5 maiores candidatos para não perder tempo com ruído
        candidates.sort(key=lambda c: c[2] * c[3], reverse=True)
        return candidates[:5]

    def _match_template(self, roi: np.ndarray) -> tuple:
        """
        Faz template matching de um ROI contra todos os templates.

        Returns:
            (melhor_letra, melhor_confiança, melhor_rotação) ou (None, 0.0, 0)
        """
        best_letter = None
        best_conf = 0.0
        best_rot = 0

        roi_h, roi_w = roi.shape[:2]

        # OTIMIZAÇÃO CRÍTICA: Se o ROI for gigante (ex: 400x400), o matchTemplate é lentíssimo.
        # Reduzimos o ROI para no máximo 80px, mantendo a proporção.
        MAX_ROI_SIZE = 80
        if max(roi_w, roi_h) > MAX_ROI_SIZE:
            scale_down = MAX_ROI_SIZE / max(roi_w, roi_h)
            roi_w = int(roi_w * scale_down)
            roi_h = int(roi_h * scale_down)
            roi = cv2.resize(roi, (roi_w, roi_h), interpolation=cv2.INTER_AREA)

        for letter, rotated_templates in self.templates.items():
            for rot_idx, tmpl in enumerate(rotated_templates):
                tmpl_h, tmpl_w = tmpl.shape[:2]

                # Calcular escalas dinâmicas baseadas no tamanho do ROI
                # O ROI tem ~15% de margem, o template tem ~10% de margem.
                base_scale = min(roi_w / (tmpl_w + 1e-5), roi_h / (tmpl_h + 1e-5))
                # OTIMIZAÇÃO: 3 escalas são suficientes em vez de 5, acelera 40%
                dynamic_scales = [base_scale * 0.7, base_scale * 0.85, base_scale * 0.95]

                for scale in dynamic_scales:
                    new_w = int(tmpl_w * scale)
                    new_h = int(tmpl_h * scale)

                    # Template tem de caber no ROI
                    if new_w >= roi_w or new_h >= roi_h:
                        continue
                    if new_w < 10 or new_h < 10:
                        continue

                    scaled = cv2.resize(tmpl, (new_w, new_h), interpolation=cv2.INTER_AREA)

                    result = cv2.matchTemplate(roi, scaled, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(result)

                    if max_val > best_conf:
                        best_conf = max_val
                        best_letter = letter
                        best_rot = ROTATIONS[rot_idx]

        return best_letter, best_conf, best_rot

    def detect(self, frame: np.ndarray) -> dict | None:
        """
        Deteta uma letra grega no frame.

        Args:
            frame: numpy array BGR (h, w, 3) ou grayscale (h, w)

        Returns:
            dict com {"letter", "status", "kits", "confidence", "rotation", "bbox"}
            ou None se nenhuma letra detetada com confiança suficiente.
        """
        binary = self._preprocess(frame)
        candidates = self._find_candidates(binary)

        best_result = None
        best_conf = 0.0

        for (x, y, w, h) in candidates:
            roi = binary[y:y+h, x:x+w]
            letter, conf, rot = self._match_template(roi)

            if letter is not None and conf > best_conf and conf >= self.confidence:
                best_conf = conf
                info = LETTERS[letter]
                best_result = {
                    "letter": letter,
                    "status": info["status"],
                    "kits": info["kits"],
                    "confidence": round(conf, 3),
                    "rotation": rot,
                    "bbox": (x, y, w, h),
                }

        return best_result

    def detect_debug(self, frame: np.ndarray) -> tuple:
        """
        Mesmo que detect() mas retorna frame anotado para debug/visualização.

        Returns:
            (resultado, frame_anotado)
        """
        binary = self._preprocess(frame)
        candidates = self._find_candidates(binary)

        debug_frame = frame.copy() if len(frame.shape) == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        best_result = None
        best_conf = 0.0

        for (x, y, w, h) in candidates:
            roi = binary[y:y+h, x:x+w]
            letter, conf, rot = self._match_template(roi)

            # Desenha todos os candidatos
            color = (0, 255, 255)  # Amarelo para candidatos
            if letter is not None and conf >= self.confidence:
                color = (0, 255, 0)  # Verde para deteções válidas

                if conf > best_conf:
                    best_conf = conf
                    info = LETTERS[letter]
                    best_result = {
                        "letter": letter,
                        "status": info["status"],
                        "kits": info["kits"],
                        "confidence": round(conf, 3),
                        "rotation": rot,
                        "bbox": (x, y, w, h),
                    }

            cv2.rectangle(debug_frame, (x, y), (x + w, y + h), color, 2)
            if letter:
                label = f"{letter} {conf:.2f} r{rot}"
                cv2.putText(debug_frame, label, (x, y - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        # Rótulo do resultado final
        if best_result:
            text = f"DETECTED: {best_result['letter']} ({best_result['status']}) conf={best_result['confidence']}"
            cv2.putText(debug_frame, text, (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        else:
            cv2.putText(debug_frame, "No letter detected", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (128, 128, 128), 1)

        return best_result, debug_frame
