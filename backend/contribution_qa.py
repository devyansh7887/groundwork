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
        what_needs_to_change: str,
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

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a patient, friendly open-source mentor helping a beginner make their first contribution.

The person is working on a specific GitHub issue and has a question. Your job is to answer it clearly and simply.

Rules:
1. Always assume the person has basic coding knowledge but has NEVER contributed to open source before.
2. If the question is about code, cite the specific file and line/function where the answer is found.
3. Use plain language. If you need to use a technical term, explain it with an analogy.
4. Be encouraging but honest. If you don't know the answer with certainty, say so.
5. Keep answers concise — 2-4 paragraphs maximum.
6. Never tell them to "just Google it" or similar dismissals.
"""),
            ("human", """The person is working on this GitHub issue:
Issue: {issue_title}

What the issue is about:
{understanding}

What needs to change:
{what_needs_to_change}

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
                "what_needs_to_change": what_needs_to_change,
                "target_files": ", ".join(target_files) if target_files else "Not specified",
                "file_context": file_context or "No file contents available.",
                "question": question,
            })
            answer_text = result.content if hasattr(result, "content") else str(result)
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
