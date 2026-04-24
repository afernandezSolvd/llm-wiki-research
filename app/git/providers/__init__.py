from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings


class GitProvider(ABC):
    @abstractmethod
    def create_repo(self, org: str, repo_name: str) -> str:
        """Create a remote repo and return its clone URL. Idempotent."""
        ...

    @abstractmethod
    def get_push_url(self, remote_url: str, token: str) -> str:
        """Return authenticated push URL for the given remote URL."""
        ...


def get_provider(settings: "Settings") -> GitProvider:
    from app.git.providers.github import GitHubProvider
    from app.git.providers.gitlab import GitLabProvider

    if settings.wiki_git_provider == "gitlab":
        return GitLabProvider(
            token=settings.wiki_git_provider_token,
            base_url=settings.wiki_git_base_url or "https://gitlab.com",
        )
    return GitHubProvider(token=settings.wiki_git_provider_token)
