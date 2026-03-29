FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY collector/ collector/
COPY api/ api/
COPY frontend/ frontend/

VOLUME /app/data

# Default: run collector. Override with docker-compose for API.
CMD ["python", "-m", "collector.main"]
