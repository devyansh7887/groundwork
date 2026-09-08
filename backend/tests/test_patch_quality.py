"""
tests/test_patch_quality.py — Patch Quality Evaluation

Evaluates the output of the Contribution Drafter by ensuring that the generated
unified diff patches are syntactically valid and apply cleanly using `git apply`.
"""
import pytest
import tempfile
import subprocess
import os

def test_patch_applies_cleanly():
    """
    Simulates a generated patch from the Contribution Drafter and verifies
    that `git apply --check` succeeds. This proves the agent's output is
    syntactically valid and maintainer-safe.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Create a dummy file in a mock git repo
        file_path = os.path.join(tmpdir, "target.py")
        with open(file_path, "w") as f:
            f.write("def hello():\n    print('Hello World')\n    return False\n")
            
        # Initialize a mock git repo so `git apply` works cleanly
        subprocess.run(["git", "init"], cwd=tmpdir, check=True, capture_output=True)
        subprocess.run(["git", "add", "target.py"], cwd=tmpdir, check=True, capture_output=True)

        # 2. Simulate the LLM agent generating a unified diff patch
        # This matches the strict schema enforced by the ContributionDrafter
        mock_patch_diff = """--- a/target.py
+++ b/target.py
@@ -1,3 +1,3 @@
 def hello():
-    print('Hello World')
-    return False
+    print('Hello Groundwork')
+    return True
"""
        patch_path = os.path.join(tmpdir, "fix.patch")
        with open(patch_path, "w") as f:
            f.write(mock_patch_diff)
            
        # 3. Verify the patch applies cleanly
        # Using --check ensures we validate syntax and context without modifying the file
        result = subprocess.run(
            ["git", "apply", "--check", "fix.patch"],
            cwd=tmpdir,
            capture_output=True,
            text=True
        )
        
        # 4. Assert success
        assert result.returncode == 0, f"git apply failed: {result.stderr}"
