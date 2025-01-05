import sys
import json
import grpc
import redis
import pika
import socket
from flask import Flask, jsonify, request
from prometheus_client import Counter, generate_latest
from proto import service_pb2, service_pb2_grpc

app = Flask(__name__)

# Подключение к Redis для кеширования
redis_client = redis.Redis(host="redis", port=6379)

# Метрики для Prometheus
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint'])


# Функция для отправки сообщений в RabbitMQ
def send_to_rabbitmq(queue_name, message):
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
        channel = connection.channel()
        channel.queue_declare(queue=queue_name)
        channel.basic_publish(exchange='', routing_key=queue_name, body=message)
        connection.close()
    except Exception as e:
        print(f"Error sending to RabbitMQ: {e}")


# Функция для отправки сообщений в Logstash
def send_to_logstash(message):
    host = 'logstash'  # Имя контейнера Logstash
    port = 5044
    try:
        # Создаём TCP-сокет и подключаемся к Logstash
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            s.sendall(message.encode('utf-8'))
            print(f"Message sent to Logstash: {host}:{port}")
    except Exception as e:
        # Обработка ошибок
        print(f"Error sending message to Logstash: {e}")


# Маршрут для создания клиента (POST)
@app.route('/clients', methods=['POST'])
def create_client():
    REQUEST_COUNT.labels(method='POST', endpoint='/clients').inc()  # Добавляем инкремент для POST

    data = request.get_json()
    message = json.dumps(data)

    # Отправляем в RabbitMQ для асинхронной обработки
    send_to_rabbitmq('create_client', message)

    # Формируем сообщение для отправки в Logstash
    logstash_message = json.dumps({
        "event": "create_client",
        "data": data
    })
    send_to_logstash(logstash_message)

    # Очищаем кеш клиентов, чтобы следующий GET-запрос получил актуальные данные
    redis_client.delete('clients')

    return jsonify({"message": "Client creation request processed"}), 202


# Маршрут для обновления клиента (PUT)
@app.route('/clients/<string:id>', methods=['PUT'])
def update_client(id):
    REQUEST_COUNT.labels(method='PUT', endpoint='/clients').inc()  # Добавляем инкремент для PUT

    data = request.get_json()
    data['id'] = id
    message = json.dumps(data)

    # Отправляем в RabbitMQ для асинхронной обработки
    send_to_rabbitmq('update_client', message)

    # Формируем сообщение для отправки в Logstash
    logstash_message = json.dumps({
        "event": "update_client",
        "id": id,
        "data": data
    })
    send_to_logstash(logstash_message)

    # Очищаем кеш клиентов, чтобы следующий GET-запрос получил актуальные данные
    redis_client.delete('clients')

    return jsonify({"message": f"Client {id} update request processed"}), 202


# Маршрут для удаления клиента (DELETE)
@app.route('/clients/<string:id>', methods=['DELETE'])
def delete_client(id):
    REQUEST_COUNT.labels(method='DELETE', endpoint='/clients').inc()  # Добавляем инкремент для DELETE

    # Подготавливаем сообщение для отправки в RabbitMQ для асинхронной обработки
    message = json.dumps({"id": id})

    # Отправляем в RabbitMQ
    send_to_rabbitmq('delete_client', message)

    # Формируем сообщение для отправки в Logstash
    logstash_message = json.dumps({
        "event": "delete_client",
        "id": id
    })
    send_to_logstash(logstash_message)

    # Очищаем кеш клиентов, чтобы следующий GET-запрос получил актуальные данные
    redis_client.delete('clients')

    return jsonify({"message": f"Client {id} deletion request processed"}), 202


# Маршрут для получения данных о клиентах (GET)
@app.route('/clients', methods=['GET'])
def get_clients():
    REQUEST_COUNT.labels(method='GET', endpoint='/clients').inc()  # Добавляем инкремент для GET

    cached = redis_client.get('clients')
    if cached:
        # Логируем получение данных из кеша
        print('Returning cached clients data')
        return jsonify({"data": json.loads(cached.decode('utf-8'))}), 200

    try:
        with grpc.insecure_channel("domain:50051") as channel:
            stub = service_pb2_grpc.ClientServiceStub(channel)
            response = stub.GetClients(service_pb2.Empty())
            clients = [
                {"id": c.id, "first_name": c.first_name, "last_name": c.last_name, "address": c.address,
                 "phone": c.phone}
                for c in response.clients
            ]
            redis_client.setex('clients', 60, json.dumps(clients))

            # Формируем сообщение для отправки в Logstash
            logstash_message = json.dumps({
                "event": "get_clients",
                "status": "fetched_from_service",
                "data": clients
            })
            send_to_logstash(logstash_message)

            return jsonify({"data": clients}), 200
    except grpc.RpcError as e:
        print(f"gRPC error: {e}")
        return jsonify({"error": "Failed to fetch clients from domain"}), 500


# Маршрут для метрик Prometheus
@app.route('/metrics', methods=['GET'])
def metrics():
    return generate_latest(), 200, {'Content-Type': 'text/plain'}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
