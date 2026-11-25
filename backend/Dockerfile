FROM python:3.12-slim

# OCR for scanned résumés: ocrmypdf shells out to Tesseract and Ghostscript.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng ghostscript \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# scripts/, migrations/ and alembic.ini let scheduled jobs and migrations reuse this image.
COPY app ./app
COPY data ./data
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini .

RUN useradd --create-home appuser && mkdir -p local_results local_exports && chown -R appuser /app
USER appuser

EXPOSE 8000
# One worker: plan and run stores use in-process locks.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
