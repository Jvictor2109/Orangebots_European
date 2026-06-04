import RPi.GPIO as GPIO
import time
import math

class TCS3200:
    """
    TCS3200 Color Sensor class for Raspberry Pi.
    Instead of using pulse width measurement like Arduino's pulseIn (which is inaccurate
    on a Linux OS), this implementation uses hardware interrupts to count pulse frequency.
    """
    # Filter colors
    COLOR_RED = 0
    COLOR_GREEN = 1
    COLOR_BLUE = 2
    COLOR_CLEAR = 3

    # Frequency scaling
    PWR_DOWN = 0
    OFREQ_2P = 1
    OFREQ_20P = 2
    OFREQ_100P = 3

    def __init__(self, s0_pin, s1_pin, s2_pin, s3_pin, out_pin):
        self._s0_pin = s0_pin
        self._s1_pin = s1_pin
        self._s2_pin = s2_pin
        self._s3_pin = s3_pin
        self._out_pin = out_pin

        # Calibration limits (in frequencies: pulses per integration period)
        self.min_r, self.max_r = 0, 1000
        self.min_g, self.max_g = 0, 1000
        self.min_b, self.max_b = 0, 1000

        self._integration_time = 0.05  # 50ms integration time to count pulses
        self._frequency_scaling = self.OFREQ_20P
        self.is_calibrated = False

        self.white_balance_rgb = {'red': 0, 'green': 0, 'blue': 0}
        self._pulse_count = 0

    def begin(self):
        GPIO.setmode(GPIO.BCM)
        
        GPIO.setup(self._s0_pin, GPIO.OUT)
        GPIO.setup(self._s1_pin, GPIO.OUT)
        GPIO.setup(self._s2_pin, GPIO.OUT)
        GPIO.setup(self._s3_pin, GPIO.OUT)
        
        # Sensor output is read via interrupts to avoid busy-waiting loop inaccuracies
        GPIO.setup(self._out_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(self._out_pin, GPIO.RISING, callback=self._pulse_callback)
        
        self.frequency_scaling(self._frequency_scaling)

    def cleanup(self):
        """Cleans up GPIO settings. Important to call when exiting the program."""
        GPIO.remove_event_detect(self._out_pin)
        GPIO.cleanup([self._s0_pin, self._s1_pin, self._s2_pin, self._s3_pin, self._out_pin])

    def _pulse_callback(self, channel):
        self._pulse_count += 1

    def select_filter(self, filter_color):
        if filter_color == self.COLOR_RED:
            GPIO.output(self._s2_pin, GPIO.LOW)
            GPIO.output(self._s3_pin, GPIO.LOW)
        elif filter_color == self.COLOR_GREEN:
            GPIO.output(self._s2_pin, GPIO.HIGH)
            GPIO.output(self._s3_pin, GPIO.HIGH)
        elif filter_color == self.COLOR_BLUE:
            GPIO.output(self._s2_pin, GPIO.LOW)
            GPIO.output(self._s3_pin, GPIO.HIGH)
        elif filter_color == self.COLOR_CLEAR:
            GPIO.output(self._s2_pin, GPIO.HIGH)
            GPIO.output(self._s3_pin, GPIO.LOW)

    def frequency_scaling(self, scaling):
        self._frequency_scaling = scaling
        if scaling == self.PWR_DOWN:
            GPIO.output(self._s0_pin, GPIO.LOW)
            GPIO.output(self._s1_pin, GPIO.LOW)
        elif scaling == self.OFREQ_2P:
            GPIO.output(self._s0_pin, GPIO.LOW)
            GPIO.output(self._s1_pin, GPIO.HIGH)
        elif scaling == self.OFREQ_20P:
            GPIO.output(self._s0_pin, GPIO.HIGH)
            GPIO.output(self._s1_pin, GPIO.LOW)
        elif scaling == self.OFREQ_100P:
            GPIO.output(self._s0_pin, GPIO.HIGH)
            GPIO.output(self._s1_pin, GPIO.HIGH)

    def _read_frequency(self, color_filter):
        self.select_filter(color_filter)
        time.sleep(0.01)  # Allow photodiode to settle
        
        self._pulse_count = 0
        time.sleep(self._integration_time)
        return self._pulse_count

    def _map_value(self, x, in_min, in_max, out_min, out_max):
        if in_max == in_min:
            return out_min
        val = (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
        
        if out_min < out_max:
            return max(out_min, min(out_max, val))
        return max(out_max, min(out_min, val))

    def read_red(self):
        freq = self._read_frequency(self.COLOR_RED)
        if self.is_calibrated:
            return int(self._map_value(freq, self.min_r, self.max_r, 0, 255))
        return int(self._map_value(freq, 0, 1000, 0, 255))

    def read_green(self):
        freq = self._read_frequency(self.COLOR_GREEN)
        if self.is_calibrated:
            return int(self._map_value(freq, self.min_g, self.max_g, 0, 255))
        return int(self._map_value(freq, 0, 1000, 0, 255))

    def read_blue(self):
        freq = self._read_frequency(self.COLOR_BLUE)
        if self.is_calibrated:
            return int(self._map_value(freq, self.min_b, self.max_b, 0, 255))
        return int(self._map_value(freq, 0, 1000, 0, 255))

    def read_clear(self):
        return self._read_frequency(self.COLOR_CLEAR)

    def calibrate(self):
        """Finalize calibration."""
        self.is_calibrated = True

    def calibrate_light(self):
        """
        Calibrate on a white surface.
        White reflects the most light, yielding the highest pulse frequency.
        """
        r, g, b = 0, 0, 0
        samples = 10
        for _ in range(samples):
            r += self._read_frequency(self.COLOR_RED)
            g += self._read_frequency(self.COLOR_GREEN)
            b += self._read_frequency(self.COLOR_BLUE)
        
        self.max_r = r / samples
        self.max_g = g / samples
        self.max_b = b / samples
        self.white_balance_rgb = {'red': self.max_r, 'green': self.max_g, 'blue': self.max_b}

    def calibrate_dark(self):
        """
        Calibrate on a black surface.
        Black absorbs light, yielding the lowest pulse frequency.
        """
        r, g, b = 0, 0, 0
        samples = 10
        for _ in range(samples):
            r += self._read_frequency(self.COLOR_RED)
            g += self._read_frequency(self.COLOR_GREEN)
            b += self._read_frequency(self.COLOR_BLUE)
        
        self.min_r = r / samples
        self.min_g = g / samples
        self.min_b = b / samples

    def read_rgb_color(self):
        return {
            'red': self.read_red(),
            'green': self.read_green(),
            'blue': self.read_blue()
        }

    def get_rgb_dominant_color(self):
        color = self.read_rgb_color()
        max_val = max(color['red'], color['green'], color['blue'])
        
        if max_val == color['red']:
            return self.COLOR_RED
        elif max_val == color['green']:
            return self.COLOR_GREEN
        return self.COLOR_BLUE

    # More advanced conversions (HSV, CMYK) can be easily added on top of read_rgb_color.
    def read_hsv(self):
        rgb = self.read_rgb_color()
        r = rgb['red'] / 255.0
        g = rgb['green'] / 255.0
        b = rgb['blue'] / 255.0

        max_val = max(r, g, b)
        min_val = min(r, g, b)
        delta = max_val - min_val

        v = max_val
        s = delta / max_val if max_val > 0 else 0.0

        h = 0.0
        if delta > 0:
            if max_val == r:
                h = 60 * (((g - b) / delta) % 6)
            elif max_val == g:
                h = 60 * (((b - r) / delta) + 2)
            else:
                h = 60 * (((r - g) / delta) + 4)
        
        if h < 0:
            h += 360

        return {'hue': h, 'saturation': s, 'value': v}

    # ── Classificação de cor (HSV) ────────────────────────────────────────────

    def get_cor(self, black_v_max=0.15, white_s_max=0.15, white_v_min=0.70) -> str | None:
        """
        Lê HSV e classifica a cor do tile:
          - 'preto', 'branco', 'vermelho', 'azul', 'verde', 'amarelo', 'desconhecido'
        Retorna None se o sensor não estiver inicializado.

        Thresholds configuráveis via argumentos (defaults de config.py).
        """
        try:
            hsv = self.read_hsv()
        except Exception as e:
            print(f"[TCS] Erro em get_cor: {e}")
            return None

        h, s, v = hsv['hue'], hsv['saturation'], hsv['value']

        # Preto: value muito baixo (superfície absorve quase toda a luz)
        if v <= black_v_max:
            return "preto"

        # Branco: saturação muito baixa + value alto (reflete tudo igualmente)
        if s <= white_s_max and v >= white_v_min:
            return "branco"

        # Classificação por hue (matiz)
        if h < 15 or h >= 345:
            return "vermelho"
        if 15 <= h < 45:
            return "laranja"
        if 45 <= h < 80:
            return "amarelo"
        if 80 <= h < 160:
            return "verde"
        if 160 <= h < 200:
            return "ciano"
        if 200 <= h < 260:
            return "azul"
        if 260 <= h < 300:
            return "roxo"
        if 300 <= h < 345:
            return "magenta"

        return "desconhecido"

    def is_preto(self, black_v_max=0.15) -> bool:
        """Retorna True se o tile atual é preto (a não atravessar)."""
        try:
            hsv = self.read_hsv()
            return hsv['value'] <= black_v_max
        except Exception as e:
            print(f"[TCS] Erro em is_preto: {e}")
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# STUB — Sensor virtual quando hardware não está disponível
# ═══════════════════════════════════════════════════════════════════════════════

class _StubSensor:
    """Stub que substitui o TCS3200 quando o hardware não está disponível.
    Nunca bloqueia o robot (is_preto → False) e nunca deteta cor (get_cor → None).
    """

    @property
    def available(self) -> bool:
        return False

    def is_preto(self) -> bool:
        return False

    def get_cor(self) -> str | None:
        return None

    def cleanup(self):
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# FACTORY — Cria sensor real ou stub (degradação graciosa)
# ═══════════════════════════════════════════════════════════════════════════════

def create_floor_sensor(enabled: bool = True):
    """
    Cria e inicializa o sensor TCS3200, ou devolve um _StubSensor se:
      - enabled=False (utilizador pediu --no-floor)
      - RPi.GPIO não está disponível (a correr em PC)
      - Qualquer erro de hardware

    Retorna um objeto com interface: is_preto(), get_cor(), cleanup().
    """
    if not enabled:
        print("[TCS] Sensor de chão desativado.")
        return _StubSensor()

    try:
        from config import TCS_S0, TCS_S1, TCS_S2, TCS_S3, TCS_OUT
        from config import TCS_BLACK_VALUE_MAX, TCS_WHITE_SAT_MAX, TCS_WHITE_VALUE_MIN
        from config import TCS_USE_PREDEFINED_CALIBRATION, TCS_CALIBRATION_BLACK, TCS_CALIBRATION_WHITE

        sensor = TCS3200(
            s0_pin=TCS_S0, s1_pin=TCS_S1,
            s2_pin=TCS_S2, s3_pin=TCS_S3,
            out_pin=TCS_OUT,
        )
        sensor.begin()

        # Aplicar calibração predefinida (se ativado)
        if TCS_USE_PREDEFINED_CALIBRATION:
            sensor.min_r = TCS_CALIBRATION_BLACK['r']
            sensor.min_g = TCS_CALIBRATION_BLACK['g']
            sensor.min_b = TCS_CALIBRATION_BLACK['b']
            sensor.max_r = TCS_CALIBRATION_WHITE['r']
            sensor.max_g = TCS_CALIBRATION_WHITE['g']
            sensor.max_b = TCS_CALIBRATION_WHITE['b']
            sensor.is_calibrated = True
            print("[TCS] Usando calibração predefinida do config.py.")

        # Guardar thresholds de config para usar em get_cor / is_preto
        sensor._black_v_max = TCS_BLACK_VALUE_MAX
        sensor._white_s_max = TCS_WHITE_SAT_MAX
        sensor._white_v_min = TCS_WHITE_VALUE_MIN

        # Monkey-patch get_cor e is_preto para usarem thresholds do config
        _original_get_cor = sensor.get_cor
        _original_is_preto = sensor.is_preto
        sensor.get_cor = lambda: _original_get_cor(
            black_v_max=TCS_BLACK_VALUE_MAX,
            white_s_max=TCS_WHITE_SAT_MAX,
            white_v_min=TCS_WHITE_VALUE_MIN,
        )
        sensor.is_preto = lambda: _original_is_preto(
            black_v_max=TCS_BLACK_VALUE_MAX,
        )

        print("[TCS] Sensor de chão OK.")
        return sensor

    except Exception as e:
        print(f"[TCS] Hardware indisponível ({e}). Sensor no modo stub.")
        return _StubSensor()

