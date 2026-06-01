"""
camera.py — Wrapper de câmara com backends múltiplos.

Backends:
  - "picamera"  : Raspberry Pi Camera Module 3 via picamera2
  - "webcam"    : Webcam USB via OpenCV (para testes em PC)
  - "/path.jpg" : Imagem estática de ficheiro (para testes unitários)

Uso:
  cam = Camera(source="webcam")          # PC com webcam
  cam = Camera(source="picamera")        # Raspberry Pi
  cam = Camera(source="test_image.jpg")  # Imagem fixa

  frame = cam.capture()  # numpy array BGR (h, w, 3)
  cam.close()
"""

import os
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


class Camera:

    def __init__(self, source="picamera", resolution=(640, 480)):
        """
        Inicializa a câmara.

        Args:
            source: "picamera" | "webcam" | caminho para ficheiro de imagem
            resolution: (largura, altura) — usado por picamera e webcam
        """
        self.source = source
        self.resolution = resolution
        self._cap = None       # cv2.VideoCapture (webcam)
        self._picam = None     # Picamera2 instance
        self._static = None    # numpy array (imagem estática)

        if source == "picamera":
            self._init_picamera()
        elif source == "webcam":
            self._init_webcam()
        elif os.path.isfile(source):
            self._init_static(source)
        else:
            raise ValueError(
                f"Fonte de câmara inválida: '{source}'. "
                "Usa 'picamera', 'webcam' ou caminho para imagem."
            )

    # ── Inicializações por backend ────────────────────────────────────────────

    def _init_picamera(self):
        from picamera2 import Picamera2

        self._picam = Picamera2()
        config = self._picam.create_preview_configuration(
            main={
                "format": "RGB888",
                "size": self.resolution,
            }
        )
        self._picam.configure(config)
        self._picam.start()
        print(f"[CAM] Picamera2 inicializada ({self.resolution[0]}x{self.resolution[1]})")

    def _init_webcam(self):
        if cv2 is None:
            raise ImportError("opencv-python é necessário para modo webcam")

        self._cap = cv2.VideoCapture(0)
        if not self._cap.isOpened():
            raise RuntimeError("Não foi possível abrir a webcam")

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])

        # Lê um frame para confirmar que funciona
        ret, _ = self._cap.read()
        if not ret:
            raise RuntimeError("Webcam aberta mas não retorna frames")

        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[CAM] Webcam inicializada ({w}x{h})")

    def _init_static(self, path: str):
        if cv2 is None:
            raise ImportError("opencv-python é necessário para carregar imagens")

        img = cv2.imread(path)
        if img is None:
            raise FileNotFoundError(f"Não foi possível carregar imagem: {path}")

        self._static = img
        h, w = img.shape[:2]
        print(f"[CAM] Imagem estática carregada: {path} ({w}x{h})")

    # ── API pública ───────────────────────────────────────────────────────────

    def capture(self) -> np.ndarray:
        """
        Captura um frame.

        Returns:
            numpy array BGR com shape (height, width, 3)
        """
        if self._picam is not None:
            # picamera2 retorna RGB — converter para BGR para consistência com OpenCV
            rgb = self._picam.capture_array()
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        if self._cap is not None:
            ret, frame = self._cap.read()
            if not ret:
                raise RuntimeError("Falha ao capturar frame da webcam")
            return frame

        if self._static is not None:
            return self._static.copy()

        raise RuntimeError("Câmara não inicializada")

    def close(self):
        """Liberta recursos."""
        if self._picam is not None:
            try:
                self._picam.stop()
            except Exception:
                pass
            self._picam = None
            print("[CAM] Picamera2 parada.")

        if self._cap is not None:
            self._cap.release()
            self._cap = None
            print("[CAM] Webcam fechada.")

        self._static = None

    @property
    def is_open(self) -> bool:
        if self._picam is not None:
            return True
        if self._cap is not None:
            return self._cap.isOpened()
        if self._static is not None:
            return True
        return False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
