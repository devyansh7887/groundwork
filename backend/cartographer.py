import os
import json
import logging
import gc
import logging
from typing import Dict, Any, List
from tree_sitter import Language, Parser
import tree_sitter_python
import tree_sitter_javascript

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load tree-sitter languages
PY_LANGUAGE = Language(tree_sitter_python.language())
JS_LANGUAGE = Language(tree_sitter_javascript.language())

class Cartographer:
    def __init__(self):
        self.parsers = {
            "Python": Parser(PY_LANGUAGE),
            "JavaScript": Parser(JS_LANGUAGE),
            "TypeScript": Parser(JS_LANGUAGE)
        }

    def determine_language(self, file_path: str) -> str:
        if file_path.endswith(".py"):
            return "Python"
        elif file_path.endswith((".ts", ".tsx")):
            return "TypeScript"
        elif file_path.endswith((".js", ".jsx", ".mjs", ".cjs")):
            return "JavaScript"
        return "Unknown"

    def parse_file(self, file_path: str, content: bytes) -> Dict[str, Any]:
        """Parses a file and extracts graph nodes and edges."""
        lang = self.determine_language(file_path)
        parser = self.parsers.get(lang)
        
        nodes = []
        imports = []
        calls = []
        entry_points = []
        
        # Prevent C-level segfaults on heavily minified files with extremely long lines
        try:
            text = content.decode('utf8', errors='ignore')
            if any(len(line) > 2000 for line in text.splitlines()):
                logger.warning(f"Skipping AST parse for {file_path} due to extremely long lines (minified)")
                parser = None
        except Exception:
            pass
            
        if parser:
            try:
                tree = parser.parse(content)
                def traverse(node):
                    if lang == "Python":
                        self._extract_python_features(node, file_path, content, nodes, imports, calls, entry_points)
                    else:
                        self._extract_js_features(node, file_path, content, nodes, imports, calls, entry_points)
                        
                    for child in node.children:
                        traverse(child)
                        
                traverse(tree.root_node)
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
            # Fallback if parsing failed
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
        # Functions and Classes
        if node.type in ["function_declaration", "class_declaration", "arrow_function", "method_definition"]:
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
        """Analyzes a list of files (dict containing 'path' and 'content')."""
        graph = {
            "files": [],
            "nodes": [],
            "imports": [],
            "calls": [],
            "entry_points": [],
            "action_findings": []
        }
        total_files = len(files)
        for i, f in enumerate(files, 1):
            path = f["path"]
            content = f["content"].encode('utf8')
            file_data = self.parse_file(path, content)
            
            if i % max(1, total_files // 10) == 0 or i == total_files:
                logger.info(f"🗺️  [CARTOGRAPHER] Parsing AST: {i}/{total_files}...")
                
            # Force garbage collection to prevent tree-sitter AST memory leaks
            gc.collect()
            
            graph["files"].append(path)
            graph["nodes"].extend(file_data.get("nodes", []))
            graph["imports"].extend(file_data.get("imports", []))
            graph["calls"].extend(file_data.get("calls", []))
            graph["entry_points"].extend(file_data.get("entry_points", []))

        graph["security_findings"] = self.security_scan(files)
        patterns, actions = self.pattern_scan(graph, files)
        graph["pattern_findings"] = patterns
        graph["action_findings"] = actions
        return graph

    def security_scan(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Regex-based security scan: TODO/FIXME, hardcoded secrets, eval usage."""
        import re
        findings = []
        patterns = [
            ("TODO/FIXME", re.compile(r'\b(TODO|FIXME|HACK|XXX)\b', re.IGNORECASE), "info", "Technical debt can accumulate and cause maintenance issues over time.", "Track this debt in a ticketing system and assign it to a sprint."),
            ("eval() usage", re.compile(r'\beval\s*\('), "high", "Execution of arbitrary code can lead to critical remote code execution (RCE) vulnerabilities.", "Replace eval() with safer alternatives like ast.literal_eval() or specific parsers."),
            ("Hardcoded secret", re.compile(r'(?i)(password|secret|api_key|token|passwd)\s*=\s*["\'][^"\']{4,}["\']'), "critical", "Secrets in source code can be extracted by attackers and used to access sensitive systems.", "Move secrets to environment variables or a secure secret manager (e.g., AWS Secrets Manager, HashiCorp Vault)."),
            ("SQL injection risk", re.compile(r'execute\s*\(\s*f["\']|execute\s*\(\s*".*%s'), "high", "Dynamic SQL queries can be manipulated by user input, leading to unauthorized data access or deletion.", "Use parameterized queries or an ORM that automatically escapes input parameters."),
            ("Insecure hash", re.compile(r'\b(md5|sha1)\b', re.IGNORECASE), "medium", "Weak hashing algorithms are vulnerable to collision attacks and can be cracked quickly.", "Upgrade to a strong hashing algorithm like SHA-256 or bcrypt for passwords."),
            ("XSS Vulnerability", re.compile(r'(?i)innerHTML\s*=|dangerouslySetInnerHTML'), "high", "Unescaped HTML can allow attackers to inject malicious scripts into the browsers of other users.", "Use textContent or safely sanitize HTML input using libraries like DOMPurify."),
            ("Debug code", re.compile(r'\bpdb\.set_trace\(\)|debugger;'), "info", "Leftover debug code can halt production execution or expose internal state.", "Remove debug statements before committing or use a configurable logging framework."),
            ("Debug Statements", re.compile(r'\b(console\.log|print)\s*\('), "low", "Excessive logging can clutter production logs and potentially leak sensitive information.", "Replace with structured logging at appropriate log levels (DEBUG, INFO, ERROR)."),
        ]
        for f in files:
            path = f["path"]
            content = f.get("content", "")
            if not content:
                continue
            for lines_idx, line in enumerate(content.splitlines(), 1):
                for label, pattern, severity, impact, remediation in patterns:
                    if pattern.search(line):
                        findings.append({
                            "file": path, "line": lines_idx,
                            "type": label, "severity": severity,
                            "snippet": line.strip()[:120],
                            "impact": impact,
                            "remediation": remediation
                        })
        return findings

    def pattern_scan(self, graph: Dict[str, Any], files: List[Dict[str, Any]]):
        """Detects architectural patterns and anti-patterns, returns (patterns, actions)."""
        findings = []
        actions = []
        from collections import Counter
            # 1. High Complexity Files (God Object)
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

        # 2. Highly Coupled (Imported by > 5 other files)
        imported_by = Counter()
        for imp in graph.get("imports", []):
            tgt_mod = imp.get("target_module", "").replace(".", "/")
            for fpath in graph.get("files", []):
                if tgt_mod and fpath.endswith(tgt_mod + ".py") or fpath.endswith(tgt_mod + ".ts") or fpath.endswith(tgt_mod + ".tsx"):
                    imported_by[fpath] += 1
                    
        highly_coupled = [f for f, c in imported_by.items() if c > 5]
        if highly_coupled:
            findings.append({"type": "Highly Coupled", "severity": "warning",
                "file": highly_coupled[0], "detail": f"Files that import 5+ other files. Consider if this is intentional."})
            actions.append({
                "title": "Reduce Coupling",
                "severity": "medium",
                "description": f"{len(highly_coupled)} files are imported by many others. Consider if this is intentional.",
                "action": "Review if these should be split or if importers should be consolidated",
                "impact": "Reduces blast radius of changes",
                "target_file": highly_coupled[0]
            })

        # 3. Large Files / Long Files: > 500 lines
        long_files = [f["path"] for f in files if (f.get("content") or "").count("\n") > 500]
        if long_files:
            findings.append({"type": "Long File", "severity": "warning",
                "file": long_files[0], "detail": f"Files over 500 lines are harder to maintain. Consider breaking into smaller modules."})

        # 4. Action for Security if any security findings exist
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
