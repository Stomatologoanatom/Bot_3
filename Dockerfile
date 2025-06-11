# Базовый образ с Python 3.10 (можно взять 3.11 или 3.13, если поддерживается aiogram)
FROM python:3.10

# Рабочая директория в контейнере
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Обновляем pip и ставим зависимости
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Копируем весь проект внутрь контейнера
COPY . .

# Создаем папку для логов (если нет)
RUN mkdir -p logs

# Точка входа - запуск бота
CMD ["python", "bot.py"]