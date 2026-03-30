FROM python:3.12-slim

WORKDIR /app

COPY ./team_bot/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY ./team_bot /app/team_bot
COPY ./orchestrator /app/orchestrator
COPY ./shared_models /app/shared_models

ENV PYTHONPATH=/app
EXPOSE 3978

CMD ["uvicorn", "team_bot.main:app", "--host", "0.0.0.0", "--port", "3978"]
