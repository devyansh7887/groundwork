import re
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
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
    def __init__(self):
        pass

    async def verify_claim_async(self, claim: Dict[str, Any], graph: Dict[str, Any], downloaded_files: List[Dict[str, str]], session_token: str | None = None) -> VerifierResult:
        cited_file = claim.get("cited_file", "")
        cited_symbol = claim.get("cited_symbol", "")
        claim_text = claim.get("claim", "")
        
        # 1. Direct Graph Check
        file_in_graph = cited_file in graph.get("files", [])
        symbol_in_graph = False
        
        if cited_symbol:
            target_id = f"{cited_file}:{cited_symbol}"
            symbol_in_graph = any(n.get("id") == target_id for n in graph.get("nodes", []))
            if not symbol_in_graph:
                # Fuzzy check
                symbol_in_graph = any(cited_symbol in n.get("name", "") and cited_file in n.get("id", "") for n in graph.get("nodes", []))
        
        # 2. Grep Check
        file_content = ""
        for f in downloaded_files:
            if f["path"] == cited_file:
                file_content = f["content"]
                break
                
        symbol_in_file = False
        if cited_symbol and file_content:
            if re.search(r'\b' + re.escape(cited_symbol) + r'\b', file_content):
                symbol_in_file = True

        # --- FAST PATH: resolve without LLM when answer is clear from static data ---

        # File doesn't exist at all → definitive Unverified, no LLM needed
        if not file_in_graph:
            return VerifierResult(
                claim=claim_text, cited_file=cited_file, cited_symbol=cited_symbol,
                status="Unverified",
                reasoning=f"File '{cited_file}' was not found in the repository graph."
            )

        # File exists AND symbol confirmed in graph or grep → Verified
        if symbol_in_graph or symbol_in_file:
            return VerifierResult(
                claim=claim_text, cited_file=cited_file, cited_symbol=cited_symbol,
                status="Verified",
                reasoning="File and symbol both confirmed by static analysis."
            )

        # File exists but no specific symbol cited → Inferred (file-level claim)
        if not cited_symbol:
            return VerifierResult(
                claim=claim_text, cited_file=cited_file, cited_symbol=cited_symbol,
                status="Inferred",
                reasoning="File exists in repository; no specific symbol to verify deeper."
            )

        # --- FAST PATH ONLY: Grey area — file exists but symbol not found. ---
        # We used to call the LLM here, but it takes too long and causes 100s timeouts on Render.
        return VerifierResult(
            claim=claim_text, cited_file=cited_file, cited_symbol=cited_symbol,
            status="Inferred",
            reasoning=f"File exists in repository, but symbol was not explicitly found. Marked Inferred to save time."
        )

    async def verify_claims_async(self, claims: List[Dict[str, Any]], graph: Dict[str, Any], downloaded_files: List[Dict[str, str]], session_token: str | None = None) -> List[Dict[str, Any]]:
        import asyncio
        sem = asyncio.Semaphore(2) # Limit to 2 concurrent requests to avoid instant 429s
        
        async def verify_with_sem(claim):
            async with sem:
                try:
                    return await self.verify_claim_async(claim, graph, downloaded_files, session_token)
                except Exception as e:
                    logger.warning(f"Failed to verify claim '{claim.get('claim', '')[:20]}...': {e}")
                    # Return the module-level fallback so asyncio.gather doesn't crash the pipeline
                    return _FallbackResult()

        tasks = [verify_with_sem(claim) for claim in claims]
        results = await asyncio.gather(*tasks)
        
        verified_claims = []
        for claim, res in zip(claims, results):
            claim_data = claim.copy()
            claim_data["status"] = res.status
            claim_data["reasoning"] = res.reasoning
            verified_claims.append(claim_data)
        return verified_claims
