
import smbus2
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

bus = smbus2.SMBus(1)

AK09918_ADDR = 0x0C
ICM20600_ADDR = 0x69

# Acorda ICM20600 (necessário para o I2C bypass ao AK09918)
bus.write_byte_data(ICM20600_ADDR, 0x6B, 0x00)
time.sleep(0.1)

# AK09918 modo contínuo 100Hz
bus.write_byte_data(AK09918_ADDR, 0x31, 0x08)
time.sleep(0.1)


def get_mag():
    for _ in range(10):
        status = bus.read_byte_data(AK09918_ADDR, 0x10)
        if status & 0x01:
            break
        time.sleep(0.01)
    else:
        return None

    data = bus.read_i2c_block_data(AK09918_ADDR, 0x11, 6)
    bus.read_byte_data(AK09918_ADDR, 0x18)

    mx = (data[1] << 8) | data[0]
    my = (data[3] << 8) | data[2]
    if mx >= 0x8000: mx -= 65536
    if my >= 0x8000: my -= 65536
    return mx * 0.15, my * 0.15


DURACAO = 30  # segundos de recolha

print("=" * 50)
print("  CALIBRAÇÃO DO MAGNETÓMETRO AK09918")
print("=" * 50)
print(f"\nRoda a IMU lentamente em 360° durante {DURACAO} segundos.")
print("Tenta manter nivelado e cobrir todas as direções.\n")
input("Pressiona ENTER para começar...")
print()

samples_x = []
samples_y = []

start = time.time()
count = 0

while time.time() - start < DURACAO:
    mag = get_mag()
    if mag:
        mx, my = mag
        samples_x.append(mx)
        samples_y.append(my)
        count += 1

        elapsed = time.time() - start
        remaining = DURACAO - elapsed
        print(f"\r  Amostras: {count} | Tempo restante: {remaining:.0f}s  ", end="", flush=True)

    time.sleep(0.05)

print(f"\n\nRecolhidas {count} amostras.\n")

if count < 20:
    print("ERRO: Poucas amostras recolhidas. Verifica a ligação ao sensor.")
    sys.exit(1)

# --- Hard-iron (offset) ---
min_x = min(samples_x)
max_x = max(samples_x)
min_y = min(samples_y)
max_y = max(samples_y)

offset_x = (max_x + min_x) / 2
offset_y = (max_y + min_y) / 2

# --- Soft-iron (escala) ---
range_x = (max_x - min_x) / 2
range_y = (max_y - min_y) / 2
avg_range = (range_x + range_y) / 2

if range_x == 0 or range_y == 0:
    print("ERRO: Sem variação num dos eixos. Rodaste a IMU em todas as direções?")
    sys.exit(1)

scale_x = avg_range / range_x
scale_y = avg_range / range_y

print("=" * 50)
print("  RESULTADOS DA CALIBRAÇÃO")
print("=" * 50)
print(f"\n  Hard-iron offsets:")
print(f"    OFFSET_X = {offset_x:.4f}")
print(f"    OFFSET_Y = {offset_y:.4f}")
print(f"\n  Soft-iron scales:")
print(f"    SCALE_X  = {scale_x:.4f}")
print(f"    SCALE_Y  = {scale_y:.4f}")
print(f"\n  Raw ranges:")
print(f"    X: [{min_x:.2f}, {max_x:.2f}]")
print(f"    Y: [{min_y:.2f}, {max_y:.2f}]")
print()
print("=" * 50)
print("  Cola isto no teu código:")
print("=" * 50)
print(f"""
  imu = IMU(
      mag_offset=({offset_x:.4f}, {offset_y:.4f}),
      mag_scale=({scale_x:.4f}, {scale_y:.4f})
  )
""")
