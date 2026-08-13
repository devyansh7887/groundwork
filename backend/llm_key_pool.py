import os
import time
import logging
import threading
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LLMKeyPool:
    def __init__(self):
        self.keys = []
        self._lock = threading.Lock()
        
        # Load Groq Keys
        self._load_keys("GROQ_API_KEY", "groq")
        
        # Load Gemini Keys
        self._load_keys("GEMINI_API_KEY", "gemini")
        
        # Load OpenAI Keys
        self._load_keys("OPENAI_API_KEY", "openai")
        
        # Load Anthropic Keys
        self._load_keys("ANTHROPIC_API_KEY", "anthropic")
            
        if not self.keys:
            logger.warning("No LLM keys found in environment. AI drafting will be unavailable unless a session token is provided.")

    def _is_valid_token(self, token: str, key_type: str) -> bool:
        if not token:
            return False
        token = token.strip(" \t\n\r\"'")
        if not token or "your_" in token or "dummy" in token:
            return False
        if key_type == "gemini" and not (token.startswith("AIza") or token.startswith("AQ.")):
            return False
        if key_type == "groq" and not token.startswith("gsk_"):
            return False
        if key_type == "anthropic" and not token.startswith("sk-ant-"):
            return False
        return True

    def _load_keys(self, base_env_name: str, key_type: str):
        # Check base env (e.g. GROQ_API_KEY)
        base_val = os.environ.get(base_env_name)
        if base_val:
            for val in base_val.split(','):
                clean_val = val.strip(" \t\n\r\"'")
                if clean_val and self._is_valid_token(clean_val, key_type):
                    self.keys.append({"token": clean_val, "type": key_type, "reset_time": 0, "remaining": -1})
            
        # Check GROQ_API_KEY_1, GROQ_API_KEY_2, etc.
        i = 1
        while True:
            token = os.environ.get(f"{base_env_name}_{i}")
            if not token:
                break
            for val in token.split(','):
                clean_val = val.strip(" \t\n\r\"'")
                if clean_val and self._is_valid_token(clean_val, key_type):
                    self.keys.append({"token": clean_val, "type": key_type, "reset_time": 0, "remaining": -1})
            i += 1

    def _determine_key_type(self, token: str) -> str:
        if token.startswith("gsk_"):
            return "groq"
        if token.startswith("AIza") or token.startswith("AQ."):
            return "gemini"
        if token.startswith("sk-ant-"):
            return "anthropic"
        if token.startswith("sk-proj-") or token.startswith("sk-"):
            return "openai"
        return "unknown"

    def get_best_key(self) -> Optional[Dict[str, Any]]:
        """Returns the healthiest key dictionary from the pool."""
        now = time.time()
        
        with self._lock:
            available_keys = [k for k in self.keys if (k["remaining"] > 0 or k["remaining"] == -1) and k["reset_time"] < now]
            
            if available_keys:
                # Prioritize gemini due to massive rate limits and 1M context window
                def sort_key(k):
                    type_score = 1 if k["type"] == "gemini" else 0
                    return (type_score, k["remaining"])
                return sorted(available_keys, key=sort_key, reverse=True)[0]
                
            if self.keys:
                # All exhausted, return the one resetting soonest
                return sorted(self.keys, key=lambda k: k["reset_time"])[0]
            
            return None

    def get_llm(self, session_token: Optional[str] = None, temperature: float = 0.2, max_retries: int = 2) -> Any:
        """Instantiates and returns the correct LangChain model based on the available or provided key."""
        token_to_use = None
        key_type = "groq" # Default preference
        
        if session_token:
            if not isinstance(session_token, str) or len(session_token) < 10:
                raise HTTPException(status_code=400, detail="Malformed session token")
            
            if session_token.startswith("gsk_") or session_token.startswith("AIza") or session_token.startswith("sk-"):
                token_to_use = session_token
                key_type = self._determine_key_type(token_to_use)
            else:
                raise HTTPException(status_code=400, detail="Invalid session token prefix. Must be gsk_, AIza, sk-proj-, or sk-ant-")
        else:
            best = self.get_best_key()
            if best:
                token_to_use = best["token"]
                key_type = best["type"]
                
        if not token_to_use:
            raise ValueError("No valid LLM API key available in pool and no valid session token provided.")
            
        if key_type == "groq":
            return ChatGroq(
                model="llama-3.3-70b-versatile",
                groq_api_key=token_to_use,
                temperature=temperature,
                max_retries=max_retries,
                max_tokens=8192
            )
        elif key_type == "gemini":
            return ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=token_to_use,
                temperature=temperature,
                max_retries=max_retries,
                max_output_tokens=8192
            )
        elif key_type == "openai":
            return ChatOpenAI(
                model="gpt-4o",
                api_key=token_to_use,
                temperature=temperature,
                max_retries=max_retries
            )
        elif key_type == "anthropic":
            return ChatAnthropic(
                model="claude-3-5-sonnet-20240620",
                api_key=token_to_use,
                temperature=temperature,
                max_retries=max_retries
            )
        else:
            raise ValueError(f"Unsupported LLM key type: {key_type}")

    def mark_rate_limit(self, token: str, retry_after: int = 60):
        """Marks a key as exhausted for a certain period."""
        with self._lock:
            for k in self.keys:
                if k["token"] == token:
                    k["remaining"] = 0
                    k["reset_time"] = time.time() + retry_after
                    logger.warning(f"LLM Key marked as rate-limited. Resets in {retry_after}s.")
                    break

    def get_status(self):
        """Returns the current pool status for UI rendering."""
        now = time.time()
        with self._lock:
            return [
                {
                    "id": f"{k['type']}-{i+1}",
                    "remaining": k["remaining"],
                    "reset_in_seconds": max(0, int(k["reset_time"] - now)) if k["reset_time"] > now else 0
                }
                for i, k in enumerate(self.keys)
            ]

# Global instance
llm_key_pool = LLMKeyPool()
