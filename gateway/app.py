import json
import grpc
import redis
import pika
import socket
from flask import Flask, jsonify, request
from prometheus_client import Counter, generate_latest
from proto import service_pb2, service_pb2_grpc

app = Flask(__name__)

redis_client = redis.Redis(host="redis", port=6379)

REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint'])


def send_to_rabbitmq(queue_name, grpc_message):
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
        channel = connection.channel()
        channel.queue_declare(queue=queue_name)
        channel.basic_publish(exchange='', routing_key=queue_name, body=grpc_message)
        connection.close()
    except Exception as e:
        print(f"Error sending to RabbitMQ: {e}")


def send_to_logstash(message):
    host = 'logstash'
    port = 5044
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            s.sendall(message.encode('utf-8'))
            print(f"Message sent to Logstash: {host}:{port}")
    except Exception as e:
        print(f"Error sending message to Logstash: {e}")


@app.route('/clients', methods=['POST'])
def create_client():
    REQUEST_COUNT.labels(method='POST', endpoint='/clients').inc()

    data = request.get_json()
    grpc_message = service_pb2.CreateClientRequest(
        first_name=data.get('first_name'),
        last_name=data.get('last_name'),
        address=data.get('address'),
        phone=data.get('phone')
    ).SerializeToString()

    send_to_rabbitmq('create_client', grpc_message)

    logstash_message = json.dumps({
        "event": "create_client",
        "data": data
    })
    send_to_logstash(logstash_message)

    redis_client.delete('clients')

    return jsonify({"message": "Client creation request processed"}), 202


@app.route('/clients/<string:id>', methods=['PUT'])
def update_client(id):
    REQUEST_COUNT.labels(method='PUT', endpoint='/clients').inc()

    data = request.get_json()
    grpc_message = service_pb2.UpdateClientRequest(
        id=id,
        first_name=data.get('first_name'),
        last_name=data.get('last_name'),
        address=data.get('address'),
        phone=data.get('phone')
    ).SerializeToString()

    send_to_rabbitmq('update_client', grpc_message)

    logstash_message = json.dumps({
        "event": "update_client",
        "id": id,
        "data": data
    })
    send_to_logstash(logstash_message)

    redis_client.delete('clients')

    return jsonify({"message": f"Client {id} update request processed"}), 202


@app.route('/clients/<string:id>', methods=['DELETE'])
def delete_client(id):
    REQUEST_COUNT.labels(method='DELETE', endpoint='/clients').inc()

    grpc_message = service_pb2.DeleteClientRequest(id=id).SerializeToString()

    send_to_rabbitmq('delete_client', grpc_message)

    logstash_message = json.dumps({
        "event": "delete_client",
        "id": id
    })
    send_to_logstash(logstash_message)

    redis_client.delete('clients')

    return jsonify({"message": f"Client {id} deletion request processed"}), 202


@app.route('/clients', methods=['GET'])
def get_clients():
    REQUEST_COUNT.labels(method='GET', endpoint='/clients').inc()

    cached = redis_client.get('clients')
    if cached:
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


@app.route('/metrics', methods=['GET'])
def metrics():
    return generate_latest(), 200, {'Content-Type': 'text/plain'}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
