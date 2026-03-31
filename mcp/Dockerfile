FROM python:3.12-slim
WORKDIR /app

# Install shared_models first (mcp depends on it)
COPY ./shared_models /deps/shared_models
RUN pip install --no-cache-dir /deps/shared_models

# Install mcp server
COPY ./mcp /deps/mcp
RUN pip install --no-cache-dir /deps/mcp

COPY ./mcp /app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
