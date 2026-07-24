# Bunk Budget — one container that serves both the API and the frontend.
# Students never see this; it's how you (the owner) put the app online once.
FROM python:3.11-slim

WORKDIR /app

# Install deps first so this layer caches between code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hosts (Render, Railway, Fly, HF Spaces, Cloud Run…) inject $PORT; default 8000.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
