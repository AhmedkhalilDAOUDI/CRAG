FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-ocr.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ocr.txt
COPY crag ./crag
COPY web ./web
COPY scripts ./scripts
COPY data/index ./data/index
RUN useradd -m crag && chown -R crag /app
USER crag
EXPOSE 8080
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8080/api/health')"
CMD ["uvicorn", "crag.api:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
