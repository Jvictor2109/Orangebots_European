import traceback
try:
    from picamera2 import Picamera2
    p = Picamera2()
    print("Success")
except Exception as e:
    traceback.print_exc()
