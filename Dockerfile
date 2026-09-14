$env:Path = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin;$env:Path"
gcloud auth listFROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 app:app