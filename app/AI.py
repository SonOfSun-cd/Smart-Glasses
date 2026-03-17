from ultralytics import YOLO
import cv2
import requests
import time
from PIL import Image
import io

model = YOLO("./yolov8n.pt")


ip = "192.168.137.34"
session = requests.Session()
session.headers.update({"Connection": "keep-alive"})

for i in range(1000000):
    try:
        img = session.get(f"http://{ip}:3000/img").content
    
    except:
        print("Not able to establish connection. Retrying...")
        continue
    
    img = Image.open(io.BytesIO(img)).transpose(Image.Transpose.ROTATE_270)
    print(i)

    frame = model.predict(img)
    img = frame[0].plot()
    cv2.imshow('object detection', img)
    objects = []
    cords = []
    result = frame[0]
    if result.boxes is not None:
        # Получите классы, confidence и координаты
        classes = result.boxes.cls  # Классы (номера)
        class_names = result.names  # Словарь с именами классов
        # Сформируйте список объектов
        detected_objects = []
        for idx, cls in enumerate(classes):
            object_name = class_names[int(cls)]
            objects.append(object_name)
        for idx, box in enumerate(result.boxes.xyxy):
            x1, y1, x2, y2 = box.tolist()
            cords.append([round(x1,2), round(y1,2), round(x2,2), round(y2,2)])
    #time.sleep(2)
    print(objects)
    print(cords)
    key = cv2.waitKey(1) & 0xFF
cv2.destroyAllWindows()

