FROM python:3.14-slim

RUN pip install --no-cache-dir requests && \
    mkdir /app

COPY main.py /app/main.py

WORKDIR /app

ENTRYPOINT ["python", "/app/main.py"]
CMD []
