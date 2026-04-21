import difflib
import os
import uuid
from pathlib import Path

import git

from app.config import get_settings
from app.core.exceptions import GitError
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

DEFAULT_SCHEMA = """\
# Wiki Schema

## Page Types
- **entity**: Named real-world entities (people, orgs, technologies, places)
- **concept**: Abstract ideas, methodologies, frameworks
- **summary**: Summaries of source documents
- **exploration**: Q&A sessions and synthesized research
- **index**: Navigational index pages
- **log**: Append-only change log

## Naming Conventions
- Entity pages: `pages/entities/{slug}.md`
- Concept pages: `pages/concepts/{slug}.md`
- Summaries: `pages/summaries/{slug}.md`
- Explorations: `pages/explorations/{slug}.md`

## Cross-Reference Format
Link to other pages using: `[[page_path]]` or `[Title](page_path)`

## Quality Standards
- Every entity page must have: description, key facts, related entities
- Summaries must include: source title, key points, entities mentioned
- All claims should reference source documents where possible
"""

DEFAULT_INDEX = """\
# Wiki Index

## Entities
_No entities yet._

## Concepts
_No concepts yet._

## Summaries
_No summaries yet._
"""

DEFAULT_LOG = """\
# Change Log

_Wiki initialized._
"""


class RepoManager:
    def __init__(self, workspace_id: uuid.UUID):
        self.workspace_id = workspace_id
        self.repo_path = Path(settings.wiki_repos_root) / str(workspace_id)

    def _repo(self) -> git.Repo:
        if not (self.repo_path / ".git").exists():
            raise GitError(f"Repo not initialized for workspace {self.workspace_id}")
        return git.Repo(self.repo_path)

    def init(self) -> None:
        """Initialize a new wiki git repo with default structure."""
        if (self.repo_path / ".git").exists():
            return  # Already initialized

        self.repo_path.mkdir(parents=True, exist_ok=True)
        repo = git.Repo.init(self.repo_path)

        # Configure git user for commits
        repo.config_writer().set_value("user", "name", "LLM Wiki System").release()
        repo.config_writer().set_value("user", "email", "wiki@system.local").release()

        # Create directory structure
        for d in ["pages/entities", "pages/concepts", "pages/summaries", "pages/explorations"]:
            (self.repo_path / d).mkdir(parents=True, exist_ok=True)
            (self.repo_path / d / ".gitkeep").touch()

        # Write default files
        (self.repo_path / "schema.md").write_text(DEFAULT_SCHEMA)
        (self.repo_path / "index.md").write_text(DEFAULT_INDEX)
        (self.repo_path / "log.md").write_text(DEFAULT_LOG)

        repo.git.add("--all")
        repo.index.commit("Initial wiki structure")
        logger.info("wiki_repo_initialized", workspace_id=str(self.workspace_id))

    def read_file(self, page_path: str) -> str | None:
        """Read current content of a wiki page. Returns None if not found."""
        full_path = self.repo_path / page_path
        if not full_path.exists():
            return None
        return full_path.read_text(encoding="utf-8")

    def write_file(
        self,
        page_path: str,
        content: str,
        commit_message: str,
        author_name: str = "LLM Wiki",
        author_email: str = "wiki@system.local",
    ) -> str:
        """Write content to a wiki page and commit. Returns commit SHA."""
        repo = self._repo()
        full_path = self.repo_path / page_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

        repo.git.add(page_path)

        if not repo.index.diff("HEAD") and not repo.untracked_files:
            # Nothing actually changed
            return repo.head.commit.hexsha

        author = git.Actor(author_name, author_email)
        commit = repo.index.commit(commit_message, author=author, committer=author)
        logger.info("wiki_page_committed", page_path=page_path, sha=commit.hexsha[:8])
        return commit.hexsha

    def delete_file(self, page_path: str, commit_message: str) -> str:
        """Delete a wiki page and commit."""
        repo = self._repo()
        full_path = self.repo_path / page_path
        if full_path.exists():
            repo.index.remove([page_path], working_tree=True)
            commit = repo.index.commit(commit_message)
            return commit.hexsha
        return repo.head.commit.hexsha

    def rollback_file(self, page_path: str, commit_sha: str, rollback_message: str) -> str:
        """Restore a file to its state at commit_sha and commit the revert."""
        repo = self._repo()
        target_commit = repo.commit(commit_sha)

        try:
            blob = target_commit.tree[page_path]
            content = blob.data_stream.read().decode("utf-8")
        except KeyError as e:
            raise GitError(f"File {page_path} not found at commit {commit_sha}") from e

        return self.write_file(page_path, content, rollback_message)

    def get_file_history(self, page_path: str, max_count: int = 50) -> list[dict]:
        """Return git log for a specific file."""
        repo = self._repo()
        commits = list(repo.iter_commits(paths=page_path, max_count=max_count))
        return [
            {
                "sha": c.hexsha,
                "message": c.message.strip(),
                "author": c.author.name,
                "timestamp": c.committed_datetime.isoformat(),
            }
            for c in commits
        ]

    def compute_diff(self, old_content: str, new_content: str, page_path: str) -> str:
        """Compute a unified diff between two content strings."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines, new_lines, fromfile=f"a/{page_path}", tofile=f"b/{page_path}"
        )
        return "".join(diff)

    def list_pages(self) -> list[str]:
        """List all markdown files relative to repo root."""
        result = []
        for root, _, files in os.walk(self.repo_path):
            for f in files:
                if f.endswith(".md"):
                    rel = os.path.relpath(os.path.join(root, f), self.repo_path)
                    result.append(rel)
        return sorted(result)
