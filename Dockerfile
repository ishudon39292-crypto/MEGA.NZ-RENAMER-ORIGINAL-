# 1. Python ka lightweight aur stable version use karenge
FROM python:3.10-slim-buster

# 2. System updates aur FFmpeg install karenge (Renamer bots ke liye zaroori hai)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# 3. Container ke andar ka folder (Working Directory) set karenge
WORKDIR /app

# 4. Pehle requirements.txt copy karenge taaki libraries install ho sakein
COPY requirements.txt .

# 5. Saari Python libraries (Pyrogram, Gunicorn, etc.) install karenge
RUN pip install --no-cache-dir -r requirements.txt

# 6. Ab bacha hua poora bot ka code container mein copy karenge
COPY . .

# 7. Gunicorn web server aur Python bot dono ko ek sath chalane ke liye command
CMD gunicorn app:app & python3 main.py
