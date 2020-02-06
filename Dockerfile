FROM python:3.7-slim

WORKDIR /root
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY webhook-mailbox.py .

CMD python3 webhook-mailbox.py watch $WEBHOOK_QUEUE_NAME $WEBHOOK_FORWARD_URL
