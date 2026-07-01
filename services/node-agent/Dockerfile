FROM python:3.13-slim

WORKDIR /app

RUN useradd -r -u 10001 nodeagent

COPY simulator.py ./simulator.py

RUN pip install --no-cache-dir simpy==4.1.1

RUN mkdir -p /data && chown -R nodeagent:nodeagent /data /app

USER nodeagent

ENV LOCAL_DB_PATH=/data/node.db

CMD ["python", "simulator.py"]
