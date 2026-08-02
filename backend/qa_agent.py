import logging
import chromadb
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from verifier import Verifier
from config import GEMINI_API_KEY
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
        self.chroma_client = chromadb.PersistentClient(path="./chroma_db")
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        
        self.verifier = Verifier()

    def index_repository(self, repo_name: str, files: List[Dict[str, str]], generated_docs: str):
        """Chunks and indexes the code and generated docs into ChromaDB."""
        collection_name = repo_name.replace("/", "_").replace(".", "_")
        try:
            self.chroma_client.delete_collection(collection_name)
        except Exception:
            pass
            
        collection = self.chroma_client.create_collection(name=collection_name)
        
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        
        docs = []
        metadatas = []
        ids = []
        
        # Index Code
        for f in files:
            chunks = text_splitter.split_text(f["content"])
            for i, chunk in enumerate(chunks):
                docs.append(chunk)
                metadatas.append({"source": f["path"], "type": "code"})
                ids.append(f"{f['path']}_chunk_{i}")
                
        # Index Docs
        if generated_docs:
            doc_chunks = text_splitter.split_text(generated_docs)
            for i, chunk in enumerate(doc_chunks):
                docs.append(chunk)
                metadatas.append({"source": "generated_docs", "type": "doc"})
                ids.append(f"doc_chunk_{i}")
                
        # We need to compute embeddings using Gemini Embeddings and add them
        # chromadb uses default embedding function if not provided, but we want Gemini.
        # So we can compute them directly or wrap Gemini embeddings in Chroma's interface.
        # For simplicity, we just use Langchain's Chroma wrapper or compute them here.
        # Langchain's GoogleGenerativeAIEmbeddings:
        if docs:
            embedded_docs = self.embeddings.embed_documents(docs)
            collection.add(
                embeddings=embedded_docs,
                documents=docs,
                metadatas=metadatas,
                ids=ids
            )
        logger.info(f"Indexed {len(docs)} chunks for repo {repo_name}.")

    async def answer_question(self, repo_name: str, question: str, graph: Dict[str, Any], downloaded_files: List[Dict[str, str]], session_token: str | None = None) -> Dict[str, Any]:
        """Answers a question, citing files and verifying the claims."""
        collection_name = repo_name.replace("/", "_").replace(".", "_")
        try:
            collection = self.chroma_client.get_collection(name=collection_name)
        except Exception:
            return {"error": "Repository not indexed."}
            
        # Retrieve
        query_embedding = self.embeddings.embed_query(question)
        results = collection.query(query_embeddings=[query_embedding], n_results=5)
        
        context_chunks = results["documents"][0]
        context_sources = [m["source"] for m in results["metadatas"][0]]
        
        context_text = ""
        for i, chunk in enumerate(context_chunks):
            context_text += f"\n--- Source: {context_sources[i]} ---\n{chunk}\n"
            
        # Generate Answer
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a codebase Q&A assistant.
Use the provided context to answer the user's question.
You MUST output a structured list of claims made in your answer, citing the exact file path from the context.
CRITICAL: You MUST also inject inline citations directly into your `answer` text immediately after the sentence they support.
Format the inline citation exactly as `[filename]` (e.g. `[src/app.py]`) where filename is the cited file. Do not put citations at the end of the paragraph, inject them inline.
"""),
            ("human", """Context:
{context}

Question: {question}
""")
        ])
        
        llm = llm_key_pool.get_llm(session_token, temperature=0.0)
        structured_llm = llm.with_structured_output(QAResponse)
        chain = prompt | structured_llm
        logger.info("Generating Q&A response...")
        qa_res: QAResponse = await chain.ainvoke({"context": context_text, "question": question})
        
        # Convert Pydantic claims to dicts for verifier
        claims_dicts = [c.model_dump() for c in qa_res.claims]
        
        # Verify Claims
        verified_claims = await self.verifier.verify_claims_async(claims_dicts, graph, downloaded_files, session_token)
        
        return {
            "answer": qa_res.answer,
            "claims": verified_claims
        }
