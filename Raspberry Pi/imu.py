try:
    import smbus2
    _SMBUS_AVAILABLE = True
except ImportError:
    _SMBUS_AVAILABLE = False
import time
import math


class IMU:
    ICM20600_ADDR = 0x69
    AK09918_ADDR  = 0x0C

    def __init__(self, bus_number=1,
                 mag_offset=(0.0, 0.0),
                 mag_scale=(1.0, 1.0),
                 maze_north_offset=0.0):

        self.mag_offset        = mag_offset
        self.mag_scale         = mag_scale
        self.maze_north_offset = maze_north_offset

        # Modo stub — sem hardware I2C (PC / ambiente de desenvolvimento)
        if not _SMBUS_AVAILABLE:
            print("[IMU] smbus2 indisponível — modo stub (sem hardware)")
            self._stub = True
            self.bus   = None
            return

        self._stub  = False
        self.bus    = smbus2.SMBus(bus_number)

        # Acorda ICM20600
        try:
            self.bus.write_byte_data(self.ICM20600_ADDR, 0x6B, 0x00)
            time.sleep(0.1)
        except OSError as e:
            print(f"[IMU AVISO] Falha ao acordar ICM20600: {e}")

        # AK09918 modo continuo 100Hz
        try:
            self.bus.write_byte_data(self.AK09918_ADDR, 0x31, 0x08)
            time.sleep(0.1)
        except OSError as e:
            print(f"[IMU AVISO] Falha ao configurar AK09918: {e}")

    def _read_word_2c(self, addr, reg):
        high = self.bus.read_byte_data(addr, reg)
        low  = self.bus.read_byte_data(addr, reg + 1)
        val  = (high << 8) + low
        return val - 65536 if val >= 0x8000 else val

    def get_gyro(self):
        if self._stub:
            return 0.0, 0.0, 0.0
        # Leitura atomica de 6 bytes (gx, gy, gz)
        try:
            data = self.bus.read_i2c_block_data(self.ICM20600_ADDR, 0x43, 6)
            gx = (data[0] << 8) | data[1]
            gy = (data[2] << 8) | data[3]
            gz = (data[4] << 8) | data[5]
            if gx >= 0x8000: gx -= 65536
            if gy >= 0x8000: gy -= 65536
            if gz >= 0x8000: gz -= 65536
            scale = 131.0
            return gx / scale, gy / scale, gz / scale
        except OSError as e:
            print(f"[IMU AVISO] Erro I2C no giroscópio: {e}")
            return 0.0, 0.0, 0.0

    def get_accel(self):
        if self._stub:
            return 0.0, 0.0, 1.0
        # Leitura atomica de 6 bytes (ax, ay, az)
        try:
            data = self.bus.read_i2c_block_data(self.ICM20600_ADDR, 0x3B, 6)
            ax = (data[0] << 8) | data[1]
            ay = (data[2] << 8) | data[3]
            az = (data[4] << 8) | data[5]
            if ax >= 0x8000: ax -= 65536
            if ay >= 0x8000: ay -= 65536
            if az >= 0x8000: az -= 65536
            scale = 16384.0  # +/-2g
            return ax / scale, ay / scale, az / scale
        except OSError as e:
            print(f"[IMU AVISO] Erro I2C no acelerômetro: {e}")
            return 0.0, 0.0, 0.0

    def get_inclination(self):
        """Retorna o ângulo de inclinação (pitch/roll) aproximado em graus.
        Retorna 180.0 no stub (plano, sem rampas).
        """
        if self._stub:
            return 180.0  # plano — nunca deteta rampa
        ax, ay, az = self.get_accel()
        if (ax, ay, az) == (0.0, 0.0, 0.0):
            return None
        
        # Dependendo da montagem, a inclinação frente/trás pode estar no eixo X ou Y.
        # Estamos calculando com o eixo Y. Se for o eixo X, basta trocar ay por ax.
        inclination = math.atan2(ay, az) * 180 / math.pi
        
        # O atan2 pode retornar negativo, então vamos converter para positivo se necessário, 
        # ou apenas usar o valor absoluto para facilitar a lógica (180 vira 180, -180 vira 180)
        return abs(inclination)

    def get_inclination_signed(self):
        """Retorna o ângulo de inclinação COM SINAL em graus.
        Positivo = inclinado para trás (subindo rampa).
        Negativo = inclinado para a frente (descendo rampa).
        Retorna 0.0 no stub (plano).

        NOTA: O sinal depende da montagem física da IMU no robô.
        Se na prática a subida der negativo, basta inverter o return
        para `-inclination`.
        """
        if self._stub:
            return 0.0  # plano — nunca deteta rampa
        ax, ay, az = self.get_accel()
        if (ax, ay, az) == (0.0, 0.0, 0.0):
            return None

        # Mesmo cálculo que get_inclination, mas SEM abs()
        inclination = math.atan2(ay, az) * 180 / math.pi
        return inclination

    def get_mag(self):
        if self._stub:
            return None
        # Espera até dados estarem prontos (max 10 tentativas)
        for _ in range(10):
            try:
                status = self.bus.read_byte_data(self.AK09918_ADDR, 0x10)
                if status & 0x01:
                    break
            except OSError:
                pass # Ignora falhas momentâneas no status
            time.sleep(0.01)
        else:
            return None  # timeout

        try:
            data = self.bus.read_i2c_block_data(self.AK09918_ADDR, 0x11, 6)
            self.bus.read_byte_data(self.AK09918_ADDR, 0x18)  # liberta buffer
        except OSError as e:
            print(f"[IMU AVISO] Erro I2C ao ler dados do magnetômetro: {e}")
            return None

        mx = (data[1] << 8) | data[0]
        my = (data[3] << 8) | data[2]
        mz = (data[5] << 8) | data[4]
        if mx >= 0x8000: mx -= 65536
        if my >= 0x8000: my -= 65536
        if mz >= 0x8000: mz -= 65536
        return mx * 0.15, my * 0.15, mz * 0.15

    def calibrate_north(self):
        """Le o heading atual bruto e define-o como o Norte (0 graus)."""
        if self._stub:
            return True  # Stub: assume Norte calibrado com sucesso
        mag = self.get_mag()
        if mag is None:
            return False

        mx, my, _ = mag
        mx_cal = (mx - self.mag_offset[0]) * self.mag_scale[0]
        my_cal = (my - self.mag_offset[1]) * self.mag_scale[1]

        raw_heading = -math.atan2(my_cal, mx_cal) * 180 / math.pi
        self.maze_north_offset = raw_heading
        return True

    def get_heading(self):
        mag = self.get_mag()
        if mag is None:
            return None, None

        mx, my, _ = mag

        # Aplicar calibração: remover offset e corrigir escala
        mx_cal = (mx - self.mag_offset[0]) * self.mag_scale[0]
        my_cal = (my - self.mag_offset[1]) * self.mag_scale[1]

        raw_heading = -math.atan2(my_cal, mx_cal) * 180 / math.pi
        # Aplica offset para alinhar 0deg com Norte do labirinto
        heading = (raw_heading - self.maze_north_offset) % 360

        pos = int(round(heading / 90.0)) % 4

        return heading, pos

