import json
import urllib.error
import urllib.request
from urllib.parse import urlparse

from app.git.providers import GitProvider


class GitHubProvider(GitProvider):
    def __init__(self, token: str) -> None:
        self._token = token

    def get_push_url(self, remote_url: str, token: str) -> str:
        parsed = urlparse(remote_url)
        return f"https://{token}@{parsed.netloc}{parsed.path}"

    def create_repo(self, org: str, repo_name: str) -> str:
        """Create a private GitHub repo in org. Idempotent — returns URL if exists."""
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        }
        payload = json.dumps(
            {"name": repo_name, "private": True, "auto_init": False}
        ).encode()

        req = urllib.request.Request(
            f"https://api.github.com/orgs/{org}/repos",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                return data["clone_url"]
        except urllib.error.HTTPError as exc:
            if exc.code == 422:
                return self._get_existing_repo(org, repo_name, headers)
            raise

    def _get_existing_repo(self, org: str, repo_name: str, headers: dict) -> str:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{org}/{repo_name}",
            headers=headers,
            method="GET",
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return data["clone_url"]
