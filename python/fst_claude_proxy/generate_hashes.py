#!/usr/bin/env python3
"""
Generate agent hash registry from template agent files.

Scans src/templates/.claude/agents/*.md and generates SHA256[:16] hashes
for each agent's prompt content. The generated registry maps agent hashes
to target models for per-agent model routing.

Usage:
    python generate_hashes.py [--output PATH] [--agents-dir PATH] [--dry-run]

The hash algorithm:
1. Read agent markdown file
2. Extract content after YAML frontmatter
3. Strip "\n\nNotes:" section (dynamic per-request content)
4. Compute SHA256 hash and take first 16 characters
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fst_claude_proxy.utils import compute_agent_hash


# Default registry path (global location for cross-project consistency)
GLOBAL_REGISTRY_PATH = Path.home() / ".claude-workflow" / "agent-hashes.json"

# Default model for all agents (can be overridden per-agent)
DEFAULT_MODEL = "opus"

# NOTE: Only agents requiring NON-DEFAULT models are listed here.
# Agents not in this dict inherit DEFAULT_MODEL ("opus").
# This is intentional - most agents use opus by default for quality.
# Per-agent model overrides (customize per cost/capability needs)
AGENT_MODEL_OVERRIDES: Dict[str, str] = {
    # Expensive agents - use most capable model (explicit for documentation)
    "cto-architect": "opus",
    "backend-engineer": "opus",
    "frontend-engineer": "opus",
    "research": "opus",
    "feature-planner": "opus",
    "task-maker": "opus",
    "Explore": "opus",
    # Medium complexity - balanced model
    "code-reviewer": "sonnet",
    "debugger": "sonnet",
    "qa-engineer": "sonnet",
    "devops-engineer": "sonnet",
    "task-reviewer": "sonnet",
    "skill-analyzer": "sonnet",
    "agent-analyzer": "sonnet",
    # Simple/quick tasks - fastest model
    "css-fixer": "haiku",
    "lint-fixer": "haiku",
    "auto-fixer": "haiku",
    "cleanup-agent": "haiku",
}


def extract_prompt_from_markdown(md_content: str) -> str:
    """
    Extract agent system prompt from markdown file.

    Agent markdown format:
    ---
    name: agent-name
    description: ...
    ---

    <!-- Common Queries -->
    ...

    [STAKES:MAXIMUM]
    ...

    Actual prompt content...

    Notes: Dynamic content excluded from hash

    Args:
        md_content: Full markdown file content

    Returns:
        Extracted prompt content (everything after YAML frontmatter)
    """
    # Remove YAML frontmatter (content between --- delimiters)
    parts = md_content.split("---", 2)
    if len(parts) < 3:
        # No frontmatter, use entire content
        prompt_section = md_content
    else:
        prompt_section = parts[2].strip()

    return prompt_section


def discover_agents(agents_dir: Path) -> List[Path]:
    """
    Discover all agent markdown files in directory.

    Args:
        agents_dir: Path to agents directory

    Returns:
        List of paths to agent markdown files, sorted alphabetically
    """
    if not agents_dir.exists():
        print(f"[generate-hashes] Error: Agents directory not found: {agents_dir}")
        return []

    agent_files = list(agents_dir.glob("*.md"))
    print(f"[generate-hashes] Found {len(agent_files)} agent files in {agents_dir}")
    return sorted(agent_files)


def process_agent_file(agent_path: Path) -> Tuple[str, str, str]:
    """
    Process single agent file and extract hash.

    Args:
        agent_path: Path to agent markdown file

    Returns:
        Tuple of (agent_name, hash, target_model)
    """
    agent_name = agent_path.stem  # Remove .md extension

    content = agent_path.read_text(encoding="utf-8")
    prompt = extract_prompt_from_markdown(content)
    agent_hash = compute_agent_hash(prompt)

    # Get model for this agent (defaults to DEFAULT_MODEL if not in overrides)
    target_model = AGENT_MODEL_OVERRIDES.get(agent_name, DEFAULT_MODEL)

    return agent_name, agent_hash, target_model


def generate_registry(agents_dir: Path) -> Dict:
    """
    Generate complete hash registry from agents directory.

    Args:
        agents_dir: Path to agents directory

    Returns:
        Registry dict ready for saving with mappings, metadata, and agent_info
    """
    agent_files = discover_agents(agents_dir)

    if not agent_files:
        return {"mappings": {}, "metadata": {"error": "No agents found"}}

    mappings: Dict[str, str] = {}
    agent_info: Dict[str, Dict[str, str]] = {}  # For metadata and debugging

    print("\n[generate-hashes] Processing agents:")
    print("-" * 70)

    for agent_path in agent_files:
        agent_name, agent_hash, target_model = process_agent_file(agent_path)

        mappings[agent_hash] = target_model
        agent_info[agent_name] = {
            "hash": agent_hash,
            "model": target_model,
        }

        print(f"  {agent_name:30} -> {agent_hash} -> {target_model}")

    print("-" * 70)
    print(f"[generate-hashes] Total agents processed: {len(mappings)}")

    registry = {
        "mappings": mappings,
        "metadata": {
            "description": "Agent hash to model routing table. Generated by generate_hashes.py",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "agents_dir": str(agents_dir),
            "agent_count": len(mappings),
            "default_model": DEFAULT_MODEL,
            "version": "1.0.0",
        },
        "agent_info": agent_info,  # For debugging/reference
    }

    return registry


def save_registry(registry: Dict, registry_path: Path) -> None:
    """
    Save agent hash registry to JSON file.

    Args:
        registry: Registry dict to save
        registry_path: Path to save registry to
    """
    # Ensure directory exists
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)

    print(f"[generate-hashes] Saved registry to {registry_path}")


def find_agents_dir() -> Optional[Path]:
    """
    Auto-detect agents directory from common locations.

    Searches in order:
    1. Relative to this script: ../../templates/.claude/agents
    2. Current working directory: src/templates/.claude/agents
    3. Current working directory: .claude/agents

    Returns:
        Path to agents directory if found, None otherwise
    """
    script_dir = Path(__file__).parent
    # Navigate from fst_claude_proxy package to find agents
    possible_paths = [
        script_dir.parent.parent.parent / "templates" / ".claude" / "agents",
        Path.cwd() / "src" / "templates" / ".claude" / "agents",
        Path.cwd() / ".claude" / "agents",
    ]

    for path in possible_paths:
        if path.exists():
            return path

    return None


def main() -> None:
    """CLI entry point for generate-agent-hashes command."""
    parser = argparse.ArgumentParser(
        description="Generate agent hash registry from template agents"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=GLOBAL_REGISTRY_PATH,
        help=f"Output path for registry JSON (default: {GLOBAL_REGISTRY_PATH})",
    )
    parser.add_argument(
        "--agents-dir",
        type=Path,
        default=None,
        help="Path to agents directory (default: auto-detect from package)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print registry without saving",
    )

    args = parser.parse_args()

    # Auto-detect agents directory if not specified
    if args.agents_dir is None:
        args.agents_dir = find_agents_dir()

        if args.agents_dir is None:
            print("[generate-hashes] Error: Could not auto-detect agents directory")
            print("Please specify --agents-dir explicitly")
            sys.exit(1)

    print(f"[generate-hashes] Using agents directory: {args.agents_dir}")

    registry = generate_registry(args.agents_dir)

    if args.dry_run:
        print("\n[dry-run] Registry content:")
        print(json.dumps(registry, indent=2))
    else:
        save_registry(registry, args.output)
        print(f"\n[generate-hashes] Registry saved to: {args.output}")
        print(f"[generate-hashes] {registry['metadata']['agent_count']} agents registered")


if __name__ == "__main__":
    main()
