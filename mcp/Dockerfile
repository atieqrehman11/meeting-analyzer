FROM python:3.12-slim
WORKDIR /app

# Install dependencies
COPY ./shared_models /deps/shared_models
COPY ./mcp /deps/mcp
RUN pip install --no-cache-dir /deps/shared_models /deps/mcp

# Copy source — shared_models alongside app so it's importable as a package
COPY ./mcp /app
COPY ./shared_models /app/shared_models

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
