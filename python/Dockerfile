# claude-proxy Dockerfile
# ========================
# LiteLLM-based proxy with agent routing and OAuth support
#
# Build:
#   docker build -t claude-proxy .
#
# Run:
#   docker run -p 4000:4000 \
#     -v ~/.claude/.credentials.json:/app/.credentials.json:ro \
#     -e ANTHROPIC_API_KEY=sk-ant-... \
#     claude-proxy

FROM python:3.11-slim

LABEL maintainer="claude-workflow"
LABEL description="Claude Proxy - LiteLLM proxy with per-agent model routing"
LABEL version="0.1.0"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy pyproject.toml for package metadata
COPY pyproject.toml .

# Copy the claude_proxy package
COPY claude_proxy/ /app/claude_proxy/

# Copy config files
COPY litellm_config.yaml /app/litellm_config.yaml
COPY routing_config.yaml /app/routing_config.yaml

# Install the package in development mode (editable)
RUN pip install -e .

# Create directories for config and registry (may be overridden by volume mounts)
RUN mkdir -p /app/config /app/registry

# Copy registry data to the expected location
RUN cp /app/claude_proxy/registry/agent_hashes.json /app/registry/agent_hashes.json || true

# Set Python path to include app directory for imports
ENV PYTHONPATH=/app

# Default configuration
ENV PROXY_PORT=4000
ENV PROXY_HOST=0.0.0.0
ENV LITELLM_CONFIG=/app/litellm_config.yaml
ENV ROUTING_CONFIG=/app/routing_config.yaml
ENV AGENT_REGISTRY_PATH=/app/registry/agent_hashes.json
ENV CLAUDE_CREDENTIALS_PATH=/app/.credentials.json

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PROXY_PORT}/health || exit 1

# Expose proxy port
EXPOSE ${PROXY_PORT}

# Start the server using the CLI
CMD ["claude-proxy", "start"]
