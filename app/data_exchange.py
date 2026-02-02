from flask import Flask, jsonify, request
import os 
import signal
import sqlite3
import json
app = Flask(__name__)
wifi = [{"ssid": "...", "password": "...", "IP": "..."}]

connection = sqlite3.connect("./db.db", check_same_thread=False)
cursor = connection.cursor()
cursor.execute("SELECT * FROM AP_DATA")
data = list(cursor.fetchall()[0])
wifi[0]["ssid"] = data[1]
wifi[0]["password"] = data[2]
wifi[0]["IP"] = data[0]
data_fetched = False

@app.route('/')
def exchange_data():
    global data_fetched

    return json.dumps(wifi,ensure_ascii=False)

@app.post('/IP')
def get_IP():
    global data_fetched
    text = request.json
    IP = text["IP"]
    print(IP)
    cursor.execute("UPDATE AP_DATA SET ESP_IP = ? WHERE rowid=1", (IP,))
    connection.commit()
    connection.close()
    data_fetched = True
    return "thanks for IP"



@app.post('/end')
def shutdown():
    if data_fetched:
        os.kill(os.getpid(), signal.SIGTERM)
    return "Still active"
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)