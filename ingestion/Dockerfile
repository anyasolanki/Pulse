FROM python:3.12-slim
WORKDIR /app
COPY ingestion/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ingestion /app/ingestion
CMD ["python", "-m", "ingestion.hacker_news"]
