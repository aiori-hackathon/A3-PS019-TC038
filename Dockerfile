# PrivacyTwin API (FastAPI). Build context: the repository root.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PORT=8000 PRIVACYTWIN_DB=/data/workspace.sqlite3
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py ./
COPY core ./core
# Workspace database and uploads live on a mounted volume at /data.
RUN mkdir -p /data
EXPOSE 8000
# "::" listens on IPv6 and IPv4, which Railway's private network needs.
# Run a single worker: AI review runs in background threads inside this process.
CMD ["sh", "-c", "exec uvicorn main:app --host :: --port ${PORT} --workers 1 --proxy-headers"]
