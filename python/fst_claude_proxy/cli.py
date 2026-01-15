"""CLI entry point using click."""
import os
from typing import Optional

import click


@click.group()
@click.version_option(version="0.1.0", prog_name="fst-proxy")
def main() -> None:
    """fst-claude-proxy - LiteLLM proxy with agent routing and OAuth injection."""
    pass


@main.command()
@click.option("--port", "-p", default=4000, help="Port to listen on")
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.option(
    "--config", "-c", type=click.Path(exists=True), help="Path to litellm config"
)
@click.option("--debug", is_flag=True, help="Enable debug logging")
def start(port: int, host: str, config: Optional[str], debug: bool) -> None:
    """Start the proxy server."""
    os.environ["PROXY_PORT"] = str(port)
    os.environ["PROXY_HOST"] = host
    if config:
        os.environ["LITELLM_CONFIG"] = config
    if debug:
        os.environ["DEBUG"] = "true"

    from .server import main as server_main

    server_main()


@main.command()
@click.argument("agents_dir", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output path for hashes JSON")
def generate_hashes(agents_dir: str, output: Optional[str]) -> None:
    """Generate agent fingerprint hashes from agent markdown files."""
    from .generate_hashes import main as gen_main
    import sys

    # Build argv for the generate_hashes script
    argv = ["generate_hashes", "--agents-dir", agents_dir]
    if output:
        argv.extend(["--output", output])

    sys.argv = argv
    gen_main()


@main.command()
def config() -> None:
    """Show current configuration."""
    import json

    from .config.loader import get_config

    cfg = get_config()
    litellm_cfg = cfg.load_litellm_config()
    routing_cfg = cfg.load_routing_config()

    output = {
        "litellm": litellm_cfg,
        "routing": routing_cfg,
    }
    click.echo(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
