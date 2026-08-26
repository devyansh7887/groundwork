import re
import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from verifier import Verifier
from llm_key_pool import llm_key_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QAClaim(BaseModel):
    claim: str = Field(description="The factual claim.")
    cited_file: str = Field(description="The exact file path cited.")
    cited_symbol: str = Field(default="", description="The specific function or class cited.")

class QAResponse(BaseModel):
    answer: str = Field(description="The generated answer to the question.")
    claims: List[QAClaim] = Field(description="List of factual claims made in the answer, with 'claim', 'cited_file', and optionally 'cited_symbol'.")


# ─── Lightweight keyword-based file retriever (no ChromaDB needed) ───────────

def _score_file_relevance(question: str, file: Dict[str, str]) -> float:
    """
    Score a file's relevance to a question using keyword overlap.
    Returns a float — higher = more relevant.
    """
    q_lower = question.lower()
    path = file.get("path", "").lower()
    content = (file.get("content") or "")[:3000].lower()  # first 3KB

    # Extract meaningful keywords from question (skip stop words)
    stops = {"what", "where", "how", "does", "the", "a", "an", "is", "are",
              "in", "of", "to", "do", "for", "this", "that", "which", "with"}
    keywords = [w for w in re.findall(r'\b\w{3,}\b', q_lower) if w not in stops]

    score = 0.0
    for kw in keywords:
        # Strong signal: keyword appears in file path
        if kw in path:
            score += 3.0
        # Medium signal: keyword appears in content
        if kw in content:
            score += 1.0

    return score


def _get_relevant_file_snippets(question: str, downloaded_files: List[Dict[str, str]], top_k: int = 5) -> str:
    """
    Return the top-k most question-relevant file snippets as a formatted context string.
    This replaces ChromaDB with a zero-dependency keyword-match approach.
    """
    if not downloaded_files:
        return ""

    scored = [
        (f, _score_file_relevance(question, f))
        for f in downloaded_files
        if f.get("content")  # skip empty/binary files
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    top_files = [f for f, score in scored[:top_k] if score > 0]

    if not top_files:
        return ""

    snippets = []
    for f in top_files:
        path = f.get("path", "unknown")
        content = (f.get("content") or "")[:1500]  # first 1.5KB per file
        snippets.append(f"--- {path} ---\n{content}\n")

    return "\n".join(snippets)


# ─── Q&A Agent ────────────────────────────────────────────────────────────────

class QAAgent:
    def __init__(self):
        self.verifier = Verifier()

    def index_repository(self, repo_name: str, files: List[Dict[str, str]], generated_docs: str, session_token: str | None = None):
        """No-op. Indexing is handled on-demand via keyword retrieval in answer_question."""
        pass

    async def answer_question(
        self,
        repo_name: str,
        question: str,
        graph: Dict[str, Any],
        downloaded_files: List[Dict[str, str]],
        session_token: str | None = None
    ) -> Dict[str, Any]:
        """
        Answers a question using two context sources:
          1. Architecture summary + top files from the graph (structural context)
          2. Actual file content snippets matched by question keywords (semantic context)
        """

        # ── Context 1: Graph structural summary ──────────────────────────────
        context_text = f"Repository: {repo_name}\n"
        if "summary" in graph:
            context_text += f"Architecture Summary:\n{graph['summary']}\n\n"
        else:
            context_text += "Architecture summary not available.\n\n"

        context_text += "Top Files by importance (dependents count):\n"
        sorted_nodes = sorted(
            graph.get("nodes", []),
            key=lambda x: x.get("dependents_count", 0),
            reverse=True
        )[:10]
        for node in sorted_nodes:
            context_text += f"- {node.get('id', 'Unknown')} (dependents: {node.get('dependents_count', 0)})\n"

        # ── Context 2: Relevant file snippets (keyword retrieval) ─────────────
        file_snippets = _get_relevant_file_snippets(question, downloaded_files, top_k=5)
        if file_snippets:
            context_text += f"\nRelevant File Snippets:\n{file_snippets}"
            logger.info(f"Q&A: injected {min(5, len(downloaded_files))} relevant file snippets as context")
        else:
            logger.info("Q&A: no relevant file snippets found — answering from graph summary only")

        # ── Generate structured answer ────────────────────────────────────────
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a senior software engineer helping someone understand a codebase.
Use the provided context — which includes an architecture summary AND actual file code snippets — to give a precise, specific answer.
Do NOT give vague or generic answers. If you see relevant code in the snippets, quote it.
You MUST output a structured list of claims with exact file citations from the context.
Inject inline citations directly into your `answer` text after each sentence: format as `[filepath]`.
If context is insufficient, say what you know and what you cannot determine."""),
            ("human", "Context:\n{context}\n\nQuestion: {question}")
        ])

        try:
            llm = llm_key_pool.get_llm(session_token, temperature=0.0)
            structured_llm = llm.with_structured_output(QAResponse)
            chain = prompt | structured_llm
            logger.info("Generating Q&A response...")
            qa_res: QAResponse = await chain.ainvoke({"context": context_text, "question": question})
        except Exception as e:
            logger.warning(f"Failed to generate QA response: {e}")
            return {
                "answer": "I'm sorry, I cannot answer right now — the AI API is unavailable. Please try again in a moment.",
                "claims": []
            }

        # ── Verify claims against graph ───────────────────────────────────────
        claims_dicts = [c.model_dump() for c in qa_res.claims]
        verified_claims = await self.verifier.verify_claims_async(
            claims_dicts, graph, downloaded_files, session_token
        )

        return {
            "answer": qa_res.answer,
            "claims": verified_claims
        }
