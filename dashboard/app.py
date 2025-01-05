import random
import time
import threading
import requests
from flask import Flask, render_template, jsonify, request
from pymongo import MongoClient

app = Flask(__name__)

# Подключение к MongoDB
mongo_client = MongoClient("mongodb://admin:root@mongo:27017/")
db = mongo_client["main_db"]
clients_collection = db["clients"]

# Переменные для управления генерацией трафика
traffic_generation_active = False
traffic_rate = 1  # Запросов в секунду
stop_event = threading.Event()


def get_random_client_id():
    """
    Получить случайный ID клиента из базы данных.
    """
    try:
        clients = list(clients_collection.find({}, {"id": 1}))
        if clients:
            return random.choice(clients)["id"]  # Извлекаем строковый ID
        else:
            print("База данных пуста. ID клиента отсутствует.")
            return None
    except Exception as e:
        print(f"Ошибка при получении данных из базы MongoDB: {e}")
        return None


def generate_traffic():
    endpoints = [
        ("POST", "/clients"),
        # ("PUT", "/clients/{id}"),
        # ("DELETE", "/clients/{id}"),
        ("GET", "/clients")
    ]

    while not stop_event.is_set():
        if traffic_generation_active:
            method, endpoint = random.choice(endpoints)

            # Если нужно заменить {id}, получить реальный ID из базы
            if "{id}" in endpoint:
                client_id = get_random_client_id()
                if client_id is None:
                    time.sleep(1)  # Если ID нет, подождать перед следующим запросом
                    continue
                endpoint = endpoint.replace("{id}", client_id)

            data = {
                "first_name": "John",
                "last_name": "Doe",
                "address": "123 Main St",
                "phone": "1234567890"
            }

            # Генерация запроса
            try:
                if method == "POST":
                    response = requests.post(f"http://gateway:8080{endpoint}", json=data)
                elif method == "PUT":
                    response = requests.put(f"http://gateway:8080{endpoint}", json=data)
                elif method == "DELETE":
                    response = requests.delete(f"http://gateway:8080{endpoint}")
                elif method == "GET":
                    response = requests.get(f"http://gateway:8080{endpoint}")

                print(f"{method} {endpoint} -> Status: {response.status_code}")
            except Exception as e:
                print(f"Error sending {method} {endpoint}: {e}")

        time.sleep(random.uniform(1 / traffic_rate, 2 / traffic_rate))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/traffic/start", methods=["POST"])
def start_traffic():
    global traffic_generation_active
    traffic_generation_active = True
    return jsonify({"message": "Traffic generation started"}), 200


@app.route("/traffic/stop", methods=["POST"])
def stop_traffic():
    global traffic_generation_active
    traffic_generation_active = False
    return jsonify({"message": "Traffic generation stopped"}), 200


@app.route("/traffic/set_rate", methods=["POST"])
def set_traffic_rate():
    global traffic_rate
    data = request.get_json()
    traffic_rate = max(1, data.get("rate", 1))
    return jsonify({"message": f"Traffic rate set to {traffic_rate} requests per second"}), 200


if __name__ == "__main__":
    # Запускаем поток генерации трафика
    threading.Thread(target=generate_traffic, daemon=True).start()
    app.run(host="0.0.0.0", port=8082)
