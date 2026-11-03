FROM python:3.10-slim-bookworm

ENV PYTHONUNBUFFERED=1

WORKDIR /app
RUN pip install --no-cache-dir flask redis minio requests gunicorn
COPY rest-server.py .

EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "rest-server:app"]
