FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY src/ ./src/
COPY pyproject.toml uv.lock* ./

RUN uv pip install --system --no-cache .

COPY data/ ./data/

RUN cp -r /app/data /usr/local/lib/python3.11/site-packages/nsh_mcp/data

EXPOSE 8080

CMD ["uvicorn", "nsh_mcp.server:app", "--host", "0.0.0.0", "--port", "8080"]
