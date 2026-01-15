"""Shared utilities for claude-proxy."""
import hashlib


def compute_agent_hash(prompt: str, strip_notes: bool = True) -> str:
    """
    Compute canonical agent hash from system prompt.

    Args:
        prompt: The system prompt to hash
        strip_notes: Whether to strip the Notes: section before hashing

    Returns:
        16-character hex hash
    """
    if strip_notes:
        # Handle all Notes: variations consistently
        for separator in ["\n\nNotes:", "\nNotes:", "Notes:"]:
            if separator in prompt:
                prompt = prompt.split(separator)[0]
                break
    return hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()[:16]
