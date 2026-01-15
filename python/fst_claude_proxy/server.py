"""
fst-claude-proxy server entry point.

Starts LiteLLM proxy server with custom hooks for:
- Agent routing (per-agent model selection based on prompt fingerprinting)
- OAuth token injection (Claude credentials forwarding)

Usage:
    python server.py
    # or
    python -m fst_claude_proxy.server

Environment Variables:
    PROXY_PORT: Port to listen on (default: 4000)
    PROXY_HOST: Host to bind to (default: 0.0.0.0)
    LITELLM_CONFIG: Path to LiteLLM config YAML
    AGENT_REGISTRY_PATH: Path to agent hash registry JSON
    CLAUDE_CREDENTIALS_PATH: Path to Claude OAuth credentials
    DEBUG: Enable verbose logging (default: false)
"""

import logging
import os
from pathlib import Path

# Configure logging based on DEBUG environment variable
log_level = (
    logging.DEBUG
    if os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
    else logging.INFO
)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Start the LiteLLM proxy server."""
    import shutil

    # Get configuration from environment
    port = int(os.environ.get("PROXY_PORT", "4000"))
    host = os.environ.get("PROXY_HOST", "0.0.0.0")
    config_path = os.environ.get(
        "LITELLM_CONFIG",
        str(Path(__file__).parent / "litellm_config.yaml"),
    )

    logger.info("[server] fst-claude-proxy starting...")
    logger.info(f"[server] Config: {config_path}")
    logger.info(f"[server] Host: {host}:{port}")

    # Note: Callbacks are configured in litellm_config.yaml, not in Python
    # The YAML file has: callbacks: fst_claude_proxy.hooks.callbacks.proxy_callbacks

    # Find litellm CLI executable (not litellm-proxy which is the client)
    litellm_cli = shutil.which("litellm")
    if not litellm_cli:
        logger.error("[server] litellm executable not found!")
        raise RuntimeError("litellm not found in PATH")

    # Build litellm proxy command
    cmd = [
        litellm_cli,
        "--config",
        config_path,
        "--host",
        host,
        "--port",
        str(port),
    ]

    # Add debug flag if enabled
    if os.environ.get("DEBUG", "").lower() in ("1", "true", "yes"):
        cmd.append("--detailed_debug")

    logger.info(f"[server] Starting LiteLLM proxy: {' '.join(cmd)}")

    # Execute litellm proxy (replaces current process)
    os.execvp(litellm_cli, cmd)


if __name__ == "__main__":
    main()
