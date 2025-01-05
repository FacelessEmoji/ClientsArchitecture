import os
import subprocess


# first need grpc package
# Путь к корневой директории проекта
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
# Путь к папке, где находятся .proto файлы
proto_files_dir = os.path.join(PROJECT_ROOT, 'proto')

# Проход по папке proto для поиска .proto файлов
for dirpath, dirnames, filenames in os.walk(proto_files_dir):
    proto_files = [f for f in filenames if f.endswith('.proto')]
    if proto_files:
        # Генерация Python файлов для каждого .proto
        for proto_file in proto_files:
            print(f"Processing .proto file '{proto_file}'...", end=' ')
            proto_file_path = os.path.join(dirpath, proto_file)
            command = (
                f'python -m grpc_tools.protoc '
                f'--proto_path={proto_files_dir} '  # Указываем папку proto как корень
                f'--python_out={proto_files_dir} '
                f'--grpc_python_out={proto_files_dir} '
                f'{proto_file_path}'
            )
            subprocess.run(command, shell=True, check=True)
            print("OK!")

        # Создание __init__.py в папке proto (если нужно для импорта)
        init_file_path = os.path.join(proto_files_dir, '__init__.py')
        if not os.path.exists(init_file_path):
            with open(init_file_path, 'w') as init_file:
                init_file.write(
                    "import os\nimport sys\n\nsys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))\n")
            print(f"Created __init__.py in {proto_files_dir}")
