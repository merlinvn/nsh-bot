FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install deps first — cached, only invalidates when pyproject.toml/uv.lock change
COPY pyproject.toml uv.lock* ./
RUN uv pip install --system --no-cache .

# Copy source — code changes don't invalidate the deps layer above
COPY src/ ./src/
COPY data/ ./data/

EXPOSE 8080

ENV NSH_MCP_DATA_DIR=/app/data

CMD ["uvicorn", "nsh_mcp.server:app", "--host", "0.0.0.0", "--port", "8080"]
