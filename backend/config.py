import os
from dotenv import load_dotenv

load_dotenv()

# Environment Variables
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if GITHUB_TOKEN and "your_" in GITHUB_TOKEN:
    GITHUB_TOKEN = None

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY or "your_" in GEMINI_API_KEY:
    GEMINI_API_KEY = "dummy_key_to_prevent_crash_on_startup"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY or "your_" in GROQ_API_KEY:
    GROQ_API_KEY = "dummy_key_to_prevent_crash_on_startup"

# Hard Constraints from Spec
MAX_FILES = 300
MAX_LOC = 150000
SUPPORTED_LANGUAGES = [
    "Python", 
    "JavaScript", 
    "TypeScript"
]
DEFAULT_BRANCH_ONLY = True
PUBLIC_REPOS_ONLY = True

# Tree-sitter file extensions mapping
LANGUAGE_EXTENSIONS = {
    "Python": [".py"],
    "JavaScript": [".js", ".jsx", ".mjs", ".cjs"],
    "TypeScript": [".ts", ".tsx"]
}
