FROM python:3.12-alpine

WORKDIR /app
RUN pip install --no-cache-dir pyyaml watchdog
COPY generate.py /app/generate.py
ENTRYPOINT ["python", "/app/generate.py"]
