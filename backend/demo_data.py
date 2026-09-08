"""
Mock payloads for the Interview Demo Mode.
These allow the application to bypass LLM and GitHub API rate limits.
"""

DEMO_ANALYSIS = {
    "diagram": '''graph TD
    classDef domain fill:#1f2937,stroke:#3b82f6,stroke-width:2px;
    classDef entry fill:#065f46,stroke:#10b981,stroke-width:2px;
    classDef core fill:#4c1d95,stroke:#8b5cf6,stroke-width:2px;
    classDef util fill:#374151,stroke:#6b7280,stroke-width:1px;

    subgraph "Filesystem Subsystem"
        fs["docs/04_filesystem_interface.md"]:::core
        workspace["src/fs/WorkspaceFilesystem.ts"]:::entry
        symlink["src/fs/symlink.ts"]:::core
    end

    workspace --> fs
    workspace --> symlink
    ''',
    "readme": "WorkspaceFilesystem implements public symlink primitives, but the documentation currently incorrectly labels symlinks as internal primitives.",
    "claims": [
        {
            "claim": "WorkspaceFilesystem implements public symlink primitives.",
            "status": "Verified",
            "cited_file": "src/fs/WorkspaceFilesystem.ts"
        },
        {
            "claim": "Documentation currently incorrectly labels symlinks as internal primitives.",
            "status": "Verified",
            "cited_file": "docs/04_filesystem_interface.md"
        }
    ],
    "patterns": [
        {"pattern": "Uses class-based abstraction for filesystem operations.", "description": "Uses class-based abstraction for filesystem operations."},
        {"pattern": "Documentation and source code drift on public API surface.", "description": "Documentation and source code drift on public API surface."}
    ],
    "security": [],
    "actions": [
        "Update documentation to correctly reflect public API surface."
    ],
    "graph": {
        "nodes": 3,
        "edges": 2,
        "most_central_files": ["src/fs/WorkspaceFilesystem.ts", "docs/04_filesystem_interface.md"]
    }
}

DEMO_ISSUES = [
    {
        "number": 106,
        "title": "worker-shell: sqlite3 is unusable in the published package",
        "state": "open",
        "html_url": "https://github.com/demo/groundwork-demo/issues/106",
        "created_at": "2026-08-15T12:00:00Z",
        "comments": 2,
        "labels": [],
        "_difficulty": "medium"
    },
    {
        "number": 68,
        "title": "Make gc() reachable so orphaned blobs and manifests are actually cleaned up",
        "state": "open",
        "html_url": "https://github.com/demo/groundwork-demo/issues/68",
        "created_at": "2026-08-01T12:00:00Z",
        "comments": 1,
        "labels": [],
        "_difficulty": "medium"
    },
    {
        "number": 118,
        "title": "Document the public symlink filesystem surface",
        "state": "open",
        "html_url": "https://github.com/demo/groundwork-demo/issues/118",
        "created_at": "2026-08-25T12:00:00Z",
        "comments": 0,
        "labels": [],
        "_difficulty": "medium"
    },
    {
        "number": 121,
        "title": "Add exclude glob patterns and subtree pruning to 'find'",
        "state": "open",
        "html_url": "https://github.com/demo/groundwork-demo/issues/121",
        "created_at": "2026-08-25T14:00:00Z",
        "comments": 1,
        "labels": [],
        "_difficulty": "medium"
    }
]

DEMO_DRAFT = {
    "issue_title": "Document the public symlink filesystem surface",
    "issue_url": "https://github.com/demo/groundwork-demo/issues/118",
    "difficulty": "medium",
    "difficulty_reason": "Moderate complexity — requires understanding the codebase but changes are contained.",
    "target_files": [
        {
            "path": "docs/04_filesystem_interface.md",
            "reason": "This is the primary documentation file describing the filesystem interface that needs to be updated."
        }
    ],
    "understanding": "The documentation in `docs/04_filesystem_interface.md` claims that symbolic links are an internal implementation detail and that methods like `symlink`, `readlink`, `lstat`, and `chmod` are not publicly available on `Workspace.fs`. However, these methods are already implemented and shipped as part of the public `WorkspaceFilesystem` API. We need to update the documentation so that it accurately describes these four methods, explains their return values and error conditions, updates the error table, and corrects the Node.js comparison table and symlinks note in the appendix.",
    "modifications": [
        {
            "file": "docs/04_filesystem_interface.md",
            "instruction": "Under the 'stat' subsection in the 'API' section, update the description and add the new 'lstat', 'chmod', 'symlink', and 'readlink' subsections right after 'stat'."
        },
        {
            "file": "docs/04_filesystem_interface.md",
            "instruction": "In the Appendix table and Note: symlinks section at the bottom of the document."
        }
    ],
    "diff": """--- a/docs/04_filesystem_interface.md
+++ b/docs/04_filesystem_interface.md
@@ -100,5 +100,16 @@
-`stat` follows symlinks transparently; there is no `lstat`. See the
-note on internal symlink support in the appendix.
+`stat` follows trailing symbolic links transparently. To inspect a
+symbolic link itself without following it, use `lstat`.
+
+```ts
+const s = await fs.stat("/workspace/build/out.wasm");
+console.log(`${s.size} bytes, modified ${new Date(s.mtime).toISOString()}`);
+```
+
+### `lstat`
+
+```ts
+lstat(path: string): Promise<WorkspaceStatResult>
+```
@@ -500,8 +500,0 @@
-| `stat` / `lstat` | `stat` | No `lstat`; `stat` follows symlinks. See note below. |
-...
-| `chmod` | - | Pass `mode` to `writeFile` / `mkdir` at create time. There is no way to chmod an existing file without recreating it. |
-...
-| `symlink` / `readlink` | - | Not on the public surface; see note below. |
-...
-### Note: symlinks
-
-Symlinks exist as an **internal primitive** used by the `node:vfs`...
-visible paths as if they pointed straight at real files.
""",
    "test_code": "No tests required for documentation updates. Run `npm run docs:build` to verify formatting.",
    "pr_title": "docs: document the public symlink filesystem surface",
    "pr_description": "Fixes #118. Updates `04_filesystem_interface.md` to reflect that `symlink`, `readlink`, `lstat`, and `chmod` are now exposed on the public `WorkspaceFilesystem` API.",
    "confidence": "high",
    "confidence_reason": "Changes are strictly confined to markdown documentation and map exactly to the issue request."
}
