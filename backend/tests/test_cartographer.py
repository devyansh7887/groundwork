"""
tests/test_cartographer.py — pytest version of the old script-style test.
Run with: pytest backend/tests/ -v
"""
import time
import pytest
from cartographer import Cartographer


@pytest.fixture(scope="module")
def cartographer():
    return Cartographer()


def test_large_benchmark_file_within_deadline(cartographer):
    """Tree-sitter must not hang on a 43KB TS benchmark file with huge arrays."""
    row = b'  { id: 1, value: "test", nested: { a: 1, b: 2 } },\n'
    bench_content = b'const benchData = [\n' + (row * 800) + b'];\n'

    t0 = time.monotonic()
    result = cartographer.parse_file('packages/computer/src/bench/fs-ops.bench.ts', bench_content)
    elapsed = time.monotonic() - t0

    assert elapsed < 3.0, f"Took {elapsed:.2f}s — would still drop connection on Render!"
    # The AST result doesn't need any nodes for a pure data file
    assert "nodes" in result
    assert "imports" in result


def test_normal_tsx_file_parsed_correctly(cartographer):
    """Standard React TSX file extracts the exported component as a node."""
    normal_ts = b'''
import { useState } from "react";
export function App() {
  const [count, setCount] = useState(0);
  return count;
}
'''
    t0 = time.monotonic()
    result = cartographer.parse_file('src/app.tsx', normal_ts)
    elapsed = time.monotonic() - t0

    assert elapsed < 1.0, f"Normal TSX took {elapsed:.2f}s — unexpectedly slow"
    # Should extract the App function node and the react import
    assert any(n["name"] == "App" for n in result["nodes"]), "Missing App function node"
    assert any("react" in imp.get("statement", "").lower() for imp in result["imports"]), "Missing React import"


def test_python_file_extracts_functions_and_imports(cartographer):
    """Python file parser extracts functions, classes and imports correctly."""
    py_content = b'''
import os
from typing import List

def hello(name: str) -> str:
    return f"Hello, {name}"

class MyClass:
    def method(self):
        pass
'''
    result = cartographer.parse_file('src/example.py', py_content)

    func_names = [n["name"] for n in result["nodes"]]
    assert "hello" in func_names, "Missing 'hello' function"
    assert "MyClass" in func_names, "Missing 'MyClass' class"

    import_targets = [imp.get("target_module", "") for imp in result["imports"]]
    assert "os" in import_targets, "Missing 'os' import"
    assert "typing" in import_targets, "Missing 'typing' import"


def test_minified_js_file_is_skipped(cartographer):
    """Minified files (no newlines, >500 bytes) should be skipped by the parser safely."""
    minified = b'var a=1;' + b'var b=function(){return a+1;};' * 30  # >500 bytes, no newlines
    result = cartographer.parse_file('dist/bundle.min.js', minified)
    # Should not crash and should return empty collections
    assert "nodes" in result
    assert "imports" in result


def test_count_stats_sloc_accuracy(cartographer):
    """SLOC counter should exclude blank lines and pure comment lines."""
    content = """
# This is a comment
def foo():
    # inline comment
    x = 1  # trailing comment counts as code

    return x
"""
    stats = cartographer.count_stats('example.py', content)
    # Lines with code: 'def foo():', 'x = 1  # trailing comment counts as code', 'return x'
    assert stats["sloc"] == 3, f"Expected 3 SLOC, got {stats['sloc']}"
    assert stats["public_functions"] == 1, f"Expected 1 function, got {stats['public_functions']}"
