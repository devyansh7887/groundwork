import re
import asyncio
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from llm_key_pool import llm_key_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VerifierResult(BaseModel):
    claim: str
    cited_file: str
    cited_symbol: Optional[str]
    status: str = Field(description="One of: 'Verified', 'Inferred', 'Unverified'")
    reasoning: str = Field(description="Explanation of why this status was assigned.")

class _FallbackResult(BaseModel):
    """Module-level fallback used when a claim verification raises an exception."""
    status: str = "Unverified"
    reasoning: str = "LLM or system error during verification."

class Verifier:
    # LLM verification per-claim timeout (seconds).
    # Keeps the pipeline moving even on very large repos with slow models.
    _LLM_TIMEOUT = 8.0

    def __init__(self):
        pass

    async def verify_claim_async(
        self,
        claim: Dict[str, Any],
        graph: Dict[str, Any],
        downloaded_files: List[Dict[str, str]],
        session_token: str | None = None,
    ) -> VerifierResult:
        cited_file = claim.get("cited_file", "")
        cited_symbol = claim.get("cited_symbol", "")
        claim_text = claim.get("claim", "")

        # ── 1. Graph existence check ───────────────────────────────────────────
        file_in_graph = cited_file in graph.get("files", [])
        symbol_in_graph = False

        if cited_symbol:
            target_id = f"{cited_file}:{cited_symbol}"
            symbol_in_graph = any(n.get("id") == target_id for n in graph.get("nodes", []))
            if not symbol_in_graph:
                symbol_in_graph = any(
                    cited_symbol in n.get("name", "") and cited_file in n.get("id", "")
                    for n in graph.get("nodes", [])
                )

        # ── 2. Grep check on raw file content ──────────────────────────────────
        file_content = ""
        for f in downloaded_files:
            if f["path"] == cited_file:
                file_content = f.get("content") or ""
                break

        symbol_in_file = False
        if cited_symbol and file_content:
            symbol_in_file = bool(re.search(r'\b' + re.escape(cited_symbol) + r'\b', file_content))

        # ── FAST PATH: definitively resolve without LLM ────────────────────────

        # File doesn't exist → definitively Unverified
        if not file_in_graph:
            return VerifierResult(
                claim=claim_text, cited_file=cited_file, cited_symbol=cited_symbol,
                status="Unverified",
                reasoning=f"File '{cited_file}' was not found in the repository graph.",
            )

        # File + symbol both confirmed → definitively Verified
        if symbol_in_graph or symbol_in_file:
            return VerifierResult(
                claim=claim_text, cited_file=cited_file, cited_symbol=cited_symbol,
                status="Verified",
                reasoning="File and symbol both confirmed by static analysis.",
            )

        # File-level claim (no symbol) → Inferred without LLM
        if not cited_symbol:
            return VerifierResult(
                claim=claim_text, cited_file=cited_file, cited_symbol=cited_symbol,
                status="Inferred",
                reasoning="File exists in repository; no specific symbol to verify deeper.",
            )

        # ── LLM PATH: file exists but symbol not found by static analysis ──────
        # Try LLM verification with a hard per-claim timeout so large repos can't
        # stall the pipeline. Falls back to Inferred on timeout / error.
        try:
            result = await asyncio.wait_for(
                self._llm_verify(claim_text, cited_file, cited_symbol, file_content, session_token),
                timeout=self._LLM_TIMEOUT,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(
                f"Verifier LLM timed out for claim '{claim_text[:40]}...' — marking Inferred."
            )
        except Exception as e:
            logger.warning(f"Verifier LLM error for '{claim_text[:40]}...': {e}")

        # Graceful fallback — file exists, we just couldn't deep-check the symbol
        return VerifierResult(
            claim=claim_text, cited_file=cited_file, cited_symbol=cited_symbol,
            status="Inferred",
            reasoning="File exists. Symbol presence could not be confirmed by static analysis; "
                       "LLM deep-check timed out or was unavailable.",
        )

    async def _llm_verify(
        self,
        claim_text: str,
        cited_file: str,
        cited_symbol: str,
        file_content: str,
        session_token: str | None,
    ) -> VerifierResult:
        """
        Calls the LLM to semantically verify a symbol in a file snippet.
        Runs in an executor so it doesn't block the event loop.
        Only the first 4 KB of the file is sent to keep token usage bounded.
        """
        # Truncate large files — top 4 KB covers all imports and function signatures
        snippet = file_content[:4096] if file_content else "(file content unavailable)"

        prompt = f"""You are a code verifier. Your ONLY job is to check whether the following architectural claim is supported by the code snippet below.

CLAIM: "{claim_text}"
FILE:  {cited_file}
SYMBOL EXPECTED: {cited_symbol}

CODE SNIPPET (first 4 KB):
```
{snippet}
```

Respond with exactly one of:
- VERIFIED: <one sentence why the symbol is clearly present and the claim holds>
- INFERRED: <one sentence why the file is related but you can't fully confirm the claim>
- UNVERIFIED: <one sentence why the claim contradicts the code>

Do NOT add anything else."""

        def _call_llm():
            max_retries = 6
            for attempt in range(1, max_retries + 1):
                try:
                    llm = llm_key_pool.get_llm(session_token=session_token, temperature=0.0)
                    from langchain_core.messages import HumanMessage
                    response = llm.invoke([HumanMessage(content=prompt)])
                    return response.content.strip()
                except Exception as e:
                    error_str = str(e).lower()
                    if "429" in error_str or "rate limit" in error_str or "quota" in error_str or "exhausted" in error_str:
                        try:
                            llm_key_pool.mark_rate_limit_for_llm(llm)
                        except Exception:
                            pass
                    
                    if attempt == max_retries:
                        raise RuntimeError(f"LLM call failed after {max_retries} attempts: {e}") from e
                    
                    import time
                    time.sleep(1.0)

        raw = await asyncio.to_thread(_call_llm)

        # Parse the structured response
        upper = raw.upper()
        if upper.startswith("VERIFIED"):
            status = "Verified"
        elif upper.startswith("UNVERIFIED"):
            status = "Unverified"
        else:
            status = "Inferred"

        # Extract the reasoning after the colon
        reasoning = raw.split(":", 1)[-1].strip() if ":" in raw else raw

        return VerifierResult(
            claim=claim_text,
            cited_file=cited_file,
            cited_symbol=cited_symbol,
            status=status,
            reasoning=reasoning,
        )

    async def verify_claims_async(
        self,
        claims: List[Dict[str, Any]],
        graph: Dict[str, Any],
        downloaded_files: List[Dict[str, str]],
        session_token: str | None = None,
    ) -> List[Dict[str, Any]]:
        # Concurrency cap: 1 simultaneous LLM call max to survive free-tier Gemini's strict 15 RPM limit.
        sem = asyncio.Semaphore(1)

        async def verify_with_sem(claim):
            async with sem:
                try:
                    # Artificially slow down to guarantee we never exceed 15 requests per minute
                    await asyncio.sleep(4.1) 
                    return await self.verify_claim_async(
                        claim, graph, downloaded_files, session_token
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to verify claim '{claim.get('claim', '')[:20]}...': {e}"
                    )
                    return _FallbackResult()

        results = await asyncio.gather(*[verify_with_sem(c) for c in claims])

        verified_claims = []
        for claim, res in zip(claims, results):
            claim_data = claim.copy()
            claim_data["status"] = res.status
            claim_data["reasoning"] = res.reasoning
            verified_claims.append(claim_data)

        return verified_claims
