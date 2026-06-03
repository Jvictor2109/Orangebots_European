import serial

s = serial.Serial('/dev/ttyS0', 115200, timeout=2)
s.write(b'hello\n')
print(s.readline().decode())
s.close()