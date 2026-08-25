import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
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

class QAAgent:
    def __init__(self):
        self.verifier = Verifier()

    def index_repository(self, repo_name: str, files: List[Dict[str, str]], generated_docs: str, session_token: str | None = None):
        """No-op. We no longer use ChromaDB to avoid rate limits on large repos."""
        pass

    async def answer_question(self, repo_name: str, question: str, graph: Dict[str, Any], downloaded_files: List[Dict[str, str]], session_token: str | None = None) -> Dict[str, Any]:
        """Answers a question using the graph summary as context."""
        
        # Build context from graph summary
        context_text = f"Repository: {repo_name}\n"
        if "summary" in graph:
            context_text += f"Architecture Summary:\n{graph['summary']}\n\n"
        else:
            context_text += "Architecture summary not available.\n\n"
            
        context_text += "Top Files by dependents:\n"
        # Just list the top 15 files to give the LLM some file context
        sorted_files = sorted(
            graph.get("nodes", []), 
            key=lambda x: x.get("dependents_count", 0), 
            reverse=True
        )[:15]
        for f in sorted_files:
            context_text += f"- {f.get('id', 'Unknown')} (Dependents: {f.get('dependents_count', 0)})\n"

        # Generate Answer
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a codebase Q&A assistant.
Use the provided architectural context to answer the user's question.
You MUST output a structured list of claims made in your answer, citing the exact file path from the context.
CRITICAL: You MUST also inject inline citations directly into your `answer` text immediately after the sentence they support.
Format the inline citation exactly as `[filename]` (e.g. `[src/app.py]`) where filename is the cited file. Do not put citations at the end of the paragraph, inject them inline.
If the context doesn't contain enough specific details to fully answer the question, state what you DO know based on the architecture summary, and acknowledge what you cannot see.
"""),
            ("human", """Context:
{context}

Question: {question}
""")
        ])
        
        try:
            llm = llm_key_pool.get_llm(session_token, temperature=0.0)
            structured_llm = llm.with_structured_output(QAResponse)
            chain = prompt | structured_llm
            logger.info("Generating Q&A response from graph context...")
            qa_res: QAResponse = await chain.ainvoke({"context": context_text, "question": question})
        except Exception as e:
            logger.warning(f"Failed to generate QA response: {e}")
            return {
                "answer": "I'm sorry, I cannot answer right now because no valid AI keys are available on the server. Please configure your Groq or Gemini keys.",
                "claims": []
            }
        
        # Convert Pydantic claims to dicts for verifier
        claims_dicts = [c.model_dump() for c in qa_res.claims]
        
        # Verify Claims
        verified_claims = await self.verifier.verify_claims_async(claims_dicts, graph, downloaded_files, session_token)
        
        return {
            "answer": qa_res.answer,
            "claims": verified_claims
        }
