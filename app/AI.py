from ultralytics import YOLO
import cv2
import time

model = YOLO("./yolov8n.pt")
for i in range(1000000):
    try:
        f = open(f"./images/img_{i}.jpg", "r")
        f.close()
    except:
        continue

    

    frame = model.predict(f"./images/img_{i}.jpg", conf=0.5)
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
    key = cv2.waitKey(1000) & 0xFF
cv2.destroyAllWindows()

