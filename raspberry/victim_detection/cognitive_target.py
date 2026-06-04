"""
cognitive_target.py — Deteção de cognitive targets (anéis concêntricos).

Regras 2026:
  - Círculo com 5cm de diâmetro, 5 anéis concêntricos
  - Anéis de dentro para fora: Ø 1cm, 2cm, 3cm, 4cm, 5cm
  - Cores possíveis: Preto(-2), Vermelho(-1), Amarelo(0), Verde(+1), Azul(+2)
  - Soma dos 5 anéis: 0=Unharmed, 1=Stable, 2=Harmed
  - Soma fora de {0,1,2} → FALSO ALVO (não identificar!)

Abordagem:
  1. Pré-processamento: blur + HSV
  2. Deteção de círculos: HoughCircles ou deteção de contorno circular
  3. Amostragem radial: 5 distâncias proporcionais do centro
  4. Classificação de cor em HSV
  5. Soma e validação

Testável no PC:
  python -m victim_detection.test_cognitive --webcam
  python -m victim_detection.test_cognitive --image foto.jpg
"""

import numpy as np
import cv2
import math


# ═══════════════════════════════════════════════════════════════════════════════
# MAPEAMENTO COR → VALOR
# ═══════════════════════════════════════════════════════════════════════════════

COLOR_VALUES = {
    "black":  -2,
    "red":    -1,
    "yellow":  0,
    "green":   1,
    "blue":    2,
}

# Status por soma
SUM_TO_STATUS = {
    0: ("unharmed", 0),
    1: ("stable",   1),
    2: ("harmed",   2),
}

# ═══════════════════════════════════════════════════════════════════════════════
# THRESHOLDS HSV (ajustáveis — calibrar no local da competição)
# ═══════════════════════════════════════════════════════════════════════════════
# Formato: (H_min, S_min, V_min, H_max, S_max, V_max)
# OpenCV usa H: 0-179, S: 0-255, V: 0-255

DEFAULT_HSV_RANGES = {
    "black":  {"v_max": 60},                        # Muito escuro
    "red":    {"h_ranges": [(0, 10), (170, 179)],    # Vermelho wraparound
               "s_min": 70, "v_min": 50},
    "yellow": {"h_min": 18, "h_max": 38,
               "s_min": 70, "v_min": 80},
    "green":  {"h_min": 36, "h_max": 90,
               "s_min": 40, "v_min": 40},
    "blue":   {"h_min": 90, "h_max": 135,
               "s_min": 50, "v_min": 40},
}


# ═══════════════════════════════════════════════════════════════════════════════
# CLASSIFICADOR DE COR
# ═══════════════════════════════════════════════════════════════════════════════

def classify_color_hsv(h: float, s: float, v: float,
                       hsv_ranges: dict = None) -> str:
    """
    Classifica uma cor HSV numa das 5 categorias.

    Args:
        h, s, v: valores HSV (H: 0-179, S: 0-255, V: 0-255)
        hsv_ranges: thresholds customizados (ou None para defaults)

    Returns:
        "black" | "red" | "yellow" | "green" | "blue"
    """
    if hsv_ranges is None:
        hsv_ranges = DEFAULT_HSV_RANGES

    # 1. Preto: valor muito baixo (independente de H e S)
    if v <= hsv_ranges["black"]["v_max"]:
        return "black"

    # 2. Vermelho: H perto de 0 ou perto de 179 (wraparound)
    red_cfg = hsv_ranges["red"]
    if s >= red_cfg["s_min"] and v >= red_cfg["v_min"]:
        for h_min, h_max in red_cfg["h_ranges"]:
            if h_min <= h <= h_max:
                return "red"

    # 3. Amarelo
    ycfg = hsv_ranges["yellow"]
    if ycfg["h_min"] <= h <= ycfg["h_max"] and s >= ycfg["s_min"] and v >= ycfg["v_min"]:
        return "yellow"

    # 4. Verde
    gcfg = hsv_ranges["green"]
    if gcfg["h_min"] <= h <= gcfg["h_max"] and s >= gcfg["s_min"] and v >= gcfg["v_min"]:
        return "green"

    # 5. Azul
    bcfg = hsv_ranges["blue"]
    if bcfg["h_min"] <= h <= bcfg["h_max"] and s >= bcfg["s_min"] and v >= bcfg["v_min"]:
        return "blue"

    # Fallback: se S muito baixo e V alto → branco (não é uma cor válida)
    # Se V baixo → preto-ish
    if v < 100:
        return "black"

    # Se nenhum match, retorna a cor mais próxima por distância H
    # (isto é um fallback robusto para iluminação não ideal)
    if s < 40:
        return "black"  # Dessaturado = provavelmente preto/branco mal iluminado

    return "yellow"  # Fallback seguro (valor 0, neutro)


def classify_color_region(hsv_img: np.ndarray, mask: np.ndarray) -> tuple:
    """
    Classifica a cor dominante numa região mascarada de uma imagem HSV.

    Usa votação por pixel: cada pixel é classificado individualmente e a cor
    com mais votos ganha. Muito mais robusto a contaminação de bordas do que
    usar a mediana do HSV.

    Args:
        hsv_img: imagem em HSV
        mask: máscara binária da região de interesse

    Returns:
        (cor_str, confiança)
        A confiança é a fração de pixels que votaram na cor vencedora.
    """
    pixels = hsv_img[mask > 0]
    
    # OTIMIZAÇÃO: Limitar o número de píxeis para evitar lentidão extrema no loop Python
    MAX_PIXELS = 150
    total_pixels = len(pixels)
    if total_pixels > MAX_PIXELS:
        step = total_pixels // MAX_PIXELS
        pixels = pixels[::step]
        # Garantir que não ultrapassamos muito o limite
        if len(pixels) > MAX_PIXELS:
            pixels = pixels[:MAX_PIXELS]

    if len(pixels) < 3:
        return "black", 0.0

    # Classifica cada pixel individualmente
    h = pixels[:, 0].astype(int)
    s = pixels[:, 1].astype(int)
    v = pixels[:, 2].astype(int)

    colors_list = []
    for idx in range(len(pixels)):
        colors_list.append(classify_color_hsv(h[idx], s[idx], v[idx]))

    # Contagem de votos
    votes: dict = {}
    for c in colors_list:
        votes[c] = votes.get(c, 0) + 1

    # Cor vencedora e confiança = fracção de votos
    winner = max(votes, key=votes.get)
    confidence = round(votes[winner] / len(pixels), 3)

    return winner, confidence


# ═══════════════════════════════════════════════════════════════════════════════
# DETETOR PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

class CognitiveTargetDetector:
    """
    Deteta cognitive targets (anéis concêntricos coloridos) em frames de câmara.
    """

    # Proporções radiais dos 5 anéis (relativas ao raio total)
    # Anel 1 (centro): 0 a 0.2R, Anel 2: 0.2R a 0.4R, etc.
    RING_RATIOS = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]

    def __init__(self, confidence: float = 0.5, hsv_ranges: dict = None):
        """
        Args:
            confidence: threshold mínimo de confiança média dos anéis
            hsv_ranges: thresholds HSV customizados (ou None para defaults)
        """
        self.confidence = confidence
        self.hsv_ranges = hsv_ranges or DEFAULT_HSV_RANGES
        print(f"[COGNITIVE] Detetor inicializado (confiança mín: {confidence})")

    def _find_circles(self, frame: np.ndarray) -> list:
        """
        Encontra círculos candidatos na imagem.

        Returns:
            Lista de (cx, cy, radius) ordenada por confiança
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        blurred = cv2.GaussianBlur(gray, (9, 9), 2)

        h, w = blurred.shape[:2]
        min_radius = max(10, int(min(h, w) * 0.03))
        max_radius = int(min(h, w) * 0.4)

        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=max(30, min_radius * 2),
            param1=80,
            param2=30,  # Reduzido de 40 para 30 para detetar alvos ligeiramente de lado (elipses)
            minRadius=min_radius,
            maxRadius=max_radius,
        )

        if circles is None:
            return []

        result = []
        for c in circles[0]:
            cx, cy, r = int(c[0]), int(c[1]), int(c[2])

            # Verifica que o círculo está dentro da imagem
            if cx - r < 0 or cy - r < 0 or cx + r >= w or cy + r >= h:
                continue

            result.append((cx, cy, r))

        # OTIMIZAÇÃO: O HoughCircles já retorna os círculos ordenados por votos (confiança).
        # Limitamos aos 3 melhores para não perder tempo com eventuais falsos círculos no fundo.
        return result[:3]

    def _analyze_rings(self, frame: np.ndarray, cx: int, cy: int, radius: int) -> tuple:
        """
        Analisa as 5 zonas concêntricas de um círculo detetado.

        Args:
            frame: imagem BGR original
            cx, cy: centro do círculo
            radius: raio do círculo exterior

        Returns:
            (rings_info, avg_confidence) onde rings_info é lista de dicts
        """
        h_img, w_img = frame.shape[:2]

        # OTIMIZAÇÃO: Recortar a área do alvo para não processar a imagem toda em HSV e Máscaras
        x1 = max(0, cx - radius)
        y1 = max(0, cy - radius)
        x2 = min(w_img, cx + radius)
        y2 = min(h_img, cy + radius)
        
        roi_bgr = frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        roi_h, roi_w = hsv.shape[:2]
        
        # Centro relativo ao ROI
        rel_cx = cx - x1
        rel_cy = cy - y1

        rings = []
        confidences = []

        for i in range(5):
            # Limites radiais deste anel
            r_inner = int(radius * self.RING_RATIOS[i])
            r_outer = int(radius * self.RING_RATIOS[i + 1])

            # Cria máscara anelar restrita ao ROI
            mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
            cv2.circle(mask, (rel_cx, rel_cy), r_outer, 255, -1)
            if r_inner > 0:
                cv2.circle(mask, (rel_cx, rel_cy), r_inner, 0, -1)

            # Classifica cor
            color, conf = classify_color_region(hsv, mask)

            rings.append({
                "ring": i + 1,
                "color": color,
                "value": COLOR_VALUES[color],
                "confidence": conf,
                "r_inner": r_inner,
                "r_outer": r_outer,
            })
            confidences.append(conf)

        avg_conf = np.mean(confidences) if confidences else 0.0
        return rings, avg_conf

    def detect(self, frame: np.ndarray) -> dict | None:
        """
        Deteta um cognitive target no frame.

        Args:
            frame: numpy array BGR (h, w, 3)

        Returns:
            dict com {"rings", "colors", "values", "sum", "status", "kits",
                      "confidence", "center", "radius"}
            ou None se nenhum target válido detetado.
        """
        circles = self._find_circles(frame)

        best_result = None
        best_conf = 0.0

        for (cx, cy, r) in circles:
            rings, avg_conf = self._analyze_rings(frame, cx, cy, r)

            if avg_conf < self.confidence:
                continue

            # Calcula soma
            values = [ring["value"] for ring in rings]
            colors = [ring["color"] for ring in rings]
            total = sum(values)

            # Valida: soma tem de ser 0, 1 ou 2 para ser vítima real
            if total not in SUM_TO_STATUS:
                # FALSO ALVO — não identificar!
                continue

            status, kits = SUM_TO_STATUS[total]

            if avg_conf > best_conf:
                best_conf = avg_conf
                best_result = {
                    "rings": rings,
                    "colors": colors,
                    "values": values,
                    "sum": total,
                    "status": status,
                    "kits": kits,
                    "confidence": round(avg_conf, 3),
                    "center": (cx, cy),
                    "radius": r,
                }

        return best_result

    def detect_all(self, frame: np.ndarray) -> list:
        """
        Deteta TODOS os cognitive targets (incluindo falsos alvos).
        Útil para debug — mostra o que seria detetado e rejeitado.

        Returns:
            Lista de dicts, cada um com campo extra "valid" (bool)
        """
        circles = self._find_circles(frame)
        results = []

        for (cx, cy, r) in circles:
            rings, avg_conf = self._analyze_rings(frame, cx, cy, r)
            values = [ring["value"] for ring in rings]
            colors = [ring["color"] for ring in rings]
            total = sum(values)

            valid = total in SUM_TO_STATUS
            if valid:
                status, kits = SUM_TO_STATUS[total]
            else:
                status, kits = "FALSE TARGET", 0

            results.append({
                "rings": rings,
                "colors": colors,
                "values": values,
                "sum": total,
                "status": status,
                "kits": kits,
                "valid": valid,
                "confidence": round(avg_conf, 3),
                "center": (cx, cy),
                "radius": r,
            })

        return results

    def detect_debug(self, frame: np.ndarray) -> tuple:
        """
        Deteta todos os targets e retorna frame anotado.

        Returns:
            (melhor_resultado_válido ou None, frame_anotado)
        """
        all_targets = self.detect_all(frame)
        debug_frame = frame.copy()

        best_valid = None

        for target in all_targets:
            cx, cy = target["center"]
            r = target["radius"]
            valid = target["valid"]

            # Desenha anéis
            for ring in target["rings"]:
                r_outer = ring["r_outer"]
                color_name = ring["color"]
                # Mapeia nome de cor para BGR para visualização
                color_bgr = _color_name_to_bgr(color_name)
                cv2.circle(debug_frame, (cx, cy), r_outer, color_bgr, 2)

            # Contorno exterior
            border_color = (0, 255, 0) if valid else (0, 0, 255)
            cv2.circle(debug_frame, (cx, cy), r, border_color, 3)

            # Label
            label = f"sum={target['sum']} → {target['status']}"
            if not valid:
                label = f"FALSE (sum={target['sum']})"
            cv2.putText(debug_frame, label, (cx - r, cy - r - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, border_color, 2)

            # Cores dos anéis como texto
            colors_str = ",".join(target["colors"])
            cv2.putText(debug_frame, colors_str, (cx - r, cy + r + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            if valid and (best_valid is None or target["confidence"] > best_valid["confidence"]):
                best_valid = target

        # Header
        if best_valid:
            text = f"TARGET: {best_valid['status']} (sum={best_valid['sum']}, kits={best_valid['kits']})"
            cv2.putText(debug_frame, text, (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        else:
            cv2.putText(debug_frame, "No valid target", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (128, 128, 128), 1)

        return best_valid, debug_frame


# ═══════════════════════════════════════════════════════════════════════════════
# GERAÇÃO DE TARGETS SINTÉTICOS (para testes)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_test_target(colors: list, size: int = 300, bg_color=(200, 200, 200)) -> np.ndarray:
    """
    Gera uma imagem sintética de um cognitive target.

    Args:
        colors: lista de 5 nomes de cor (de dentro para fora)
        size: tamanho do canvas
        bg_color: cor de fundo BGR

    Returns:
        numpy array BGR
    """
    img = np.full((size, size, 3), bg_color, dtype=np.uint8)
    cx, cy = size // 2, size // 2
    max_r = int(size * 0.4)

    # Desenha de fora para dentro
    for i in range(4, -1, -1):
        r = int(max_r * (i + 1) / 5)
        bgr = _color_name_to_bgr(colors[i])
        cv2.circle(img, (cx, cy), r, bgr, -1)

    return img


def _color_name_to_bgr(name: str) -> tuple:
    """Converte nome de cor para BGR."""
    mapping = {
        "black":  (0, 0, 0),
        "red":    (0, 0, 220),
        "yellow": (0, 220, 220),
        "green":  (0, 180, 0),
        "blue":   (220, 100, 0),
    }
    return mapping.get(name, (128, 128, 128))
