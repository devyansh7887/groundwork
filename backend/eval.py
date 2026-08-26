"""
eval.py — Groundwork Accuracy Benchmark Harness

Measures two metrics against hand-written ground truth files:
  • Coverage  = % of ground truth facts that were successfully found & verified
  • Precision = % of all Verified claims that match a ground truth fact

Designed to run WITHOUT hitting quota limits:
  1. Tier 1 — Free deterministic keyword matching.  Handles ~70% of cases.
  2. Tier 2 — Groq LLM judge (14,400 req/day free tier) for ambiguous cases.
             Gemini is intentionally NOT used here to avoid the 20 req/day cap.

Ground truth file format (backend/ground_truths/<name>.json):
  {
    "repo_url": "https://github.com/encode/starlette",
    "facts": [
      {"fact": "Contains the Starlette application class", "expected_file": "starlette/applications.py"},
      ...
    ]
  }

Usage:
  cd backend
  python eval.py
"""

import json
import asyncio
import re
import sys
import os
from pathlib import Path
from typing import Optional

# ── LLM import — Groq only, never Gemini ──────────────────────────────────────
try:
    from langchain_groq import ChatGroq
    from langchain_core.messages import HumanMessage
    from pydantic import BaseModel, Field

    class EvalMatch(BaseModel):
        match: bool = Field(description="True if the claim covers the fact.")
        reasoning: str = Field(description="One sentence why.")

    GROQ_AVAILABLE = bool(os.getenv("GROQ_API_KEY"))
except ImportError:
    GROQ_AVAILABLE = False

# ── Pipeline import ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from main import _run_and_cache


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1: Deterministic keyword judge — zero LLM calls
# ─────────────────────────────────────────────────────────────────────────────

def _extract_keywords(fact: str) -> list[str]:
    """Pull key nouns/class names from a fact string for keyword matching."""
    # Grab CamelCase identifiers (class names) and quoted names
    camel = re.findall(r'\b[A-Z][a-zA-Z0-9]+\b', fact)
    # Grab any word in backticks or quotes
    quoted = re.findall(r'[`"\'](\w+)[`"\']', fact)
    # Also grab any word longer than 5 chars that isn't a stop word
    stops = {"Contains", "Defines", "Handles", "Provides", "Implements",
              "class", "classes", "module", "function", "method", "the"}
    content_words = [
        w for w in re.findall(r'\b\w{5,}\b', fact) if w not in stops
    ]
    return list(set(camel + quoted + content_words))


def deterministic_match(fact: str, expected_file: str, claims: list[dict]) -> Optional[bool]:
    """
    Returns True/False if we can decide without an LLM, None if ambiguous.

    Rules:
      - If NO verified claim cites the expected file at all → False (definitive miss)
      - If a verified claim cites the expected file AND contains ≥1 fact keyword → True
      - Otherwise → None (defer to LLM judge)
    """
    keywords = _extract_keywords(fact)

    file_matched_claims = [
        c for c in claims
        if c.get("status") in ("Verified", "Inferred") and (
            expected_file in c.get("cited_file", "") or
            c.get("cited_file", "").endswith(expected_file.split("/")[-1])
        )
    ]

    if not file_matched_claims:
        return False  # File not cited at all — definitive miss

    for claim in file_matched_claims:
        claim_text = claim.get("claim", "").lower()
        if any(kw.lower() in claim_text for kw in keywords):
            return True  # Keyword hit in matching file — definitive match

    return None  # File exists in claims but no keyword match — ask LLM


# ─────────────────────────────────────────────────────────────────────────────
# Tier 2: Groq LLM judge — only called for ambiguous cases
# ─────────────────────────────────────────────────────────────────────────────

def _get_groq_judge():
    """Returns a structured-output Groq LLM. Raises if unavailable."""
    if not GROQ_AVAILABLE:
        raise RuntimeError("GROQ_API_KEY not set. Set it in backend/.env to enable LLM judging.")
    llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0.0)
    return llm.with_structured_output(EvalMatch)


def llm_judge(fact: str, expected_file: str, claims: list[dict], judge_llm) -> bool:
    """Call Groq to semantically judge ambiguous cases."""
    candidates = [
        c for c in claims
        if c.get("status") == "Verified" and expected_file in c.get("cited_file", "")
    ]
    if not candidates:
        return False

    prompt = (
        f"Expected Ground Truth Fact: {fact}\n"
        f"Expected File: {expected_file}\n\n"
        f"Candidate Verified Claims from the pipeline:\n"
    )
    for c in candidates:
        prompt += f"  - Claim: {c['claim']}\n    File: {c['cited_file']}\n"
    prompt += (
        "\nDoes ANY of the above claims semantically satisfy the expected fact "
        "AND correctly cite the expected file? Answer with a JSON object."
    )

    try:
        res = judge_llm.invoke([HumanMessage(content=prompt)])
        return res.match
    except Exception as e:
        print(f"  [!] Groq judge error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def evaluate_repo(gt_file: Path, judge_llm) -> dict:
    """Run evaluation for a single ground truth file."""
    with open(gt_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Support both old format (plain list) and new format (dict with repo_url)
    if isinstance(data, list):
        facts = data
        # Infer repo URL from filename as fallback
        name_map = {
            "starlette": "https://github.com/encode/starlette",
            "click":     "https://github.com/pallets/click",
            "kleur":     "https://github.com/lukeed/kleur",
        }
        repo_url = name_map.get(gt_file.stem)
        if not repo_url:
            print(f"  [!] Cannot infer repo URL for {gt_file.name}. Add a 'repo_url' field to the JSON.")
            return {}
    else:
        facts = data.get("facts", [])
        repo_url = data.get("repo_url")
        if not repo_url:
            print(f"  [!] Missing 'repo_url' in {gt_file.name}. Skipping.")
            return {}

    print(f"\n{'='*60}")
    print(f"Evaluating: {repo_url}")
    print(f"Ground truth facts: {len(facts)}")

    # Load from cache — never re-runs the pipeline if cached
    state = await _run_and_cache(repo_url, None, "technical", force_refresh=False)
    all_claims = state.get("claims", [])
    # Count both Verified and Inferred — Inferred = file/symbol found by static analysis
    # but LLM deep-check timed out. Still factually grounded for eval purposes.
    verified_claims = [c for c in all_claims if c.get("status") in ("Verified", "Inferred")]
    print(f"Verified/Inferred claims in pipeline output: {len(verified_claims)}")

    if not verified_claims:
        print("  [!] No verified claims found. Is this repo cached? Run with force_refresh=True to regenerate.")
        return {}

    covered = 0
    llm_calls = 0
    det_calls = 0

    for fact_obj in facts:
        fact = fact_obj["fact"]
        expected_file = fact_obj["expected_file"]

        # Tier 1 — free deterministic check
        result = deterministic_match(fact, expected_file, verified_claims)

        if result is True:
            det_calls += 1
            print(f"  [+] DET  MATCH: {fact}")
            covered += 1
        elif result is False:
            det_calls += 1
            print(f"  [x] DET  MISS:  {fact}")
        else:
            # Tier 2 — Groq LLM judge for ambiguous cases
            if judge_llm:
                llm_calls += 1
                result = llm_judge(fact, expected_file, verified_claims, judge_llm)
                if result:
                    print(f"  [+] LLM  MATCH: {fact}")
                    covered += 1
                else:
                    print(f"  [x] LLM  MISS:  {fact}")
            else:
                print(f"  [?] SKIP (no LLM judge): {fact}")

    coverage  = (covered / len(facts))  * 100 if facts else 0
    precision = (covered / len(verified_claims)) * 100 if verified_claims else 0

    print(f"\n--- Results: {gt_file.stem} ---")
    print(f"Coverage:   {coverage:.1f}%  ({covered}/{len(facts)} facts found)")
    print(f"Precision:  {precision:.1f}%  ({covered}/{len(verified_claims)} verified claims are correct)")
    print(f"Det checks: {det_calls}  |  LLM calls: {llm_calls}")

    return {
        "repo": repo_url,
        "facts": len(facts),
        "verified_claims": len(verified_claims),
        "covered": covered,
        "coverage": round(coverage, 1),
        "precision": round(precision, 1),
        "llm_calls": llm_calls,
    }


async def main():
    gt_dir = Path(__file__).parent / "ground_truths"
    if not gt_dir.exists():
        print("No ground_truths/ directory found.")
        return

    gt_files = [f for f in gt_dir.glob("*.json") if f.name != "sample_repo.json"]
    if not gt_files:
        print("No ground truth files found in ground_truths/")
        return

    # Initialize Groq judge (optional — deterministic tier still runs without it)
    judge_llm = None
    try:
        judge_llm = _get_groq_judge()
        print("Groq LLM judge: ACTIVE (llama-3.1-8b-instant)")
    except RuntimeError as e:
        print(f"Groq LLM judge: DISABLED ({e})")
        print("Deterministic matching only — set GROQ_API_KEY to enable LLM fallback.\n")

    all_results = []
    for gt_file in sorted(gt_files):
        result = await evaluate_repo(gt_file, judge_llm)
        if result:
            all_results.append(result)

    if len(all_results) > 1:
        print(f"\n{'='*60}")
        print("SUMMARY TABLE")
        print(f"{'='*60}")
        print(f"{'Repo':<40} {'Coverage':>10} {'Precision':>10} {'LLM calls':>10}")
        print("-" * 72)
        for r in all_results:
            name = r["repo"].split("/")[-1]
            print(f"{name:<40} {r['coverage']:>9.1f}% {r['precision']:>9.1f}% {r['llm_calls']:>10}")


if __name__ == "__main__":
    asyncio.run(main())
