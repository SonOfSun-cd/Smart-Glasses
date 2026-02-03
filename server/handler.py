from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import FileResponse, RedirectResponse
import sqlite3
import hashlib
import random
import threading
from ultralytics import YOLO
from PIL import Image
import cv2
import io
app = FastAPI()

model = YOLO("./yolov8n.pt")
sessions = []
queue = {}
count = 0

#Запуск сервера
#uvicorn handler:app --reload

def AI_analyse(id, image):
    global count
    #global queue, model
    print("Got image")
    img = Image.open(io.BytesIO(image))
    # img.save(f"images/image_{count}.png")
    # count+=1
    frame = model.predict(img, conf=0.5)
    objects = []
    cords = []
    result = frame[0]
    if result.boxes is not None:
        # Получите классы, confidence и координаты
        classes = result.boxes.cls  # Классы (номера)
        class_names = result.names  # Словарь с именами классов
        # Сформируйте список объектов
        for idx, cls in enumerate(classes):
            object_name = class_names[int(cls)]
            objects.append(object_name)
        for idx, box in enumerate(result.boxes.xyxy):
            x1, y1, x2, y2 = box.tolist()
            cords.append([round(x1,2), round(y1,2), round(x2,2), round(y2,2)])
    queue.update({id: {"objects": objects, "cords": cords}})
    return

    



@app.post("/session/{id}")
async def session_get_image(id: str, img: UploadFile = File()):
    #global count, queue
    if id not in sessions:
        return {"error": "this account didnt start any streaming session"}
    content = await img.read()
    # r = threading.Thread(target=AI_analyse, args=(id, content))
    # r.start()
    AI_analyse(id, content)
    # f = open(f"./images/img_{count}.jpg", "wb")
    # count+=1
    # f.write(content)
    # f.close()
    # if content:
    #     print("Got Image succesfully")
    if id in queue.keys():
        answer = queue.pop(id)
        return {"answer": answer}
    print(queue)
    return {"answer": "..."}


@app.get("/sessions")
async def query_sessions():
    return {"sessions": sessions, "queue": queue}

@app.get("/start/{login}/{password}")
async def start_session(login: str, password: str):

    #Позже хэширование будет происходить на стороне клиента
    # login = hashlib.sha256(login.encode()).hexdigest()
    # password = hashlib.sha256(password.encode()).hexdigest()

    connection = sqlite3.connect("handler_db.db")
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM USER_DATA WHERE login = ? AND password = ?", (login, password))
    a = cursor.fetchall()
    print(a)
    if a==[]:
        return {"error": "this account doesnt exist"}
    elif a[0][2] in sessions:
        return {"error": "this account already started streaming session"}
    print(a[0][2])
    sessions.append(a[0][2])
    print(sessions)
    connection.close()

@app.get("/register/{login}/{password}")
async def register(login: str, password: str):
    connection = sqlite3.connect("handler_db.db")
    cursor = connection.cursor()

    # #Позже хэширование будет происходить на стороне клиента
    # login = hashlib.sha256(login.encode()).hexdigest()
    # password = hashlib.sha256(password.encode()).hexdigest()

    cursor.execute("SELECT * FROM USER_DATA WHERE login = ?", (login,))
    a = cursor.fetchall()
    print(a)
    if a!=[]:
        return {"error": "this account already exists"}
    
    
    id = ''.join(random.choices(random.choices("AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz0123456789", k=35),k=52))
    cursor.execute("INSERT INTO USER_DATA (login, password, id) VALUES (?,?,?)",(login, password, id))
    connection.commit()
    connection.close()
    return {"id": id}


@app.get("/")
async def index():
    return {"message": "this is index page"}