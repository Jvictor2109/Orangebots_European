from imu import IMU
import time
from config import *

imu = IMU()
time_base = time.time()
angulo_atual = 0.0


while True:
    gyro = imu.get_gyro()
    z_axys = gyro[2]

    vel_angular = z_axys - GYRO_OFFSET

    time_atual = time.time()

    delta_time = time_atual -time_base
    time_base = time_atual

    angulo_atual += vel_angular * delta_time
    print(angulo_atual)
    time.sleep(0.01)