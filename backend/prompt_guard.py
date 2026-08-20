"""
prompt_guard.py — Lightweight prompt injection sanitizer.

Strips common prompt injection patterns from user-supplied content
(e.g. file contents pulled from GitHub) before that content is
inserted into LLM prompts.

Usage:
    from prompt_guard import sanitize_content, sanitize_file_snippets
"""
import re
import logging

logger = logging.getLogger(__name__)

# Patterns that look like prompt injection attempts inside repo files
_INJECTION_PATTERNS = [
    # Direct instruction overrides
    re.compile(r'ignore\s+(all\s+)?(previous|prior|above)\s+instructions?', re.IGNORECASE),
    re.compile(r'disregard\s+(all\s+)?(previous|prior|above)\s+instructions?', re.IGNORECASE),
    re.compile(r'forget\s+(all\s+)?(previous|prior|above)', re.IGNORECASE),
    re.compile(r'you\s+are\s+now\s+(?:a|an)\s+', re.IGNORECASE),
    re.compile(r'new\s+(system\s+)?prompt\s*:', re.IGNORECASE),
    re.compile(r'<\|?(?:im_start|im_end|system|user|assistant)\|?>', re.IGNORECASE),
    # Template delimiters used by Llama / Mistral / Gemma
    re.compile(r'\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>', re.IGNORECASE),
    # OpenAI / Anthropic role markers that could hijack structured output
    re.compile(r'"role"\s*:\s*"(system|assistant)"', re.IGNORECASE),
]

_REPLACEMENT = "[REDACTED — potential prompt injection]"


def sanitize_content(text: str) -> str:
    """
    Sanitizes a single string (file content, README, issue body, etc.)
    by replacing detected injection patterns with a placeholder.
    Returns the sanitized string.
    """
    if not text:
        return text

    original_len = len(text)
    for pattern in _INJECTION_PATTERNS:
        text = pattern.sub(_REPLACEMENT, text)

    if len(text) != original_len:
        logger.warning(
            "prompt_guard: Injection pattern detected and redacted in content "
            f"(original_len={original_len}, sanitized_len={len(text)})."
        )

    return text


def sanitize_file_snippets(files: list[dict]) -> list[dict]:
    """
    Sanitizes the 'content' field of each file dict in a list.
    Returns a new list with sanitized content (originals are not mutated).
    """
    sanitized = []
    for f in files:
        content = f.get("content", "")
        clean = sanitize_content(content)
        if clean != content:
            # Return a shallow copy with sanitized content
            sanitized.append({**f, "content": clean})
        else:
            sanitized.append(f)
    return sanitized
