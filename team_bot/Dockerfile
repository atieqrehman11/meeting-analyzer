FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV PYTHONPATH=/app
EXPOSE 3978

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3978"]
