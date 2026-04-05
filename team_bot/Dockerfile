FROM python:3.12-slim
WORKDIR /app

# Install dependencies
COPY ./shared_models /deps/shared_models
COPY ./orchestrator /deps/orchestrator
COPY ./team_bot /deps/team_bot
RUN pip install --no-cache-dir /deps/shared_models /deps/orchestrator /deps/team_bot

# Copy source — all packages alongside app so they're importable
COPY ./team_bot /app/team_bot
COPY ./orchestrator /app/orchestrator
COPY ./shared_models /app/shared_models

EXPOSE 3978
CMD ["uvicorn", "team_bot.main:app", "--host", "0.0.0.0", "--port", "3978"]
