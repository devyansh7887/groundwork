import json
import argparse
import asyncio
from pipeline import Pipeline

def compute_metrics(verified_claims, ground_truth_facts):
    """
    Computes precision and coverage based on the Verified claims and ground truths.
    Precision: % of Verified claims that match a ground-truth expected_file
    Coverage: % of ground-truth facts that were surfaced by any Verified claim
    """
    # Precision
    matched_verified = 0
    total_verified = len(verified_claims)
    
    gt_files = set(f["expected_file"] for f in ground_truth_facts)
    
    for claim in verified_claims:
        if claim["cited_file"] in gt_files:
            matched_verified += 1
            
    precision = (matched_verified / total_verified * 100) if total_verified > 0 else 0
    
    # Coverage
    surfaced_facts = 0
    total_facts = len(ground_truth_facts)
    
    verified_files = set(c["cited_file"] for c in verified_claims)
    
    for fact in ground_truth_facts:
        if fact["expected_file"] in verified_files:
            surfaced_facts += 1
            
    coverage = (surfaced_facts / total_facts * 100) if total_facts > 0 else 0
    
    return precision, coverage, total_verified, total_facts

async def run_benchmark(repo_url: str, truth_file: str):
    print(f"Running benchmark for {repo_url}...")
    with open(truth_file, "r") as f:
        ground_truths = json.load(f)
        
    pipeline = Pipeline()
    final_state = await pipeline.run(repo_url)
    
    all_claims = final_state["claims"]
    verified_claims = [c for c in all_claims if c["status"] == "Verified"]
    
    precision, coverage, total_verified, total_facts = compute_metrics(verified_claims, ground_truths)
    
    print("\n--- Benchmark Results ---")
    print(f"Repo: {repo_url}")
    print(f"Verified Claims: {total_verified}")
    print(f"Ground Truth Facts: {total_facts}")
    print(f"Precision: {precision:.1f}%")
    print(f"Coverage: {coverage:.1f}%")
    print("-------------------------\n")
    
    return {
        "repo": repo_url,
        "precision": precision,
        "coverage": coverage,
        "verified": total_verified,
        "facts": total_facts
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Grounded Accuracy Benchmark")
    parser.add_argument("--repo", type=str, help="GitHub Repository URL")
    parser.add_argument("--truth_file", type=str, help="Path to JSON ground truth file")
    
    args = parser.parse_args()
    
    if args.repo and args.truth_file:
        asyncio.run(run_benchmark(args.repo, args.truth_file))
    else:
        print("Please provide --repo and --truth_file to run.")
        print("Example: python benchmark.py --repo https://github.com/encode/starlette --truth_file ground_truths/starlette.json")
