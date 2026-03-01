from kivy.config import Config
from numpy import rint

Config.set('graphics', 'width', '360')
Config.set('graphics', 'height', '620')
# Config.set('graphics', 'resizable', False)

from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput

import time
import requests
from requests.exceptions import HTTPError
import threading
import socket
import json
import hashlib
import pyttsx3


class main_app(App):
    def load_db(self):
        with open("./db.json", "r") as f:
            return json.load(f)
    
    def save_db(self, data):
        with open("./db.json", "w") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    
    def AP_data_send(self):
        #"start", "cmd", "/k", 
        #os.chdir("C:/Users/user/Desktop/cam/flask_servers")
        #winwifi.WinWiFi.connect("ESP32_","pfur0651")
        db = self.load_db()
        db["AP_DATA"]["SSID"] = self.SSID_Input.text
        db["AP_DATA"]["PASSWORD"] = self.PSWRD_Input.text
        self.save_db(db)

        #result = subprocess.Popen(["py","data_exchange.py"], shell=True)
        self.label.text = "Процесс передачи начат"
        try:
            ap_data_request = requests.post("http://192.168.4.1:3000/ap_data", json={"ssid": self.SSID_Input.text, "password": self.PSWRD_Input.text, "ip": "192.168.4.1"})
            ap_data_request.raise_for_status()

            print(ap_data_request.text)

            time.sleep(5)
            try:
                mac_adress = requests.get("http://192.168.4.1:3000/mac")
                mac_adress.raise_for_status()

                self.mac = mac_adress.text
                print(self.mac)
            except HTTPError as e:
                self.label.text = f"Ошибка при получении MAC адреса: {e}"
                return
        except HTTPError as e:
            self.label.text = f"Ошибка при передаче данных: {e}"
            return
        if self.is_getting_AP_data:
            self.label.text = "Процесс передачи завершен"
            self.is_getting_AP_data = False
            self.sent_AP_data = True
        self.AP_send_button.background_color = self.colors["grey"]
        return
    
    def AI_analyse(self, answer):
        filters = ["car", "person", "dog", "cat", "bird", "handbag", "suitcase", "umbrella", "tv", "laptop", "microwave", "oven"]
        distance_filter = {
            "person": [300, 700], 
            "handbag": [80, 170], 
            "car": [500, 700], 
            "bird": [50,50], 
            "dog": [150, 250], 
            "cat": [150, 250], 
            "umbrella": [150, 250],
            "tv": [150, 250], 
            "laptop": [150, 250],
            "oven": [150, 250],
            "tv": [150, 250],
            "microwave": [150, 250],
            "suitcase": [150, 250],
            }
        
        max_width = 1920 #Какая максимальная ширина изображения в пикселях
        max_dist = 500 #В пикселях относительно исходного изображения
        max_movement = 150 #Сколько максимально в пикселях может переместиться объект типа car перед тем как система оповестит пользователя

        positions = {"Слева": [0, 0.25*max_width/2], "Чуть левее": [0.25*max_width/2, 0.75*max_width/2], "Спереди": [0.75*max_width/2, 1.25*max_width/2], "Чуть правее": [1.25*max_width/2, 1.75*max_width/2], "Справа": [1.75*max_width/2, max_width]}

        obj = answer["objects"]
        cords = answer["cords"]
        centers = [[cords[i][0]+(cords[i][2]-cords[i][0])/2, cords[i][1]+(cords[i][3]-cords[i][1])/2] for i in range(len(obj))]
        groups_depth=[]
        movement_group = []
        depth_dict = {}
    

        #Алгоритм по отделению объектов по группам по глубине на изображении
        for i in range(len(obj)):
            match = False
            length = cords[i][2]-cords[i][0]
            des_l = distance_filter[obj[i]][0]
            des_h = distance_filter[obj[i]][1]
            height = cords[i][3]-cords[i][1]
            if groups_depth!=[]:
                distance = des_l/length
                if abs(des_l/length-des_h/height)>0.5:
                    distance = distance if length/height > des_l/des_h else des_h/height
                for j in range(len(groups_depth)):
                    if abs(groups_depth[j][0]-distance) <= 0.2*distance:
                        groups_depth[j].append(i)
                        groups_depth[j][0]=(groups_depth[j][0]+distance)/2
                        if obj[i]=="car":
                            depth_dict.update({f"{i}": groups_depth[j][0]})
                        match=True
                        break
            if groups_depth==[] or not match:
                distance = des_l/length
                if abs(des_l/length-des_h/height)>0.5:
                    distance = distance if length/height > des_l/des_h else des_h/height
                if obj[i]=="car":
                    depth_dict.update({f"{i}": distance})
                groups_depth.append([distance, i]) 
        print(obj)
        print(groups_depth)
        #print(depth_dict)

        #Алгоритм по нахождению аномальных движений машин и фиксированию их
        alert_group = []
        if self.previous_centers!=[] and "car" in self.previous_objects:
            group_now = [i for i in range(len(obj)) if obj[i]=="car"]
            group_previous = [i for i in range(len(self.previous_objects)) if self.previous_objects[i]=="car"]
            for now in group_now:
                min_dist = 100000
                ind = 0
                center_now = centers[now]
                for prev in group_previous:
                    center_prev = self.previous_centers[prev]
                    distance = ((center_now[0]-center_prev[0])**2+(center_now[1]-center_prev[1])**2)**0.5
                    if abs(depth_dict[str(now)]-self.previous_Y_groups[str(prev)])<=0.5 and min_dist>distance:
                        min_dist = distance
                        ind = prev
                #print(ind)
                if min_dist>=max_movement*(depth_dict[str(now)]+self.previous_Y_groups[str(ind)])/2:
                    alert_group.append(now)
                    group_previous.remove(ind)
                    position = ""
                    for pos in positions:
                        if centers[now][0]<=positions[pos][1] and centers[now][0]>=positions[pos][0]:
                            position = pos
                            break
                    self.queue.append(f"!Внимание, {position} от вас резкое движение объекта {obj[now]}")
            #abs(self.previous_centers[prev]-centers[now])<=max_movement*(depth_dict[str(now)]+self.previous_Y_groups[str(prev)])/2
            pass
        
        #Алгоритм по отделению уже этих групп на группы близких по горизонтали и фильтрация объектов в группах
        def cluster(dist, n, List, max_dista):
            group = []
            center_n = centers[n]
            for i in List:
                center_i = centers[i]
                if ((center_n[0]-center_i[0])**2+(center_n[1]-center_i[1])**2)**0.5*dist<max_dista:
                    group.append(i)
                    b=List
                    b.remove(i)
                    if n in List:
                        b.remove(n)
                    group+=cluster(dist, i, b, max_dista)
                #print(center_n, center_i)
            return group
        groups = []
        for i in groups_depth:
            Lista = i[1:]
            for j in i[1:]:
                if j not in Lista:
                    continue
                group = cluster(i[0], j, Lista, max_dist)
                group_unedited = group.copy()
                #print(group, Lista)
                # for filter in filters:
                #     for k in group_unedited:
                #         if obj[k]==filter:
                #             group.remove(k)
                #             group.append(k)
                #             print(group, filter)
                groups.append([i[0]]+[[sum(centers[k][0] for k in group)/len(group), sum(centers[k][1] for k in group)/len(group)] ]+group)
        
        #Фильтрация групп относительно фильтра важности объектов
        for i in filters:
            for j in groups:
                for k in j[2:]:
                    if obj[k]==i:
                        groups.remove(j)
                        groups.append(j)
                
        print(groups)
        print(alert_group)
        print("_______________________________")
        self.previous_centers = centers
        self.previous_objects = obj
        self.previous_Y_groups = depth_dict

        #Формирование текста, описывающего кадр
        text = ""
        for i in groups:
            local_text = ""
            position = ""
            for pos in positions:
                if i[1][0]<=positions[pos][1] and i[1][0]>=positions[pos][0]:
                    position = pos
                    break
            objects_in_group = [obj[j] for j in i[2:]]
            local_text+=position+" на расстоянии приблизительно "+str(i[0])+" метров от Вас находится группа из " + ', '.join([str(objects_in_group.count(j))+" "+j for j in filters if objects_in_group.count(j)!=0])
            text+=f"{local_text}; \n"
        self.queue.append(text)
        print(text)
        print(self.queue)

        return
    
    def Voice_text(self):
        while True:
            if self.queue:
                text = ""
                rate = 230
                if any("!" in text for text in self.queue):
                    text = [text for text in self.queue if "!" in text][0]
                    self.queue.remove(text)
                    rate=300
                else:
                    text = self.queue[0]
                    self.queue = self.queue[1:]
                    print(text)
                self.say = threading.Thread(target=self.Voice_process, args=(text, rate))
                self.say.start()


    def Voice_process(self, text, rate):
        engine = pyttsx3.init()
        engine.setProperty('rate', rate)
        engine.say(text)
        engine.runAndWait()


    def Server_start(self):
        IP = "192.168.137.85"
        i=0
        session = requests.Session()
        session.headers.update({"Connection": "keep-alive"})

        #Начало сессии с головным сервером

        login = hashlib.sha256(self.login.encode()).hexdigest()
        password = hashlib.sha256(self.password.encode()).hexdigest()
        try:
            session_start = requests.get(f"http://127.0.0.1:8000/start/{login}/{password}")
            session_start.raise_for_status()

            print(session_start.json())
            self.id = session_start.json()["id"]
        except HTTPError as error:
            self.label.text = f"Ошибка при установлении соединения: {error.response.text}"
            return
            
        while self.started_server:
            try:
                img = session.get(f"http://{IP}:3000/img")
                if img.status_code == 200:
                    files = {"img": img.content}
                    try:
                        answer = session.post(f"http://127.0.0.1:8000/session/{self.id}", files=files)
                        answer.raise_for_status()

                        if answer.json()["answer"]!="...":
                            f = threading.Thread(target=self.AI_analyse, args=(answer.json()["answer"],))
                            f.start()
                    except HTTPError as error:
                        self.label.text = f"Ошибка при отправке изображения: {error.response.text}"
                        return
                    i+=1
            except:
                self.label.text = f"Не получается установить соединение. Повторяю попытку..."
                continue
            # files = {"img": open(f"./images/img_{i}.jpg", "rb")}
            # answer = requests.post(f"http://127.0.0.1:8000/session/{self.id}", files=files)
            # print(answer.json())
            # i+=1
            #print(answer.json())
        #server = subprocess.Popen(["py","server.py"], shell=True)
        #ai_analyse = subprocess.Popen(["py", "AI.py"], shell=True)
        self.label.text = "..."
        self.previous_centers = []
        self.previous_objects = []
        self.previous_Y_groups = []
        return
    
    def terminate_url(self):
        try:
            f=requests.post("http://127.0.0.1:3000/IP",json={"IP": "..."})
            requests.post("http://127.0.0.1:3000/end")
        except:
            print("Terminated")
        return
        
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.previous_centers = []
        self.previous_objects = []
        self.previous_Y_groups = {}
        self.queue = []

        self.check = "Hello!"
        self.is_getting_AP_data = False
        self.sent_AP_data = False
        self.started_server = False
        self.labels = {"start": "Устанавливаю полное соединение с очками", "stop": "Выключаю соединение", "deny": "Сначала вам необходимо передать данные о точке доступа"}
        self.img = b""

        self.colors = {"green": (0,1,0,1), "red": (1,0,0,1), "grey": (1,1,1,1)}

        db = self.load_db()
        name = socket.gethostname()
        IP = "10.243.62.9"
        print(IP, name)
        db["AP_DATA"]["ip"] = IP
        self.save_db(db)
        
        ap_data = db["AP_DATA"]
        print(ap_data)
        self.sent_AP_data = True if ap_data.get("EXCHANGED") else False
        self.SSID = ap_data.get("SSID", "")
        self.PSWRD = ap_data.get("PASSWORD", "")
        self.mac = ap_data.get("MAC", "")
        print(self.sent_AP_data)
        
        user_data = db["USER_DATA"]
        self.login = user_data.get("login")
        self.password = user_data.get("password")
        self.id = user_data.get("id")
        
        if self.login:
            print(user_data)
        else:
            self.login = None
            self.password = None
            self.id = None

    def build(self):
        self.main_layout = BoxLayout(orientation="vertical")
        self.create_main_layout()
        self.create_login_layout()
        self.main_layout.add_widget(self.layout)
        return self.main_layout
    
    def create_main_layout(self):
        self.layout = BoxLayout(orientation="vertical")

        #Кнопка регистрации
        button_layout = BoxLayout(orientation="horizontal")
        button_layout.size_hint_y = None
        button_layout.height = 75
        self.Register_button = Button(text="Зарегистрироваться", size=(10,10))
        self.Register_button.bind(on_press=self.register)
        button_layout.add_widget(Label(text=self.login if self.login!=None else "Вы не вошли в аккаунт", font_size="12sp"))
        button_layout.add_widget(self.Register_button)
        self.layout.add_widget(button_layout)

        
        #---

        self.layout.add_widget(Label(text="Данные вашей точки доступа", font_size="24sp" ))
        big_layout = BoxLayout(orientation="vertical")
        ssid_layout = BoxLayout(orientation="horizontal")
        h=80
        self.SSID_Input = TextInput(text=(self.SSID if self.SSID!=None and self.SSID!="" else "Введите SSID"), halign="center", size_hint_y = None, multiline=False, height=h)
        ssid_layout.add_widget(Label(text="SSID: ",size_hint_y = None, height=h, font_size="16sp"))
        ssid_layout.add_widget(self.SSID_Input)
        big_layout.add_widget(ssid_layout)
        
        password_layout = BoxLayout(orientation="horizontal")
        self.PSWRD_Input = TextInput(text=(self.PSWRD if self.PSWRD!=None and self.PSWRD!="" else "Введите пароль"), halign="center")
        password_layout.add_widget(Label(text="Пароль: ", font_size="16sp"))
        password_layout.add_widget(self.PSWRD_Input)
        big_layout.add_widget(password_layout)
        self.layout.add_widget(big_layout)

        self.AP_send_button = Button(text="Начать передачу")
        self.Server_start_button = Button(text="Установить соединение с очками")
        self.Server_start_button.bind(on_press=self.Server_start_func)
        self.Terminate_button = Button(text="Принудительно завершить текущий процесс", background_color=(1,0,0,1))
        self.Terminate_button.bind(on_press=self.Terminate_func)
        self.AP_send_button.bind(on_press=self.AP_data_send_func)
        #self.layout.add_widget(self.SSID_Input)
        self.layout.add_widget(self.AP_send_button)
        self.layout.add_widget(self.Server_start_button)
        self.label = Label(text="...")
        self.layout.add_widget(self.label)
        self.layout.add_widget(self.Terminate_button)
    
    def create_login_layout(self):
        self.login_layout = BoxLayout(orientation="vertical")

        button_layout = BoxLayout(orientation="horizontal")
        button_layout.size_hint_y = None
        button_layout.height = 50
        register_cancel = Button(text="Назад", height=30)
        register_cancel.bind(on_press=self.cancel_register)
        register_cancel.background_color = self.colors["red"]
        button_layout.add_widget(Label(text="   ", font_size="12sp"))
        button_layout.add_widget(register_cancel)
        self.login_layout.add_widget(button_layout)

        self.login_layout_label = Label(text="Регистрация аккаунта/Вход в аккаунт", font_size="20sp")
        self.login_layout.add_widget(self.login_layout_label)
        self.login_input = TextInput(text=self.login if self.login!=None else "Введите логин", halign="center", size_hint_y = None, font_size="20sp")
        self.login_layout.add_widget(self.login_input)
        self.password_input = TextInput(text=self.password if self.password!=None else "Введите пароль", halign="center", size_hint_y = None, font_size="20sp")
        self.login_layout.add_widget(self.password_input)
        submit = Button(text="Зарегистрироваться")
        Register_button = Button(text="Войти")
        submit.bind(on_press=self.submit_register)
        self.login_layout.add_widget(submit)
        self.login_layout.add_widget(Register_button)
        

    
    def on_stop(self):
        db = self.load_db()
        db["AP_DATA"]["SSID"] = self.SSID_Input.text
        db["AP_DATA"]["PASSWORD"] = self.PSWRD_Input.text
        db["AP_DATA"]["EXCHANGED"] = bool(self.sent_AP_data)
        db["AP_DATA"]["MAC"] = self.mac
        db["USER_DATA"]["login"] = self.login
        db["USER_DATA"]["password"] = self.password
        self.save_db(db)
        print("Commiting all changes")

    #Функции для кнопок

    def AP_data_send_func(self, instance):
        if not self.is_getting_AP_data:  
            f = threading.Thread(target=self.AP_data_send)
            f.start()
            self.is_getting_AP_data = True
            self.AP_send_button.background_color = self.colors["green"]
        else:
             self.label.text="Передача уже началась!"

    def Server_start_func(self, instance):
        if self.sent_AP_data and not self.started_server:
            self.label.text=self.labels["start"]
            self.Server_start_button.background_color = self.colors["green"]
            self.started_server=True
            f = threading.Thread(target=self.Server_start)
            f.start()
            # k = threading.Thread(target=self.AI_analyse)
            # k.start()
        elif self.started_server:
            self.label.text=self.labels["stop"]
            self.started_server=False
            self.Server_start_button.background_color = self.colors["grey"]
        else:
            self.label.text=self.labels["deny"]

    def Terminate_func(self, instance):
        x = threading.Thread(target=self.terminate_url)
        x.start()
        if self.is_getting_AP_data:
            self.is_getting_AP_data=False

    def register(self, instance):
        self.main_layout.clear_widgets()
        self.main_layout.add_widget(self.login_layout)

    def submit_register(self, instance):
        self.login = self.login_input.text
        self.password = self.password_input.text

        login = hashlib.sha256(self.login.encode()).hexdigest()
        password = hashlib.sha256(self.password.encode()).hexdigest()


        try:
            id_req = requests.get(f"http://127.0.0.1:8000/register/{login}/{password}")
            if id_req.status_code==200:
                id = id_req.json()["id"]
                self.id = id
                print(id)
        except:
            print("Something went wrong, please try again later")
        self.create_main_layout()

        self.main_layout.clear_widgets()
        self.main_layout.add_widget(self.layout)

    def cancel_register(self, instance):
        self.main_layout.clear_widgets()
        self.main_layout.add_widget(self.layout)

if __name__ == "__main__":
    main_app().run()