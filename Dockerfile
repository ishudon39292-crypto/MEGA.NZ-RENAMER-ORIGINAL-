# 1. Python ka naya stable version use karenge (Debian Bookworm)
FROM python:3.10-slim-bookworm

# 2. System updates aur FFmpeg install karenge (Isme 404 error nahi aayega)
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

# 7. Gunicorn web server aur aapka python command dono ek sath chalane ke liye
CMD gunicorn app:app & python3 main.py
