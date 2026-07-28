import os
import time
import logging
from typing import Optional
import httpx
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KeyPool:
    def __init__(self):
        self.keys = []
        
        # Load from GITHUB_TOKEN_1, GITHUB_TOKEN_2, etc.
        i = 1
        while True:
            token = os.environ.get(f"GITHUB_TOKEN_{i}")
            if not token:
                # Fallback to older GITHUB_TOKEN format
                if i == 1 and os.environ.get("GITHUB_TOKEN"):
                    token = os.environ.get("GITHUB_TOKEN")
                else:
                    break
            
            self.keys.append({
                "token": token,
                "reset_time": 0,
                "remaining": -1, # Unknown initially
            })
            i += 1
            
        if not self.keys:
            logger.warning("No GITHUB_TOKEN variables found in environment. Proceeding unauthenticated.")

    def get_best_key(self) -> Optional[str]:
        """Returns the token with the most remaining requests, or one that has reset."""
        now = time.time()
        
        # 1. Any key with known remaining > 0
        available_keys = [k for k in self.keys if (k["remaining"] > 10 or k["remaining"] == -1) and k["reset_time"] < now]
        
        if available_keys:
            # Sort by remaining, putting -1 (unknown) at the end, so we prefer known good keys
            return sorted(available_keys, key=lambda k: k["remaining"], reverse=True)[0]["token"]
            
        # 2. All keys exhausted. Return the one resetting soonest (but it will probably fail)
        if self.keys:
            best_key = sorted(self.keys, key=lambda k: k["reset_time"])[0]
            if best_key["reset_time"] > now:
                # If we absolutely have to wait, we might as well just return None or raise an exception
                pass
            return best_key["token"]
            
        return None
        
    def update_key_status(self, token: str, remaining: int, reset_time: int):
        for k in self.keys:
            if k["token"] == token:
                k["remaining"] = remaining
                k["reset_time"] = reset_time
                break

    def get_status(self):
        now = time.time()
        return [
            {
                "id": i+1,
                "remaining": k["remaining"],
                "reset_in_seconds": max(0, int(k["reset_time"] - now)) if k["reset_time"] > now else 0
            }
            for i, k in enumerate(self.keys)
        ]

# Global instance
key_pool = KeyPool()
