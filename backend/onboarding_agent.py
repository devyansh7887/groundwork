import asyncio
import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from llm_key_pool import llm_key_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ReadingStep(BaseModel):
    file_path: str = Field(description="The exact file path to read.")
    rationale: str = Field(description="Why this file should be read at this stage.")
    concepts: List[str] = Field(description="Key concepts to learn from this file.")

class OnboardingPath(BaseModel):
    role: str
    level: str
    path: List[ReadingStep] = Field(description="Ordered sequence of files to read.")

class OnboardingAgent:
    def __init__(self):
        pass

    async def generate_path(self, role: str, level: str, graph: Dict[str, Any], narrative: str, session_token: str | None = None) -> OnboardingPath:
        logger.info(f"Generating onboarding path for {level} {role}...")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert engineering manager onboarding a new hire.
Based on the provided architecture narrative and graph (which includes entry points and central files), create an ordered reading path through the codebase.
Tailor the complexity and focus areas to the declared role and experience level.
Only cite files that exist in the provided graph.
"""),
            ("human", """Role: {role}
Level: {level}

Architecture Narrative:
{narrative}

Key Entry Points: {entry_points}
Central Files (Highly connected): {central_files}

Generate the ordered reading path.
""")
        ])
        
        entry_points = [ep.get("id", "").split(":")[0] for ep in graph.get("entry_points", [])]
        
        # Calculate centrality again for prompt context
        counts = {f: 0 for f in graph.get("files", [])}
        for imp in graph.get("imports", []):
            if imp.get("source") in counts: counts[imp.get("source")] += 1
        for call in graph.get("calls", []):
            if call.get("caller_file") in counts: counts[call.get("caller_file")] += 1
        sorted_files = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        central_files = [f[0] for f in sorted_files[:5]]
        
        llm = llm_key_pool.get_llm(session_token, temperature=0.2)
        structured_llm = llm.with_structured_output(OnboardingPath)
        chain = prompt | structured_llm
        
        invoke_kwargs = {
            "role": role,
            "level": level,
            "narrative": narrative,
            "entry_points": ", ".join(set(entry_points)),
            "central_files": ", ".join(central_files)
        }

        # chain.invoke is a blocking call — run in a thread to avoid blocking the event loop
        result: OnboardingPath = await asyncio.to_thread(chain.invoke, invoke_kwargs)
        
        return result
