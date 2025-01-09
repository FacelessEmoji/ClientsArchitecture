import grpc
import pika
import json
from concurrent import futures
from proto import service_pb2, service_pb2_grpc
from pymongo import MongoClient
from bson.objectid import ObjectId
import time

mongo_client = MongoClient("mongodb://admin:root@mongo:27017/")
db = mongo_client["main_db"]
clients_collection = db["clients"]

class ClientService(service_pb2_grpc.ClientServiceServicer):
    def GetClients(self, request, context):
        try:
            clients = clients_collection.find()
            response_clients = [
                service_pb2.Client(
                    id=str(client["_id"]),
                    first_name=client.get("first_name", ""),
                    last_name=client.get("last_name", ""),
                    address=client.get("address", ""),
                    phone=client.get("phone", "")
                )
                for client in clients
            ]
            return service_pb2.ClientsResponse(clients=response_clients)
        except Exception as e:
            context.set_details(f"Error fetching clients: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            return service_pb2.ClientsResponse()

    def create_client_from_message(self, grpc_message):
        try:
            request = service_pb2.CreateClientRequest()
            request.ParseFromString(grpc_message)

            client_data = {
                "first_name": request.first_name,
                "last_name": request.last_name,
                "address": request.address,
                "phone": request.phone
            }
            result = clients_collection.insert_one(client_data)
            print(f"Client created: {result.inserted_id}")
        except Exception as e:
            print(f"Error creating client: {e}")

    def update_client_from_message(self, grpc_message):
        try:
            request = service_pb2.UpdateClientRequest()
            request.ParseFromString(grpc_message)

            client_id = request.id
            update_data = {
                "first_name": request.first_name,
                "last_name": request.last_name,
                "address": request.address,
                "phone": request.phone
            }
            clients_collection.update_one({"_id": ObjectId(client_id)}, {"$set": update_data})
            print(f"Client updated: {client_id}")
        except Exception as e:
            print(f"Error updating client: {e}")

    def delete_client_from_message(self, grpc_message):
        try:
            request = service_pb2.DeleteClientRequest()
            request.ParseFromString(grpc_message)

            client_id = request.id
            clients_collection.delete_one({"_id": ObjectId(client_id)})
            print(f"Client deleted: {client_id}")
        except Exception as e:
            print(f"Error deleting client: {e}")


def rabbitmq_consumer():
    max_retries = 10
    retry_interval = 5
    attempt = 0

    while attempt < max_retries:
        try:
            parameters = pika.ConnectionParameters(
                host='rabbitmq',
                port=5672,
                virtual_host='/',
                credentials=pika.PlainCredentials('guest', 'guest'),
                socket_timeout=20
            )

            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            channel.queue_declare(queue='create_client')
            channel.queue_declare(queue='update_client')
            channel.queue_declare(queue='delete_client')

            def callback_create_client(ch, method, properties, body):
                print("Received Create Client message")
                try:
                    ClientService().create_client_from_message(body)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    print(f"Error processing Create Client message: {e}")
                    ch.basic_nack(delivery_tag=method.delivery_tag)

            def callback_update_client(ch, method, properties, body):
                print("Received Update Client message")
                try:
                    ClientService().update_client_from_message(body)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    print(f"Error processing Update Client message: {e}")
                    ch.basic_nack(delivery_tag=method.delivery_tag)

            def callback_delete_client(ch, method, properties, body):
                print("Received Delete Client message")
                try:
                    ClientService().delete_client_from_message(body)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    print(f"Error processing Delete Client message: {e}")
                    ch.basic_nack(delivery_tag=method.delivery_tag)

            channel.basic_consume(queue='create_client', on_message_callback=callback_create_client)
            channel.basic_consume(queue='update_client', on_message_callback=callback_update_client)
            channel.basic_consume(queue='delete_client', on_message_callback=callback_delete_client)

            print('Waiting for messages...')
            channel.start_consuming()
            break

        except pika.exceptions.AMQPConnectionError as e:
            print(f"Connection attempt {attempt + 1} failed: {str(e)}")
            attempt += 1
            if attempt < max_retries:
                print(f"Retrying in {retry_interval} seconds...")
                time.sleep(retry_interval)
            else:
                print("Max connection attempts reached, exiting.")


def initialize_database():
    if "clients" not in db.list_collection_names():
        print("Initializing database with sample data...")
        sample_clients = [
            {"first_name": "Alice", "last_name": "Johnson", "address": "100 Maple Street", "phone": "555-1010"},
            {"first_name": "Bob", "last_name": "Smith", "address": "200 Oak Avenue", "phone": "555-2020"},
            {"first_name": "Carol", "last_name": "Williams", "address": "300 Pine Lane", "phone": "555-3030"}
        ]
        clients_collection.insert_many(sample_clients)
        print("Sample data inserted successfully.")
    else:
        print("Database already initialized.")


def serve():
    initialize_database()

    time.sleep(10)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    service_pb2_grpc.add_ClientServiceServicer_to_server(ClientService(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("gRPC server is running on port 50051")

    rabbitmq_consumer()

    server.wait_for_termination()


if __name__ == '__main__':
    serve()
