"""
sensor_floor.py — Wrapper do sensor TCS com degradação graciosa.

Se o hardware (pigpio) não estiver disponível, o sensor fica no modo stub:
  - is_preto() → False  (nunca bloqueia o robot)
  - get_cor()  → None
Isto permite testar navegação em PC sem hardware.
"""


class FloorSensor:

    def __init__(self, enabled: bool = True):
        self._sensor = None
        self._pi     = None

        if not enabled:
            print("[TCS] Sensor de chão desativado.")
            return

        try:
            import pigpio
            import sensor_cor as tcs

            self._pi = pigpio.pi()
            if not self._pi.connected:
                raise RuntimeError("pigpio daemon não está a correr (executa 'sudo pigpiod')")

            self._sensor = tcs.sensor(
                self._pi,
                OUT=24, S2=22, S3=23, S0=4, S1=17, OE=18,
            )
            self._sensor.set_frequency(2)
            self._sensor.set_sample_size(20)
            print("[TCS] Sensor de chão OK.")

        except Exception as e:
            print(f"[TCS] Hardware indisponível ({e}). Sensor no modo stub.")
            self._sensor = None

    @property
    def available(self) -> bool:
        return self._sensor is not None

    def is_preto(self) -> bool:
        """Retorna True se o tile atual é preto (a não atravessar)."""
        if self._sensor is None:
            return False
        try:
            return self._sensor.is_preto() == "preto"
        except Exception as e:
            print(f"[TCS] Erro em is_preto: {e}")
            return False

    def get_cor(self) -> str | None:
        """Retorna 'preto', 'azul', 'verde', etc., ou None se indisponível."""
        if self._sensor is None:
            return None
        try:
            return self._sensor.get_cor()
        except Exception as e:
            print(f"[TCS] Erro em get_cor: {e}")
            return None

    def close(self):
        if self._pi is not None:
            try:
                self._pi.stop()
            except Exception:
                pass
