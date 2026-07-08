# 1. Python ka naya stable version use karenge (Debian Bookworm)
FROM python:3.10-slim-bookworm

# 2. System updates aur FFmpeg install karenge (Renamer bots ke liye zaroori hai)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# 3. Container ke andar working directory set karenge
WORKDIR /app

# 4. requirements.txt copy karenge taaki libraries install ho sakein
COPY requirements.txt .

# 5. Saari required Python libraries install karenge
RUN pip install --no-cache-dir -r requirements.txt

# 6. Poora code container mein copy karenge
COPY . .

# 7. Optimized Gunicorn configuration (3 Workers + 4 Threads) aur Bot dono ek sath chalane ke liye
CMD gunicorn --workers=3 --threads=4 -b 0.0.0.0:10000 app:app & python3 bot.py
