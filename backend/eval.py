import os
import json
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field
from main import _run_and_cache
from llm_key_pool import llm_key_pool
from langchain_core.messages import HumanMessage

class EvalMatch(BaseModel):
    match: bool = Field(description="True if the verified claim successfully fulfills the expected ground truth fact and points to the correct file.")
    reasoning: str = Field(description="Explanation of why it matches or fails.")

async def judge_claim(fact, expected_file, claims, llm):
    # Filter only verified claims that cite the expected file
    candidate_claims = [
        c for c in claims 
        if c.get('status') == 'Verified' and expected_file in c.get('cited_file', '')
    ]
    
    if not candidate_claims:
        return False
        
    prompt = f"Expected Fact: {fact}\nExpected File: {expected_file}\n\nCandidate Verified Claims:\n"
    for c in candidate_claims:
        prompt += f"- Claim: {c['claim']}\n  File: {c['cited_file']}\n"
    
    prompt += "\nDoes ANY candidate claim semantically cover the Expected Fact? Respond with a JSON object containing 'match' (boolean) and 'reasoning' (string)."
    
    structured_llm = llm.with_structured_output(EvalMatch)
    try:
        res = structured_llm.invoke([HumanMessage(content=prompt)])
        return res.match
    except Exception as e:
        print(f"  [!] LLM judge error: {e}")
        return False

async def main():
    gt_dir = Path(__file__).parent / "ground_truths"
    if not gt_dir.exists():
        print("No ground_truths directory found.")
        return
        
    llm = llm_key_pool.get_llm(temperature=0.0)
    
    for gt_file in gt_dir.glob("*.json"):
        if gt_file.name == "sample_repo.json":
            continue
            
        repo_name = gt_file.stem
        # Try to infer github url
        if repo_name == "starlette":
            repo_url = "https://github.com/encode/starlette"
        elif repo_name == "click":
            repo_url = "https://github.com/pallets/click"
        elif repo_name == "kleur":
            repo_url = "https://github.com/lukeed/kleur"
        else:
            print(f"Unknown repo {repo_name}")
            continue
            
        print(f"\nEvaluating {repo_url}...")
        
        with open(gt_file, "r") as f:
            facts = json.load(f)
            
        # Run analysis (use cache if available to speed up repeated eval runs)
        state = await _run_and_cache(repo_url, None, "technical", force_refresh=False)
        verified_claims = [c for c in state.get("claims", []) if c.get("status") == "Verified"]
        
        print(f"Found {len(verified_claims)} Verified Claims.")
        
        covered = 0
        for fact in facts:
            is_match = await judge_claim(fact["fact"], fact["expected_file"], verified_claims, llm)
            if is_match:
                print(f"  [+] MATCH: {fact['fact']} ({fact['expected_file']})")
                covered += 1
            else:
                print(f"  [x] MISS:  {fact['fact']} ({fact['expected_file']})")
                
        coverage = (covered / len(facts)) * 100 if facts else 0
        precision = (covered / len(verified_claims)) * 100 if verified_claims else 0
        
        print(f"\n--- {repo_name} Results ---")
        print(f"Coverage:  {coverage:.1f}% ({covered}/{len(facts)} expected facts found)")
        print(f"Precision: {precision:.1f}% ({covered} matches / {len(verified_claims)} total verified claims)")

if __name__ == "__main__":
    asyncio.run(main())
