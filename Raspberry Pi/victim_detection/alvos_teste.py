import cv2
import numpy
import cognitive_target

detetor = cognitive_target.CognitiveTargetDetector()

frame = cv2.imread("C:/Users/Aluno.AEA/Documents/Joao/Robocup/Raspberry Pi/victim_detection/teste1.png")
resultado = detetor.detect(frame)
print(resultado)