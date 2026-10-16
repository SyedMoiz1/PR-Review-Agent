FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY settings.py ./
COPY agent ./agent
COPY github_parsing ./github_parsing
COPY ingestion ./ingestion
COPY retrieval ./retrieval

EXPOSE 8080
CMD ["uvicorn", "github_parsing.webhook:app", "--host", "0.0.0.0", "--port", "8080"]
