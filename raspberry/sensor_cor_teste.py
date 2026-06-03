import time
from tcs3200 import TCS3200

# Defina os pinos BCM conectados ao sensor
S0 = 17
S1 = 27
S2 = 22
S3 = 23
OUT = 24

# Inicializa
sensor = TCS3200(s0_pin=S0, s1_pin=S1, s2_pin=S2, s3_pin=S3, out_pin=OUT)
sensor.begin()

try:
    print("Por favor, coloque o sensor numa superfície BRANCA...")
    time.sleep(3)
    sensor.calibrate_light()
    
    print("Agora coloque o sensor numa superfície PRETA...")
    time.sleep(3)
    sensor.calibrate_dark()
    
    sensor.calibrate()
    print("Calibração concluída!")
    
    while True:
        # Lê a cor
        rgb = sensor.read_rgb_color()
        print(f"R: {rgb['red']}, G: {rgb['green']}, B: {rgb['blue']}")
        
        # Você também pode ler os valores em HSV
        # hsv = sensor.read_hsv()
        # print(f"H: {hsv['hue']:.2f}")
        
        time.sleep(1)

except KeyboardInterrupt:
    print("Saindo...")
    sensor.cleanup() # Não esqueça de limpar os pinos GPIO