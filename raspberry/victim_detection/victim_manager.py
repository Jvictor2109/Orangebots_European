"""
victim_manager.py — Coordenador de deteção de vítimas.

Combina o LetterDetector e o CognitiveTargetDetector num pipeline único:
  1. Captura frame da câmara
  2. Executa ambos os detetores
  3. Retorna o melhor resultado (se houver)

Uso no DFS:
  manager = VictimManager(camera, letter_det, target_det)
  result = manager.check_for_victims()
  if result:
      print(f"Vítima: {result['type']} — {result['status']}")
"""

import time
import numpy as np


class VictimManager:
    """
    Gere a deteção de vítimas combinando múltiplos detetores.
    """

    def __init__(self, camera, letter_detector=None, cognitive_detector=None):
        """
        Args:
            camera: instância de Camera (ou qualquer objeto com .capture() → ndarray)
            letter_detector: instância de LetterDetector (ou None para desativar)
            cognitive_detector: instância de CognitiveTargetDetector (ou None)
        """
        self.camera = camera
        self.letter_det = letter_detector
        self.cognitive_det = cognitive_detector

        # Historial de deteções (evita duplicados na mesma posição)
        self.detections = []

        active = []
        if letter_detector:
            active.append("letras")
        if cognitive_detector:
            active.append("cognitive")
        print(f"[VICTIM] Manager inicializado — detetores ativos: {', '.join(active) or 'nenhum'}")

    def check_for_victims(self, num_frames: int = 3) -> dict | None:
        """
        Captura múltiplos frames e tenta detetar vítimas.
        Usar múltiplos frames aumenta a robustez (reduz falsos positivos/negativos).

        Args:
            num_frames: número de frames a capturar e analisar

        Returns:
            dict com resultado da deteção ou None.
            Campos comuns: {"type", "status", "kits", "confidence", "details"}
        """
        if self.camera is None:
            return None

        letter_hits = []
        cognitive_hits = []

        for i in range(num_frames):
            try:
                frame = self.camera.capture()
            except Exception as e:
                print(f"  [VICTIM] Erro ao capturar frame {i+1}: {e}")
                continue

            # Tenta detetar letra
            if self.letter_det is not None:
                try:
                    result = self.letter_det.detect(frame)
                    if result is not None:
                        letter_hits.append(result)
                except Exception as e:
                    print(f"  [VICTIM] Erro no detetor de letras: {e}")

            # Tenta detetar cognitive target
            if self.cognitive_det is not None:
                try:
                    result = self.cognitive_det.detect(frame)
                    if result is not None:
                        cognitive_hits.append(result)
                except Exception as e:
                    print(f"  [VICTIM] Erro no detetor de cognitive: {e}")

            # Pequena pausa entre frames para variar ligeiramente a captura
            if i < num_frames - 1:
                time.sleep(0.05)

        # ── Decisão ──────────────────────────────────────────────────────────

        # Requer deteção consistente: pelo menos 2 em N frames
        min_hits = max(1, num_frames // 2)

        best = None

        # Prioridade: letra > cognitive (letras são mais determinísticas)
        if len(letter_hits) >= min_hits:
            # Usa a deteção de maior confiança
            best_hit = max(letter_hits, key=lambda r: r["confidence"])
            best = {
                "type": "letter",
                "letter": best_hit["letter"],
                "status": best_hit["status"],
                "kits": best_hit["kits"],
                "confidence": best_hit["confidence"],
                "hits": len(letter_hits),
                "total_frames": num_frames,
                "details": best_hit,
            }

        elif len(cognitive_hits) >= min_hits:
            best_hit = max(cognitive_hits, key=lambda r: r["confidence"])
            best = {
                "type": "cognitive",
                "status": best_hit["status"],
                "kits": best_hit["kits"],
                "sum": best_hit["sum"],
                "colors": best_hit["colors"],
                "confidence": best_hit["confidence"],
                "hits": len(cognitive_hits),
                "total_frames": num_frames,
                "details": best_hit,
            }

        return best

    def log_detection(self, position: tuple, result: dict):
        """
        Regista uma deteção no historial.

        Args:
            position: (x, y) posição no mapa
            result: resultado de check_for_victims()
        """
        entry = {
            "position": position,
            "time": time.time(),
            **result,
        }
        self.detections.append(entry)

    def was_detected_at(self, position: tuple) -> bool:
        """Verifica se já detetámos uma vítima nesta posição."""
        return any(d["position"] == position for d in self.detections)

    def get_detection_summary(self) -> str:
        """Retorna resumo textual de todas as deteções."""
        if not self.detections:
            return "Nenhuma vítima detetada."

        lines = [f"Total: {len(self.detections)} vítimas"]
        for d in self.detections:
            pos = d["position"]
            tipo = d["type"]
            status = d["status"]
            conf = d["confidence"]
            if tipo == "letter":
                lines.append(f"  {pos}: {d.get('letter', '?')} ({status}) conf={conf}")
            else:
                lines.append(f"  {pos}: cognitive sum={d.get('sum', '?')} ({status}) conf={conf}")

        return "\n".join(lines)

    @staticmethod
    def get_status_info(result: dict) -> tuple:
        """
        Extrai (nome_do_status, numero_de_kits) de um resultado.

        Returns:
            (str, int) ex: ("harmed", 2)
        """
        return result.get("status", "unknown"), result.get("kits", 0)
