"""
cost_tracker.py — Per-request LLM cost and latency tracking.

Usage:
    from cost_tracker import track_llm_call, get_session_summary

    with track_llm_call("synthesizer", "gemini"):
        result = chain.invoke(...)

Or use the decorator:
    @track_llm_call_async("qa_agent", "groq")
    async def my_llm_fn():
        ...
"""
import time
import logging
import threading
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

# Approximate cost per 1M tokens (USD) — update when providers change pricing
_COST_PER_1M_TOKENS = {
    "gemini": {"input": 0.075, "output": 0.30},   # gemini-2.0-flash
    "groq": {"input": 0.05, "output": 0.08},        # llama-3.1-8b-instant (est.)
    "openai": {"input": 5.0, "output": 15.0},        # gpt-4o
    "anthropic": {"input": 3.0, "output": 15.0},     # claude-3-5-sonnet
}

# In-memory store — NOT thread-safe for aggregation, intentionally lightweight
_lock = threading.Lock()
_session_log: list[dict] = []
_MAX_LOG_ENTRIES = 500  # cap to avoid unbounded growth


def record(
    component: str,
    provider: str,
    latency_ms: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    error: Optional[str] = None,
):
    """Records a single LLM call to the in-memory log."""
    cost_table = _COST_PER_1M_TOKENS.get(provider, {"input": 0.0, "output": 0.0})
    estimated_cost_usd = (
        (input_tokens / 1_000_000) * cost_table["input"] +
        (output_tokens / 1_000_000) * cost_table["output"]
    )

    entry = {
        "component": component,
        "provider": provider,
        "latency_ms": round(latency_ms, 1),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": round(estimated_cost_usd, 6),
        "error": error,
        "timestamp": time.time(),
    }

    with _lock:
        if len(_session_log) >= _MAX_LOG_ENTRIES:
            _session_log.pop(0)
        _session_log.append(entry)

    if error:
        logger.warning(
            f"[cost_tracker] {component}/{provider} FAILED in {latency_ms:.0f}ms | {error}"
        )
    else:
        logger.info(
            f"[cost_tracker] {component}/{provider} | {latency_ms:.0f}ms | "
            f"~${estimated_cost_usd:.5f} | in={input_tokens} out={output_tokens} tokens"
        )


@contextmanager
def track(component: str, provider: str):
    """
    Context manager for synchronous LLM calls.
    Records latency. Token counts must be added manually via record() if available.

    Example:
        with track("synthesizer", "gemini"):
            result = chain.invoke(...)
    """
    t0 = time.monotonic()
    error = None
    try:
        yield
    except Exception as e:
        error = str(e)[:200]
        raise
    finally:
        latency_ms = (time.monotonic() - t0) * 1000
        record(component, provider, latency_ms, error=error)


def get_summary() -> dict:
    """Returns aggregate stats across all recorded calls in this session."""
    with _lock:
        log = list(_session_log)

    if not log:
        return {"total_calls": 0, "total_cost_usd": 0.0, "avg_latency_ms": 0.0}

    total_cost = sum(e["estimated_cost_usd"] for e in log)
    avg_latency = sum(e["latency_ms"] for e in log) / len(log)
    errors = sum(1 for e in log if e["error"])

    by_component: dict[str, dict] = {}
    for e in log:
        comp = e["component"]
        if comp not in by_component:
            by_component[comp] = {"calls": 0, "cost_usd": 0.0, "avg_latency_ms": 0.0, "latencies": []}
        by_component[comp]["calls"] += 1
        by_component[comp]["cost_usd"] += e["estimated_cost_usd"]
        by_component[comp]["latencies"].append(e["latency_ms"])

    for comp, stats in by_component.items():
        stats["avg_latency_ms"] = round(sum(stats["latencies"]) / len(stats["latencies"]), 1)
        del stats["latencies"]

    return {
        "total_calls": len(log),
        "total_cost_usd": round(total_cost, 5),
        "avg_latency_ms": round(avg_latency, 1),
        "error_count": errors,
        "by_component": by_component,
        "recent": log[-10:],  # last 10 calls
    }
