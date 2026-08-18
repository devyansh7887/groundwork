import os
import re
import json
import logging
import gc
from typing import Dict, Any, List
from collections import Counter
from tree_sitter import Language, Parser
import tree_sitter_python
import tree_sitter_javascript
from config import PARSE_SIZE_LIMIT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load tree-sitter languages
PY_LANGUAGE = Language(tree_sitter_python.language())
JS_LANGUAGE = Language(tree_sitter_javascript.language())

# Regex patterns for fast stat counting (used on ALL files regardless of size)
# These count NAMED top-level declarations only — matches industry standard "function count"
_PY_FUNC_RE = re.compile(r'^(?:async\s+)?def\s+\w+', re.MULTILINE)
_PY_CLASS_RE = re.compile(r'^class\s+\w+', re.MULTILINE)
_JS_FUNC_RE = re.compile(r'^(?:export\s+)?(?:async\s+)?function\s+\w+', re.MULTILINE)
_JS_CLASS_RE = re.compile(r'^(?:export\s+)?class\s+\w+', re.MULTILINE)
_JS_EXPORT_CONST_FN_RE = re.compile(r'^(?:export\s+)?const\s+\w+\s*=\s*(?:async\s*)?\(', re.MULTILINE)


class Cartographer:
    def __init__(self):
        self.parsers = {
            "Python": Parser(PY_LANGUAGE),
            "JavaScript": Parser(JS_LANGUAGE),
            "TypeScript": Parser(JS_LANGUAGE)
        }
        # 1-second C-level parse timeout — prevents tree-sitter from busy-looping
        for p in self.parsers.values():
            if hasattr(p, 'timeout_micros'):
                p.timeout_micros = 1_000_000

    def determine_language(self, file_path: str) -> str:
        if file_path.endswith(".py"):
            return "Python"
        elif file_path.endswith((".ts", ".tsx")):
            return "TypeScript"
        elif file_path.endswith((".js", ".jsx", ".mjs", ".cjs")):
            return "JavaScript"
        return "Unknown"

    def count_stats(self, file_path: str, content_str: str) -> Dict[str, int]:
        """
        Fast, regex-based stat counting that runs on the FULL file content —
        never truncated. Returns industry-standard metric counts:
        - sloc: non-blank, non-comment lines (Source Lines of Code)
        - public_functions: named top-level functions + classes (NOT arrow functions/callbacks)
        """
        lang = self.determine_language(file_path)
        lines = content_str.splitlines()

        # SLOC: non-blank, non-comment lines
        sloc = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Skip pure comment lines
            if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('*') or stripped.startswith('/*'):
                continue
            sloc += 1

        # Public function count — named top-level declarations only
        pub_funcs = 0
        if lang == "Python":
            pub_funcs = len(_PY_FUNC_RE.findall(content_str)) + len(_PY_CLASS_RE.findall(content_str))
        elif lang in ("JavaScript", "TypeScript"):
            pub_funcs = (
                len(_JS_FUNC_RE.findall(content_str)) +
                len(_JS_CLASS_RE.findall(content_str)) +
                len(_JS_EXPORT_CONST_FN_RE.findall(content_str))
            )

        return {"sloc": sloc, "total_lines": len(lines), "public_functions": pub_funcs}

    def parse_file(self, file_path: str, content: bytes) -> Dict[str, Any]:
        """
        Parses a file and extracts graph nodes and edges.
        
        IMPORTANT — two-pass design:
        Pass 1 (always): count_stats() runs on the FULL content string for accurate metrics.
        Pass 2 (AST): tree-sitter runs on content truncated to PARSE_SIZE_LIMIT to stay
                      within Render's 512 MB RAM. This affects graph QUALITY only — never
                      the headline stats shown to users.
        """
        import time
        lang = self.determine_language(file_path)
        parser = self.parsers.get(lang)
        
        nodes = []
        imports = []
        calls = []
        entry_points = []
        
        # ── Guard: long-line check — skip minified files (virtually no newlines)
        try:
            if content.count(b'\n') < 3 and len(content) > 500:
                parser = None
            else:
                text = content.decode('utf8', errors='ignore')
                if any(len(line) > 1000 for line in text.splitlines()):
                    parser = None
        except Exception:
            parser = None

        if parser:
            # Truncate for AST parsing only — stats were already computed from full content
            parse_content = content[:PARSE_SIZE_LIMIT] if len(content) > PARSE_SIZE_LIMIT else content
            was_truncated = len(content) > PARSE_SIZE_LIMIT

            try:
                deadline = time.monotonic() + 2.0  # 2-second wall-clock budget per file
                tree = parser.parse(parse_content)
                
                # Iterative BFS traversal — avoids Python RecursionError on deep ASTs
                stack = [tree.root_node]
                while stack:
                    if time.monotonic() > deadline:
                        break
                    node = stack.pop()
                    if lang == "Python":
                        self._extract_python_features(node, file_path, parse_content, nodes, imports, calls, entry_points)
                    else:
                        self._extract_js_features(node, file_path, parse_content, nodes, imports, calls, entry_points)
                    stack.extend(reversed(node.children))

                if was_truncated:
                    logger.debug(f"AST truncated at {PARSE_SIZE_LIMIT//1024}KB for {file_path} (stats unaffected)")
                    
            except Exception as e:
                logger.error(f"Tree-sitter failed on {file_path}: {e}")
        else:
            # Regex fallback for imports for unsupported languages (Java, Kotlin, Go, C++, etc)
            text = content.decode('utf8', errors='ignore')
            for i, line in enumerate(text.splitlines()):
                line_str = line.strip()
                if line_str.startswith("import ") or line_str.startswith("#include"):
                    target = line_str.replace("import ", "").replace("#include ", "").replace(";", "").replace('"', '').replace('<', '').replace('>', '').strip()
                    if target:
                        imports.append({
                            "source": file_path,
                            "target_module": target,
                            "statement": line_str,
                            "line": i + 1
                        })
        
        return {
            "file": file_path,
            "language": lang,
            "nodes": nodes,
            "imports": imports,
            "calls": calls,
            "entry_points": entry_points
        }

    def _extract_python_features(self, node, file_path, content, nodes, imports, calls, entry_points):
        # Functions and Classes
        if node.type in ["function_definition", "class_definition"]:
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte].decode('utf8')
                nodes.append({
                    "id": f"{file_path}:{name}",
                    "type": node.type,
                    "name": name,
                    "line": node.start_point[0] + 1
                })
                # Check for FastAPI/Flask decorators as entry points
                if node.type == "function_definition":
                    for child in node.children:
                        if child.type == "decorator":
                            entry_points.append({
                                "id": f"{file_path}:{name}",
                                "reason": "decorator_found",
                                "decorator": content[child.start_byte:child.end_byte].decode('utf8')
                            })
                            
        # Imports
        elif node.type in ["import_statement", "import_from_statement"]:
            modules = []
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        modules.append(content[child.start_byte:child.end_byte].decode('utf8'))
            elif node.type == "import_from_statement":
                module_name_node = node.child_by_field_name("module_name")
                if module_name_node:
                    modules.append(content[module_name_node.start_byte:module_name_node.end_byte].decode('utf8'))
                    
            stmt = content[node.start_byte:node.end_byte].decode('utf8')
            for mod in modules:
                imports.append({
                    "source": file_path,
                    "target_module": mod,
                    "statement": stmt,
                    "line": node.start_point[0] + 1
                })
            if not modules:
                imports.append({
                    "source": file_path,
                    "target_module": "",
                    "statement": stmt,
                    "line": node.start_point[0] + 1
                })
            
        # Call graph edges
        elif node.type == "call":
            func_node = node.child_by_field_name("function")
            if func_node:
                callee_name = content[func_node.start_byte:func_node.end_byte].decode('utf8')
                calls.append({
                    "caller_file": file_path,
                    "callee": callee_name,
                    "line": node.start_point[0] + 1
                })
                
        # Entry point: if __name__ == "__main__"
        elif node.type == "if_statement":
            condition = node.child_by_field_name("condition")
            if condition:
                cond_text = content[condition.start_byte:condition.end_byte].decode('utf8')
                if "__name__" in cond_text and "__main__" in cond_text:
                    entry_points.append({
                        "id": f"{file_path}:main_block",
                        "reason": "main_block",
                        "line": node.start_point[0] + 1
                    })

    def _extract_js_features(self, node, file_path, content, nodes, imports, calls, entry_points):
        # Named functions and classes ONLY — not bare arrow functions
        if node.type in ["function_declaration", "class_declaration", "method_definition"]:
            name_node = node.child_by_field_name("name")
            name = "anonymous"
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte].decode('utf8')
            nodes.append({
                "id": f"{file_path}:{name}",
                "type": node.type,
                "name": name,
                "line": node.start_point[0] + 1
            })

        # Named arrow functions assigned to exported const — these ARE public API
        elif node.type == "export_statement":
            # export const fn = () => {}
            for child in node.children:
                if child.type == "lexical_declaration":
                    for decl in child.children:
                        if decl.type == "variable_declarator":
                            name_node = decl.child_by_field_name("name")
                            val_node = decl.child_by_field_name("value")
                            if name_node and val_node and val_node.type in ("arrow_function", "function"):
                                name = content[name_node.start_byte:name_node.end_byte].decode('utf8')
                                nodes.append({
                                    "id": f"{file_path}:{name}",
                                    "type": "exported_function",
                                    "name": name,
                                    "line": node.start_point[0] + 1
                                })
            
        # Imports
        elif node.type == "import_statement":
            source_node = node.child_by_field_name("source")
            target_module = ""
            if source_node:
                target_module = content[source_node.start_byte:source_node.end_byte].decode('utf8').strip("'\"")
            imports.append({
                "source": file_path,
                "target_module": target_module,
                "statement": content[node.start_byte:node.end_byte].decode('utf8'),
                "line": node.start_point[0] + 1
            })
            
        # Calls
        elif node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            if func_node:
                callee_name = content[func_node.start_byte:func_node.end_byte].decode('utf8')
                calls.append({
                    "caller_file": file_path,
                    "callee": callee_name,
                    "line": node.start_point[0] + 1
                })
                # Check Express routes: app.get, router.post, etc.
                if "." in callee_name and any(m in callee_name for m in [".get", ".post", ".put", ".delete", ".use"]):
                    entry_points.append({
                        "id": f"{file_path}:{callee_name}",
                        "reason": "express_route",
                        "line": node.start_point[0] + 1
                    })

    def analyze_repo(self, files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyzes ALL files in the repo. Two-pass design:
        - Pass 1: count_stats() on full content → accurate SLOC + function counts
        - Pass 2: tree-sitter AST on first 50KB → graph nodes/edges for topology
        """
        graph = {
            "files": [],
            "nodes": [],
            "imports": [],
            "calls": [],
            "entry_points": [],
            "action_findings": [],
            # Accurate aggregate stats — always computed from full file content
            "total_sloc": 0,
            "total_public_functions": 0,
            "total_lines": 0,
        }
        total_files = len(files)
        log_interval = max(1, total_files // 10)

        for i, f in enumerate(files, 1):
            path = f["path"]
            if i == 1 or i == total_files or i % log_interval == 0:
                logger.info(f"🗺️  [CARTOGRAPHER] Parsing AST: {i}/{total_files}...")
            content_str = f.get("content", "")
            content_bytes = content_str.encode('utf8')

            # Pass 1: full-content stats (never truncated)
            stats = self.count_stats(path, content_str)
            graph["total_sloc"] += stats["sloc"]
            graph["total_public_functions"] += stats["public_functions"]
            graph["total_lines"] += stats["total_lines"]

            # Pass 2: AST graph extraction (first 50KB)
            file_data = self.parse_file(path, content_bytes)
                
            graph["files"].append(path)
            graph["nodes"].extend(file_data.get("nodes", []))
            graph["imports"].extend(file_data.get("imports", []))
            graph["calls"].extend(file_data.get("calls", []))
            graph["entry_points"].extend(file_data.get("entry_points", []))

            # GC every 50 files to prevent memory build-up from tree-sitter C bindings
            if i % 50 == 0:
                gc.collect()

        graph["security_findings"] = self.security_scan(files)
        return graph

    def security_scan(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Regex-based security scan: hardcoded secrets, eval usage, XSS risks etc."""
        import re
        findings = []
        
        # Code-only extensions — don't scan docs/configs for secrets
        CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".rb", ".php", ".cs"}
        
        patterns = [
            ("TODO/FIXME", re.compile(r'\b(TODO|FIXME|HACK|XXX)\b', re.IGNORECASE), "info", "Technical debt can accumulate and cause maintenance issues over time.", "Track this debt in a ticketing system and assign it to a sprint."),
            ("eval() usage", re.compile(r'\beval\s*\('), "high", "Execution of arbitrary code can lead to critical remote code execution (RCE) vulnerabilities.", "Replace eval() with safer alternatives like ast.literal_eval() or specific parsers."),
            ("Hardcoded secret", re.compile(r'(?i)(password|secret|api_key|token|passwd)\s*=\s*["\'][^"\']{12,}["\']'), "critical", "Secrets in source code can be extracted by attackers.", "Move secrets to environment variables or a secure secret manager."),
            ("SQL injection risk", re.compile(r'execute\s*\(\s*f["\']|execute\s*\(\s*".*%s'), "high", "Dynamic SQL queries can be manipulated by user input.", "Use parameterized queries or an ORM."),
            ("Insecure hash", re.compile(r'\b(md5|sha1)\b', re.IGNORECASE), "medium", "Weak hashing algorithms are vulnerable to collision attacks.", "Upgrade to SHA-256 or bcrypt for passwords."),
            ("XSS Vulnerability", re.compile(r'(?i)innerHTML\s*=|dangerouslySetInnerHTML'), "high", "Unescaped HTML can allow attackers to inject malicious scripts.", "Use textContent or sanitize HTML input using DOMPurify."),
            ("Debug code", re.compile(r'\bpdb\.set_trace\(\)|debugger;'), "info", "Leftover debug code can halt production execution.", "Remove debug statements before committing."),
        ]
        # Cap to first 200 files to avoid O(files*lines*patterns) blowup
        for f in files[:200]:
            path = f["path"]
            content = f.get("content", "")
            if not content:
                continue
            # Skip non-code files (markdown, yaml, json, etc.) to reduce false positives
            ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
            if ext not in CODE_EXTS:
                continue
            for lines_idx, line in enumerate(content.splitlines(), 1):
                for label, pattern, severity, impact, remediation in patterns:
                    if pattern.search(line):
                        # Extra filter: skip obvious template/example values
                        if 'your_' in line.lower() or 'example' in line.lower() or 'placeholder' in line.lower():
                            continue
                        findings.append({
                            "file": path, "line": lines_idx,
                            "type": label, "severity": severity,
                            "snippet": line.strip()[:120],
                            "impact": impact,
                            "remediation": remediation
                        })
                        if len(findings) >= 500:
                            return findings
        return findings

    def pattern_scan(self, graph: Dict[str, Any], files: List[Dict[str, Any]]):
        """Detects architectural patterns and anti-patterns."""
        findings = []
        actions = []
        node_counts = Counter(n["id"].split(":")[0] for n in graph.get("nodes", []))
        god_objects = [f for f, c in node_counts.items() if c > 15]
        
        if god_objects:
            findings.append({"type": "God Object", "severity": "warning",
                "file": god_objects[0], "detail": f"Files with too many responsibilities (15+ functions/classes). Consider splitting into smaller modules."})
            actions.append({
                "title": "Split Large Files",
                "severity": "high",
                "description": f"{len(god_objects)} files have too many functions. Split by responsibility.",
                "action": "Group related functions and extract to separate modules",
                "impact": "Improves code navigation and testing",
                "target_file": god_objects[0]
            })

        # Highly coupled files
        imported_by = Counter()
        files_set = graph.get("files", [])[:100]
        for imp in graph.get("imports", [])[:2000]:
            tgt_mod = imp.get("target_module", "").replace(".", "/")
            for fpath in files_set:
                if tgt_mod and (fpath.endswith(tgt_mod + ".py") or fpath.endswith(tgt_mod + ".ts") or fpath.endswith(tgt_mod + ".tsx")):
                    imported_by[fpath] += 1
                    
        highly_coupled = [f for f, c in imported_by.items() if c > 5]
        if highly_coupled:
            findings.append({"type": "Highly Coupled", "severity": "warning",
                "file": highly_coupled[0], "detail": f"Files imported by 5+ other files. Consider if this is intentional."})
            actions.append({
                "title": "Reduce Coupling",
                "severity": "medium",
                "description": f"{len(highly_coupled)} files are imported by many others.",
                "action": "Review if these should be split or if importers should be consolidated",
                "impact": "Reduces blast radius of changes",
                "target_file": highly_coupled[0]
            })

        # Long files
        long_files = [f["path"] for f in files if (f.get("content") or "").count("\n") > 500]
        if long_files:
            findings.append({"type": "Long File", "severity": "warning",
                "file": long_files[0], "detail": f"Files over 500 lines are harder to maintain. Consider breaking into smaller modules."})

        if graph.get("security_findings"):
            crit_high = [s for s in graph.get("security_findings", []) if s["severity"] in ("critical", "high")]
            if crit_high:
                actions.append({
                    "title": "Fix Security Issues",
                    "severity": "critical",
                    "description": f"{len(crit_high)} high-severity security issues found.",
                    "action": "Address hardcoded secrets, injection risks immediately",
                    "impact": "Prevents potential security breaches",
                    "target_file": crit_high[0]["file"]
                })

        return findings, actions
