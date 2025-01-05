FROM python:3.12-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

# Копируем приложение
COPY . .

# Открываем порт 8081
EXPOSE 8081

# Запуск приложения
CMD ["python", "app.py"]
