import os
from dotenv import load_dotenv

load_dotenv()

# Environment Variables
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if GITHUB_TOKEN and "your_" in GITHUB_TOKEN:
    GITHUB_TOKEN = None

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY and "your_" in GEMINI_API_KEY:
    GEMINI_API_KEY = None

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if GROQ_API_KEY and "your_" in GROQ_API_KEY:
    GROQ_API_KEY = None

# Hard Constraints
MAX_FILES = 500          # Absolute hard cap — repos larger than this are truly too big
MAX_LOC = 150000          # Max lines of code
SMART_SAMPLE_LIMIT = 300  # If repo has more files than this, smart-sample the most important ones
SUPPORTED_LANGUAGES = [
    "Python", 
    "JavaScript", 
    "TypeScript",
    "Java",
    "Kotlin",
    "Go",
    "Rust",
    "C",
    "C++",
    "Ruby",
    "PHP",
    "Swift",
    "C#",
    "HTML",
    "CSS",
    "Shell"
]
DEFAULT_BRANCH_ONLY = True
PUBLIC_REPOS_ONLY = True

# Tree-sitter file extensions mapping
LANGUAGE_EXTENSIONS = {
    "Python": [".py"],
    "JavaScript": [".js", ".jsx", ".mjs", ".cjs"],
    "TypeScript": [".ts", ".tsx"],
    "Java": [".java", ".gradle"],
    "Kotlin": [".kt", ".kts"],
    "Go": [".go"],
    "Rust": [".rs"],
    "C": [".c", ".h"],
    "C++": [".cpp", ".cc", ".cxx", ".hpp", ".hxx"],
    "Ruby": [".rb"],
    "PHP": [".php"],
    "Swift": [".swift"],
    "C#": [".cs"],
    "HTML": [".html", ".htm", ".xml"],
    "CSS": [".css", ".scss", ".sass"],
    "Shell": [".sh", ".bash"]
}
