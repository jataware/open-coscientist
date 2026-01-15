# mcp server dockerfile
FROM python:3.12-slim

# set working directory
WORKDIR /app

# install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# copy dependency files
COPY mcp_server/pyproject.toml ./mcp_server/

# install python dependencies
RUN pip install --no-cache-dir -e ./mcp_server

# copy application code
COPY mcp_server/ ./mcp_server/

# expose port
EXPOSE 8888

# environment variables (can be overridden via docker compose or -e flags)
ENV COSCIENTIST_MCP_PORT=8888
ENV PYTHONUNBUFFERED=1

# health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8888', timeout=5.0)" || exit 1

# run server
CMD ["uvicorn", "mcp_server.server:app", "--host", "0.0.0.0", "--port", "8888"]
