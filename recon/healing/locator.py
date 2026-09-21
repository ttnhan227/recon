from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".idea",
    ".vscode",
}

SUPPORTED_EXTENSIONS = {".py", ".ts", ".js", ".go", ".rs", ".java", ".kt", ".rb"}


@dataclass
class LocatedContext:
    file_path: Path
    relative_path: str
    line_number: int
    matched_pattern: str
    full_content: str
    snippet: str
    function_name: str | None = None


class CodeLocator:
    """Scans a local repository to locate the source file and handler for a given endpoint."""

    def __init__(self, repo_dir: Path | str = "."):
        self.repo_dir = Path(repo_dir).resolve()

    def locate_endpoint(self, method: str, endpoint_path: str) -> list[LocatedContext]:
        """Finds source code files that define or handle the given HTTP method and route."""
        if not self.repo_dir.exists() or not self.repo_dir.is_dir():
            return []

        results: list[LocatedContext] = []
        method_upper = method.upper()

        # Clean endpoint path segments: e.g. "/api/v1/auth/login" -> ["auth", "login"]
        clean_path = endpoint_path.strip().split("?")[0]
        # Remove parameter syntax like {id} or :id, numeric IDs, and UUIDs for flexible matching
        path_segments = []
        for seg in clean_path.strip("/").split("/"):
            if not seg:
                continue
            if seg.startswith("{") or seg.startswith(":"):
                continue
            if seg.isdigit() or re.match(r"^[0-9a-fA-F\-]{8,}$", seg):
                continue
            path_segments.append(seg)
        last_segment = path_segments[-1] if path_segments else ""

        # Candidates regex patterns
        patterns = []
        clean_rel = clean_path.lstrip("/")
        m_lower = re.escape(method_upper.lower())
        if clean_rel:
            esc_clean = re.escape(clean_rel)
            patterns.append(
                re.compile(
                    r"""(?:@\w+|\bapp|\brouter)\."""
                    + m_lower
                    + r"""\s*\(\s*["']/?(?:"""
                    + esc_clean
                    + r""")["']""",
                    re.IGNORECASE,
                )
            )
        if last_segment:
            esc_seg = re.escape(last_segment)
            pat_str = (
                r"""(?:@\w+|\bapp|\brouter)\."""
                + m_lower
                + r"""\s*\(\s*["']/?(?:[\w\-_/:{}]*/)?(?:"""
                + esc_seg
                + r""")(?:/\{[^}]+\}|/:\w+)?["']"""
            )
            patterns.append(re.compile(pat_str, re.IGNORECASE))
            patterns.append(
                re.compile(
                    r"""\."""
                    + m_lower
                    + r"""\s*\(\s*["']/?(?:[\w\-_/:{}]*/)?(?:"""
                    + esc_seg
                    + r""")["']""",
                    re.IGNORECASE,
                )
            )
            patterns.append(
                re.compile(r"""["']/(?:""" + esc_seg + r""")(?:/|\?|["'])""", re.IGNORECASE)
            )

        # Search repository files
        for root, dirs, files in os.walk(self.repo_dir):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for file in files:
                ext = Path(file).suffix.lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                full_path = Path(root) / file
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                # Search for match in content
                lines = content.splitlines()
                for line_idx, line in enumerate(lines):
                    for pat in patterns:
                        if pat.search(line):
                            start = max(0, line_idx - 10)
                            end = min(len(lines), line_idx + 40)
                            snippet = "\n".join(lines[start:end])

                            # Detect function name if python
                            func_name = None
                            for sub_line in lines[line_idx : min(len(lines), line_idx + 10)]:
                                fn_match = re.search(
                                    r"(?:async\s+)?def\s+([a-zA-Z0-9_]+)\s*\(", sub_line
                                )
                                if fn_match:
                                    func_name = fn_match.group(1)
                                    break

                            rel_path = str(full_path.relative_to(self.repo_dir))
                            results.append(
                                LocatedContext(
                                    file_path=full_path,
                                    relative_path=rel_path,
                                    line_number=line_idx + 1,
                                    matched_pattern=pat.pattern,
                                    full_content=content,
                                    snippet=snippet,
                                    function_name=func_name,
                                )
                            )
                            break  # Found match for this line

        # Sort results by relevance (controllers/routes/views prioritized)
        def score(ctx: LocatedContext) -> int:
            p = ctx.relative_path.lower()
            s = 0
            if "controller" in p or "route" in p or "api" in p or "view" in p:
                s += 10
            if any(seg.lower() in p for seg in path_segments):
                s += 5
            return s

        results.sort(key=score, reverse=True)
        return results
