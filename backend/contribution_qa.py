import logging
from typing import Dict, Any, List, Optional
from langchain_core.prompts import ChatPromptTemplate
from llm_key_pool import llm_key_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ContributionQA:
    """
    Lightweight Q&A handler scoped to a single contribution context.
    Used inside the Contribution Wizard when the user asks "I don't understand this".
    Different from qa_agent.py (which is whole-repo Q&A) because:
    - Context is scoped to ONE issue and ONE contribution guide
    - Answers are always beginner-friendly (never assume prior knowledge)
    - Grounded in the specific files relevant to the issue
    """

    async def answer(
        self,
        question: str,
        issue_title: str,
        understanding: str,
        modifications: List[Dict[str, Any]],
        target_files: List[str],
        relevant_file_contents: List[Dict[str, str]],
        session_token: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Answers a beginner's question about their contribution in progress.
        
        Returns: {"answer": str, "cited_file": str | None}
        """
        # Build context from relevant files
        file_context = ""
        for f in relevant_file_contents[:5]:
            file_context += f"\n--- {f['path']} ---\n"
            file_context += f["content"][:2000]

        import json
        modifications_str = json.dumps(modifications, indent=2)

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a blunt, highly technical mentor. You do not soften feedback to be encouraging. You are allergic to vague claims and filler text.

The person is working on a specific GitHub issue and has a question. Your job is to answer it with extreme conciseness and precision.

Rules:
1. NEVER say "Welcome to open source" or use any encouraging filler.
2. Be extremely brief. Give the answer immediately.
3. If they need to change code, format it EXACTLY as: "Change line X in file Y to: `new code`" or provide a minimal, exact code diff.
4. Do not explain *why* unless asked. Just tell them *what* to do.
5. If you don't know the answer with certainty, say so bluntly.
"""),
            ("human", """The person is working on this GitHub issue:
Issue: {issue_title}

What the issue is about:
{understanding}

Proposed Modifications:
{modifications}

Files involved:
{target_files}

Relevant file contents for reference:
{file_context}

---

Their question: {question}

Please answer their question in a beginner-friendly way, citing specific files/functions where relevant.
""")
        ])

        try:
            llm = llm_key_pool.get_llm(session_token, temperature=0.3)
            chain = prompt | llm
            result = chain.invoke({
                "issue_title": issue_title,
                "understanding": understanding,
                "modifications": modifications_str,
                "target_files": ", ".join(target_files) if target_files else "Not specified",
                "file_context": file_context or "No file contents available.",
                "question": question,
            })
            if hasattr(result, "content"):
                if isinstance(result.content, str):
                    answer_text = result.content
                elif isinstance(result.content, list):
                    answer_text = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in result.content)
                else:
                    answer_text = str(result.content)
            else:
                answer_text = str(result)
                
            return {
                "answer": answer_text,
                "cited_file": target_files[0] if target_files else None
            }
        except Exception as e:
            logger.error(f"ContributionQA failed: {e}")
            return {
                "answer": "I'm sorry, the AI service is currently unavailable. Please try again in a moment.",
                "cited_file": None
            }


# Global instance
contribution_qa = ContributionQA()
