from config import *
from  serial_comm import *

serial = SerialComm(port="/dev/ttyS0", baudrate=115200, simulate=False)

resposta = serial.send("PG")
print("Teste conexao")
if resposta:
    print(resposta)
else:
    print("Não chegou")