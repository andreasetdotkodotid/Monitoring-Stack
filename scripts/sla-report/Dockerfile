FROM python:3.12-alpine

WORKDIR /app
RUN pip install --no-cache-dir requests croniter
COPY report.py /app/report.py
CMD ["python", "/app/report.py"]
