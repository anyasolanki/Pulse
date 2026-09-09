FROM python:3.12-slim AS runtime
WORKDIR /app
COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt
COPY analytics /app/analytics
COPY api /app/api
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test
RUN pip install --no-cache-dir -r api/requirements-test.txt
COPY tests /app/tests
COPY ingestion /app/ingestion
COPY scripts /app/scripts
CMD ["sh", "-c", "python -m unittest discover -s tests -v && python -m unittest discover -s tests/api -v"]
