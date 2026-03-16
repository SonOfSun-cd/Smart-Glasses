from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import random
from ultralytics import YOLO
from PIL import Image
import io

from db import Base, engine, get_db
import models

app = FastAPI()

model = YOLO("./yolov8n.pt")
sessions = []
queue = {}
count = 0


for i in range(30):
    try:
        Base.metadata.create_all(bind=engine)
        break
    except Exception as e:
        print("An error occured while building DB:", str(e))
 

#Запуск сервера
#uvicorn handler:app --reload

def AI_analyse(id, image):
    global count
    #global queue, model
    print("Got image")
    img = Image.open(io.BytesIO(image))
    # img.save(f"images/image_{count}.png")
    count+=1
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

    
def createId():
    id = ''.join(random.choices("AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz0123456789",k=52))
    return id



@app.post("/session/{id}")
async def session_get_image(
    id: str,
    img: UploadFile = File(),
    db: Session = Depends(get_db)):
    #global count, queue
    if id not in sessions:
        raise HTTPException(status_code=400, detail="Данный аккаунт не начинал сессию передачи данных")
    
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
async def start_session(
    login: str,
    password: str,
    db: Session = Depends(get_db)):

    #Позже хэширование будет происходить на стороне клиента
    # login = hashlib.sha256(login.encode()).hexdigest()
    # password = hashlib.sha256(password.encode()).hexdigest()
    a = db.query(models.User).filter(models.User.login == login, models.User.password == password).first()
    id = createId()
    print(a)
    if a is None:
        raise HTTPException(status_code=400, detail="Данный аккаунт не существует")
    sessions.append(id)
    print(sessions)
    return {"id": id}

@app.get("/register/{login}/{password}")
async def register(
    login: str,
    password: str,
    db: Session = Depends(get_db)):

    a = db.query(models.User).filter(models.User.login == login).first()
    print(a)
    if a:
        raise HTTPException(status_code=400, detail="Данный логин уже занят")
    
    db.add(models.User(login=login, password=password))
    db.commit()
    return


@app.get("/")
async def index():
    return {"message": "this is index page"}