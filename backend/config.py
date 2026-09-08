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
MAX_FILES = 1000        # Absolute hard cap — repos with >1000 source files are data repos, not codebases
MAX_LOC = 150000        # Max lines of code

# Smart Sampling
# When a repo's filtered file count exceeds this, we intelligently prioritize files
# rather than hard-rejecting. Entry points + core modules are always included.
# The UI shows a transparent disclosure banner so results are never "fake".
# This replaces the old SMART_SAMPLE_LIMIT which silently dropped files with no disclosure.
SMART_SAMPLE_TARGET = 350  # Max files sent through the full analysis pipeline

# AST parser file size limit — files larger than this are truncated (not skipped).
# We always parse the first PARSE_SIZE_LIMIT bytes. Top of file = imports + class/function
# declarations = the architecturally important parts. Stats (LOC, function counts) are still
# computed for the FULL file before truncation so numbers are never falsified.
PARSE_SIZE_LIMIT = 50 * 1024   # 50 KB

# Language support — TWO TIERS:
#   Tier 1 (Full AST — tree-sitter): Python, JavaScript, TypeScript
#     → nodes, imports, call graph, entry points
#   Tier 2 (Import-only — regex fallback): all others below
#     → only top-level import statements extracted; no call graph or node list
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

# ─── Model Registry ───────────────────────────────────────────────────────────
# Centralised model names. Update HERE when providers deprecate a model.
# Do NOT hardcode model strings anywhere else in the codebase.
MODEL_REGISTRY = {
    # Groq — fast inference, used as default fallback
    "gemini": os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
    "groq": os.getenv("GROQ_MODEL", "mixtral-8x7b-32768"),

    # OpenAI — highest quality, used when an openai key is in the pool
    "openai": os.getenv("OPENAI_MODEL", "gpt-4o"),

    # Anthropic — alternative premium model
    "anthropic": os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022"),
}
