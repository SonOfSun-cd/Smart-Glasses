from kivy.config import Config

Config.set('graphics', 'width', '360')
Config.set('graphics', 'height', '620')
# Config.set('graphics', 'resizable', False)

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.utils import platform

import time
import requests
from requests.exceptions import HTTPError, RequestException
import threading
import socket
import json
import hashlib

if platform == "android":
    from jnius import autoclass


class main_app(App):
    def _build_frame_pool(self, obj, cords, centers, depth_dict):
        frame_pool = {}
        for i in range(len(obj)):
            frame_pool[i] = {
                "index": i,
                "class": obj[i],
                "cords": cords[i],
                "center": centers[i],
                "depth": depth_dict.get(f"{i}"),
                "track_id": None,
            }
        return frame_pool

    def _push_frame_pool(self, frame_pool, obj, cords, centers, depth_dict):
        frame_id = self.next_frame_id
        self.next_frame_id += 1

        snapshot = {
            "frame_id": frame_id,
            "frame_pool": {i: frame_pool[i].copy() for i in frame_pool},
            "objects": obj[:],
            "cords": [cord[:] for cord in cords],
            "centers": [center[:] for center in centers],
            "depth_dict": depth_dict.copy(),
        }
        self.frame_history[frame_id] = snapshot

        if len(self.frame_history) > self.max_frame_history:
            oldest_frame_id = next(iter(self.frame_history))
            del self.frame_history[oldest_frame_id]

        return frame_id

    def _normalize_mac(self, mac):
        return mac.strip().lower().replace("-", ":") if mac else ""

    def _set_status(self, text):
        if hasattr(self, "label") and self.label is not None:
            self.label.text = str(text)

    def _start_discovery_listener(self):
        if self.discovery_thread is not None and self.discovery_thread.is_alive():
            return

        self.discovery_running = True
        self.discovery_thread = threading.Thread(target=self._listen_for_device_announces, daemon=True)
        self.discovery_thread.start()

    def _listen_for_device_announces(self):
        try:
            self.discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.discovery_socket.bind(("0.0.0.0", self.discovery_port))
            self.discovery_socket.settimeout(1.0)
        except Exception as error:
            self.discovery_socket = None
            self._set_status(f"Не получилось запустить UDP discovery: {error}")
            return

        while self.discovery_running:
            try:
                payload, addr = self.discovery_socket.recvfrom(512)
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception:
                continue

            try:
                message = payload.decode("utf-8").strip()
            except UnicodeDecodeError:
                continue

            parts = message.split("|")
            if len(parts) != 5 or parts[0] != "SMART_GLASSES":
                continue

            _, device_name, device_mac, device_ip, device_port = parts
            normalized_mac = self._normalize_mac(device_mac)
            if not normalized_mac:
                continue

            self.discovered_hosts[normalized_mac] = {
                "name": device_name,
                "ip": device_ip.strip() or addr[0],
                "port": device_port.strip(),
                "last_seen": time.time(),
            }

        if self.discovery_socket is not None:
            try:
                self.discovery_socket.close()
            except OSError:
                pass
            self.discovery_socket = None

    def _create_android_tts(self, dt):
        try:
            self.android_tts_class = autoclass("android.speech.tts.TextToSpeech")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Locale = autoclass("java.util.Locale")

            self.tts_locale = Locale("ru", "RU")
            self.tts_listener = None
            self.tts_engine = self.android_tts_class(PythonActivity.mActivity, None)
            self.voice_backend = "android_tts"
            self.voice_backend_ready = True
            self.voice_backend_initializing = False
            self.voice_init_started_at = time.time()
            self._set_status("Инициализирую Android TTS...")
        except Exception as error:
            self.voice_backend = "console"
            self.voice_backend_ready = True
            self.voice_backend_initializing = False
            self.voice_init_event.set()
            self._set_status(f"TTS fallback в консоль: {error}")

    def _ensure_android_tts_ready(self):
        if self.voice_backend != "android_tts" or self.tts_engine is None:
            return False

        if self.tts_ready:
            return True

        if time.time() - self.voice_init_started_at < self.voice_warmup_seconds:
            return False

        try:
            if self.tts_locale is not None:
                language_status = self.tts_engine.setLanguage(self.tts_locale)
                if language_status == self.android_tts_class.LANG_MISSING_DATA:
                    self._set_status("В Android TTS отсутствуют данные русского языка")
                    return False
                if language_status == self.android_tts_class.LANG_NOT_SUPPORTED:
                    self._set_status("Android TTS не поддерживает русский язык")
                    return False
            self.tts_ready = True
            self.voice_init_event.set()
            self._set_status("Android TTS готов")
            return True
        except Exception as error:
            self._set_status(f"Ошибка подготовки Android TTS: {error}")
            return False

    def _init_voice_backend(self):
        if self.voice_backend_ready:
            return

        if platform != "android":
            self.voice_backend = "console"
            self.voice_backend_ready = True
            self._set_status("Озвучка в режиме консоли")
            return

        if self.voice_backend_initializing:
            return

        self.voice_backend_initializing = True
        self.voice_init_event.clear()
        Clock.schedule_once(self._create_android_tts, 0)

    def _voice_is_busy(self):
        if self.voice_backend == "android_tts" and self.tts_engine is not None and self.tts_ready:
            return bool(self.tts_engine.isSpeaking())
        return time.time() < self.console_voice_busy_until

    def _stop_voice_output(self, reason):
        if self.voice_backend == "android_tts" and self.tts_engine is not None and self.tts_ready:
            self._set_status(f"Останавливаю текущую озвучку: {reason}")
            self.tts_engine.stop()
            return

        if self.console_voice_busy_until > time.time():
            print(f"[VOICE/interrupt/{reason}] текущая речь остановлена")
        self.console_voice_busy_until = 0

    def _speak_text(self, text, rate, reason):
        self._init_voice_backend()

        if self.voice_backend == "android_tts":
            if not self._ensure_android_tts_ready():
                self.pending_tts = (text, rate, reason)
                self._set_status(f"TTS ещё не готов, откладываю {reason}")
                return False

            speech_rate = 1.2 if rate >= 300 else 1.0
            preview = text[:60] + ("..." if len(text) > 60 else "")

            try:
                self.tts_engine.setSpeechRate(speech_rate)
                utterance_id = str(int(time.time() * 1000))
                try:
                    self.tts_engine.speak(text, self.android_tts_class.QUEUE_FLUSH, None, utterance_id)
                except TypeError:
                    self.tts_engine.speak(text, self.android_tts_class.QUEUE_FLUSH, None)
                self._set_status(f"Озвучиваю {reason}: {preview}")
                return True
            except Exception as error:
                self._set_status(f"Ошибка Android TTS: {error}")
                return False

        print(f"[VOICE/{reason}] rate={rate} text={text}")
        self._set_status(f"[VOICE/{reason}] {text[:60]}")
        self.console_voice_busy_until = time.time() + min(max(len(text) / 35, 1.0), 4.0)
        return True

    def _read_android_arp_table(self):
        try:
            from jnius import autoclass

            Runtime = autoclass("java.lang.Runtime")
            InputStreamReader = autoclass("java.io.InputStreamReader")
            BufferedReader = autoclass("java.io.BufferedReader")

            for command in ("ip neigh", "cat /proc/net/arp"):
                process = Runtime.getRuntime().exec(command)
                reader = BufferedReader(InputStreamReader(process.getInputStream()))
                arp_lines = []

                while True:
                    line = reader.readLine()
                    if line is None:
                        break
                    arp_lines.append(str(line))

                reader.close()
                process.waitFor()
                if arp_lines:
                    return arp_lines

            return []
        except Exception as error:
            self._set_status(f"Ошибка чтения ARP: {error}")
            return []

    def _resolve_esp32_ip(self, target_mac=None, default_ip=None, target_name="ESP32", wait_for_announce=True):
        if default_ip is None:
            default_ip = self.default_esp32_ip

        target_mac = self._normalize_mac(target_mac)
        if not target_mac:
            self._set_status(f"MAC {target_name} не задан, использую запасной IP")
            return default_ip

        self._start_discovery_listener()

        known_host = self.discovered_hosts.get(target_mac)
        if known_host is not None:
            self._set_status(f"{target_name} найден через UDP discovery: {known_host['ip']}")
            return known_host["ip"]

        if wait_for_announce:
            self._set_status(f"Жду UDP announce от {target_name}...")
            deadline = time.time() + self.discovery_wait_seconds
            while time.time() < deadline:
                known_host = self.discovered_hosts.get(target_mac)
                if known_host is not None:
                    self._set_status(f"{target_name} найден через UDP discovery: {known_host['ip']}")
                    return known_host["ip"]
                time.sleep(0.2)

        if platform == "android":
            arp_lines = self._read_android_arp_table()
            for line in arp_lines:
                normalized_line = line.lower()
                if target_mac in normalized_line:
                    parts = line.split()
                    if parts:
                        self._set_status(f"{target_name} найден в ARP: {parts[0]}")
                        return parts[0]

        self._set_status(f"{target_name} не найден, использую запасной IP")
        return default_ip

    def _build_scene_signature(self, groups, obj, filters, positions):
        signature = []

        for group in groups:
            position = ""
            for pos in positions:
                if group[1][0] <= positions[pos][1] and group[1][0] >= positions[pos][0]:
                    position = pos
                    break

            objects_in_group = [obj[j] for j in group[2:]]
            counts = tuple((filter_name, objects_in_group.count(filter_name)) for filter_name in filters if objects_in_group.count(filter_name) != 0)
            depth_bucket = round(group[0], 1)
            signature.append((position, depth_bucket, counts))

        return tuple(sorted(signature))

    def _count_important_objects(self, groups, obj, filters, limit=3):
        important_filters = filters[:limit]
        count = 0

        for group in groups:
            for index in group[2:]:
                if obj[index] in important_filters:
                    count += 1

        return count

    def _should_enqueue_scene(self, scene_signature, important_count):
        if not scene_signature:
            return False

        if self.last_scene_signature is None:
            self.last_scene_signature = scene_signature
            self.last_important_count = important_count
            return True

        important_delta = important_count - self.last_important_count
        changed = scene_signature != self.last_scene_signature

        if changed or important_delta >= 1:
            self.last_scene_signature = scene_signature
            self.last_important_count = important_count
            return True

        return False

    def _match_frame_pool(self, frame_pool, max_movement):
        matches = {}
        used_tracks = set()
        candidates = []

        for det_index, detection in frame_pool.items():
            for track_id, track in self.object_tracks.items():
                last_detection = track["history"][-1]
                if detection["class"] != track["class"]:
                    continue

                depth_now = detection["depth"]
                depth_prev = last_detection.get("depth")
                if depth_now is not None and depth_prev is not None and abs(depth_now - depth_prev) > 0.7:
                    continue

                if len(track["history"]) >= 2:
                    prev_center = track["history"][-2]["center"]
                    last_center = last_detection["center"]
                    predicted_center = [
                        last_center[0] + (last_center[0] - prev_center[0]),
                        last_center[1] + (last_center[1] - prev_center[1]),
                    ]
                else:
                    predicted_center = last_detection["center"]

                dx = detection["center"][0] - predicted_center[0]
                dy = detection["center"][1] - predicted_center[1]
                distance = (dx**2 + dy**2) ** 0.5
                track_depth = depth_now if depth_now is not None else depth_prev
                allowed_distance = max_movement * (track_depth if track_depth is not None else 1)

                if distance <= allowed_distance * 1.4:
                    depth_penalty = 0 if depth_now is None or depth_prev is None else abs(depth_now - depth_prev) * 50
                    candidates.append((distance + depth_penalty, det_index, track_id))

        for _, det_index, track_id in sorted(candidates, key=lambda x: x[0]):
            if det_index in matches or track_id in used_tracks:
                continue
            matches[det_index] = track_id
            used_tracks.add(track_id)

        return matches

    def _is_sharp_motion(self, track, detection, max_movement):
        if len(track["history"]) < 1:
            return False

        last_detection = track["history"][-1]
        depth_now = detection.get("depth")
        depth_prev = last_detection.get("depth")
        scale = 1
        if depth_now is not None and depth_prev is not None:
            scale = max((depth_now + depth_prev) / 2, 0.3)
        threshold = max_movement * scale

        move_vector = [
            detection["center"][0] - last_detection["center"][0],
            detection["center"][1] - last_detection["center"][1],
        ]
        move_distance = (move_vector[0] ** 2 + move_vector[1] ** 2) ** 0.5

        if len(track["history"]) < 2:
            return move_distance >= threshold

        prev_detection = track["history"][-2]
        prev_vector = [
            last_detection["center"][0] - prev_detection["center"][0],
            last_detection["center"][1] - prev_detection["center"][1],
        ]
        prev_distance = (prev_vector[0] ** 2 + prev_vector[1] ** 2) ** 0.5

        direction_change = 1
        if move_distance > 0 and prev_distance > 0:
            dot = move_vector[0] * prev_vector[0] + move_vector[1] * prev_vector[1]
            direction_change = dot / (move_distance * prev_distance)

        return move_distance >= threshold and (
            prev_distance < threshold * 0.6
            or direction_change < 0.4
            or move_distance > prev_distance * 1.7
        )
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
        
        max_width = 1920 # Максимальная ширина изображения в пикселях
        max_dist = 500 # Максимальная дистанция группировки в пикселях
        max_movement = 150 # Максимальный сдвиг объекта перед предупреждением о резком движении

        positions = {"Слева": [0, 0.25*max_width/2], "Чуть левее": [0.25*max_width/2, 0.75*max_width/2], "Спереди": [0.75*max_width/2, 1.25*max_width/2], "Чуть правее": [1.25*max_width/2, 1.75*max_width/2], "Справа": [1.75*max_width/2, max_width]}

        obj = answer["objects"]
        cords = answer["cords"]
        centers = [[cords[i][0]+(cords[i][2]-cords[i][0])/2, cords[i][1]+(cords[i][3]-cords[i][1])/2] for i in range(len(obj))]
        groups_depth=[]
        movement_group = []
        depth_dict = {}
    

        # Алгоритм группировки объектов по глубине на изображении
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
                        depth_dict.update({f"{i}": groups_depth[j][0]})
                        match=True
                        break
                    
            if groups_depth==[] or not match:
                distance = des_l/length
                if abs(des_l/length-des_h/height)>0.5:
                    distance = distance if length/height > des_l/des_h else des_h/height
                depth_dict.update({f"{i}": distance})
                groups_depth.append([distance, i]) 
        print(obj)
        print(groups_depth)
        #print(depth_dict)

        # Алгоритм поиска аномальных движений и их фиксации
        alert_group = []
        frame_pool = self._build_frame_pool(obj, cords, centers, depth_dict)
        matches = self._match_frame_pool(frame_pool, max_movement)
        print("пул создан")

        for det_index, detection in frame_pool.items():
            track_id = matches.get(det_index)
            if track_id is None:
                track_id = self.next_track_id
                self.next_track_id += 1
                self.object_tracks[track_id] = {"class": detection["class"], "history": []}

            detection["track_id"] = track_id
            track = self.object_tracks[track_id]

            if detection["class"] == "person" and self._is_sharp_motion(track, detection, max_movement):
                alert_group.append(det_index)
                position = ""
                for pos in positions:
                    if centers[det_index][0] <= positions[pos][1] and centers[det_index][0] >= positions[pos][0]:
                        position = pos
                        break
                warning_text = f"!Внимание, {position} от вас резкое движение объекта {obj[det_index]}"
                now = time.time()
                last_warning_time = self.track_warning_times.get(track_id, 0)
                if now - last_warning_time >= self.warning_cooldown_seconds and warning_text not in self.queue:
                    if len(self.queue) >= self.max_queue_len:
                        self.queue = self.queue[1:]
                    self.queue.append(warning_text)
                    self.track_warning_times[track_id] = now

            track["history"].append({"center": detection["center"], "depth": detection["depth"], "index": det_index})
            track["history"] = track["history"][-3:]

        active_track_ids = {frame_pool[i]["track_id"] for i in frame_pool}
        self.object_tracks = {track_id: self.object_tracks[track_id] for track_id in active_track_ids}
        self.track_warning_times = {track_id: self.track_warning_times[track_id] for track_id in self.track_warning_times if track_id in active_track_ids}
        current_frame_id = self._push_frame_pool(frame_pool, obj, cords, centers, depth_dict)
        print("отделение завершено")
        # Алгоритм отделения этих групп на горизонтально близкие группы и их фильтрация
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
        print("близость найдена")
        # Фильтрация групп относительно фильтра важности объектов
        for i in filters:
            for j in groups.copy():
                for k in j[2:]:
                    if obj[k]==i:
                        groups.remove(j)
                        groups.append(j)
        print("группы сформированы")
        print(groups)
        print(alert_group)
        print("_______________________________")
        self.centers_stack = centers
        self.objects_stack = obj
        self.Y_groups_stack = depth_dict
        self.current_frame_id = current_frame_id

        # Формирование текста, описывающего кадр
        scene_signature = self._build_scene_signature(groups, obj, filters, positions)
        important_count = self._count_important_objects(groups, obj, filters)
        text = ""
        for i in groups:
            local_text = ""
            position = ""
            for pos in positions:
                if i[1][0]<=positions[pos][1] and i[1][0]>=positions[pos][0]:
                    position = pos
                    break
            objects_in_group = [obj[j] for j in i[2:]]
            local_text += position + " на расстоянии " + str(i[0]) + " метров от вас находится группа из " + ', '.join([str(objects_in_group.count(j)) + " " + j for j in filters if objects_in_group.count(j) != 0])
            text+=f"{local_text}; \n"
        if self._should_enqueue_scene(scene_signature, important_count):
            if text not in self.queue:
                if len(self.queue) >= self.max_queue_len:
                    self.queue = self.queue[1:]
                self.queue.append(text)
        print(text)
        print(self.queue)

        return
    
    def Voice_text(self):
        while True:
            if self.pending_tts is not None and self._ensure_android_tts_ready():
                text, rate, reason = self.pending_tts
                self.pending_tts = None
                self._speak_text(text, rate, reason)

            if self.queue:
                dangers = [text for text in self.queue if "!" in text]
                if dangers:
                    text = dangers[-1]
                    self.queue.remove(text)
                    self._set_status("Очередь озвучки: беру warning")
                    if self._voice_is_busy():
                        self._stop_voice_output("warning")
                    self._speak_text(text, 300, "warning")
                elif not self._voice_is_busy():
                    text = self.queue[-1]
                    self.queue = self.queue[1:]
                    self._set_status("Очередь озвучки: беру описание сцены")
                    self._speak_text(text, 230, "scene")
            time.sleep(0.05)


    def Server_start(self):
        if hasattr(self, "Server_IP_Input") and self.Server_IP_Input is not None:
            debug_server_ip = self.Server_IP_Input.text.strip()
            if debug_server_ip:
                self.default_server_ip = debug_server_ip

        IP = self._resolve_esp32_ip(self.mac, self.default_esp32_ip, "ESP32")
        server_ip = self._resolve_esp32_ip(self.server_mac, self.default_server_ip, "server", False)

        server_url = f"http://{server_ip}:8000"
        
        self._set_status(f"Подключаюсь к ESP32 по IP {IP}")
        i=0
        session = requests.Session()
        session.headers.update({"Connection": "keep-alive"})

        # Начало сессии с главным сервером

        login = self.login
        password = hashlib.sha256(self.password.encode()).hexdigest()
        try:
            self._set_status(f"Подключаюсь к серверу по IP {server_ip}")
            session_start = requests.get(f"{server_url}/start/{login}/{password}")
            session_start.raise_for_status()

            print(session_start.json())
            self.id = session_start.json()["id"]
        except HTTPError as error:
            self.label.text = f"Ошибка при установлении соединения: {error.response.text}"
            return
        except RequestException as error:
            self.label.text = f"Не получилось подключиться к серверу {server_ip}: {error}"
            return
        if self.voice_thread is None or not self.voice_thread.is_alive():
            self.voice_thread = threading.Thread(target=self.Voice_text, daemon=True)
            self.voice_thread.start()
        while self.started_server:
            try:
                img = session.get(f"http://{IP}:3000/img")
                if img.status_code == 200:
                    files = {"img": img.content}
                    try:
                        answer = session.post(f"{server_url}/session/{self.id}", files=files)
                        answer.raise_for_status()

                        if answer.json()["answer"]!="...":
                            self.AI_analyse(answer.json()["answer"])
                    except HTTPError as error:
                        self.label.text = f"Ошибка при отправке изображения: {error.response.text}"
                        return
                    i+=1
            except:
                self.label.text = "Не получается установить соединение. Повторяю попытку..."
                IP = self._resolve_esp32_ip(self.mac, self.default_esp32_ip, "ESP32")
                time.sleep(1)
                continue
            # files = {"img": open(f"./images/img_{i}.jpg", "rb")}
            # answer = requests.post(f"http://127.0.0.1:8000/session/{self.id}", files=files)
            # print(answer.json())
            # i+=1
            #print(answer.json())
        #server = subprocess.Popen(["py","server.py"], shell=True)
        #ai_analyse = subprocess.Popen(["py", "AI.py"], shell=True)
        self.label.text = "..."
        self.object_tracks = {}
        self.next_track_id = 1
        self.frame_history = {}
        self.max_frame_history = 50
        self.next_frame_id = 1
        self.current_frame_id = None
        self.last_scene_signature = None
        self.last_important_count = 0
        self.track_warning_times = {}
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

        self.centers_stack = []
        self.objects_stack= []
        self.Y_groups_stack = {}
        # Запасной IP ESP32 для ПК и для Android fallback, если discovery не помог.
        self.default_esp32_ip = "192.168.137.34"
        # Запасной IP и MAC ноутбука/сервера до появления фиксированного домена.
        self.default_server_ip = "127.0.0.1"
        self.server_mac = "56-EB-3D-2D-FD-4D"
        # UDP discovery: кэш найденных устройств и поток, слушающий announce-пакеты.
        self.discovery_port = 4210
        self.discovery_wait_seconds = 6
        self.discovered_hosts = {}
        self.discovery_thread = None
        self.discovery_running = False
        self.discovery_socket = None
        # Активные треки объектов между кадрами и счётчик новых track_id.
        self.object_tracks = {}
        self.next_track_id = 1
        # Сырые frame_pool последних кадров и счётчик новых frame_id.
        self.frame_history = {}
        self.max_frame_history = 50
        self.next_frame_id = 1
        self.current_frame_id = None
        # Очередь озвучки и её максимальный размер.
        self.queue = []
        self.max_queue_len = 15
        # Backend озвучки: Android TTS в проде и консольная симуляция на ПК.
        self.voice_thread = None
        self.voice_backend = None
        self.voice_backend_ready = False
        self.voice_backend_initializing = False
        self.voice_init_started_at = 0
        self.voice_warmup_seconds = 1.0
        self.voice_init_event = threading.Event()
        self.tts_engine = None
        self.tts_listener = None
        self.tts_ready = False
        self.tts_locale = None
        self.android_tts_class = None
        self.pending_tts = None
        self.console_voice_busy_until = 0
        # Последняя озвученная сигнатура сцены для отсечения одинаковых описаний.
        self.last_scene_signature = None
        self.last_important_count = 0
        # Время последних варнингов по track_id, чтобы не спамить одним объектом.
        self.track_warning_times = {}
        self.warning_cooldown_seconds = 2.5

        self.check = "Hello!"
        self.is_getting_AP_data = False
        self.sent_AP_data = False
        self.started_server = False
        self.labels = {"start": "Устанавливаю полное соединение с очками", "stop": "Выключаю соединение", "deny": "Сначала вам необходимо передать данные о точке доступа"}
        self.img = b""

        self.colors = {"green": (0,1,0,1), "red": (1,0,0,1), "grey": (1,1,1,1)}

        db = self.load_db()
        # name = socket.gethostname()
        IP = "10.243.62.9"
        # print(IP, name)
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
        Clock.schedule_once(lambda dt: self._init_voice_backend(), 0)
        return self.main_layout
    
    def create_main_layout(self):
        self.layout = BoxLayout(orientation="vertical")

        # Кнопка регистрации
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

        server_ip_layout = BoxLayout(orientation="horizontal")
        self.Server_IP_Input = TextInput(text=self.default_server_ip, halign="center", multiline=False)
        server_ip_layout.add_widget(Label(text="IP сервера (Debug): ", font_size="16sp"))
        server_ip_layout.add_widget(self.Server_IP_Input)
        big_layout.add_widget(server_ip_layout)

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

        self.login_layout_label = Label(text="Регистрация аккаунта / вход в аккаунт", font_size="20sp")
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
        self.discovery_running = False
        if self.discovery_socket is not None:
            try:
                self.discovery_socket.close()
            except OSError:
                pass
            self.discovery_socket = None

        if self.voice_backend == "android_tts" and self.tts_engine is not None:
            try:
                self.tts_engine.stop()
                self.tts_engine.shutdown()
            except Exception:
                pass

        db = self.load_db()
        db["AP_DATA"]["SSID"] = self.SSID_Input.text
        db["AP_DATA"]["PASSWORD"] = self.PSWRD_Input.text
        db["AP_DATA"]["EXCHANGED"] = bool(self.sent_AP_data)
        db["AP_DATA"]["MAC"] = self.mac
        db["USER_DATA"]["login"] = self.login
        db["USER_DATA"]["password"] = self.password
        self.save_db(db)
        print("Commiting all changes")

    # Функции для кнопок

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

        login = self.login
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

