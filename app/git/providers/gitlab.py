import json
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

from app.git.providers import GitProvider


class GitLabProvider(GitProvider):
    def __init__(self, token: str, base_url: str = "https://gitlab.com") -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")

    def get_push_url(self, remote_url: str, token: str) -> str:
        parsed = urlparse(remote_url)
        return f"https://oauth2:{token}@{parsed.netloc}{parsed.path}"

    def create_repo(self, org: str, repo_name: str) -> str:
        """Create a private GitLab project in namespace. Idempotent — returns URL if exists."""
        headers = {
            "PRIVATE-TOKEN": self._token,
            "Content-Type": "application/json",
        }

        namespace_id = self._get_namespace_id(org, headers)
        payload = json.dumps(
            {
                "name": repo_name,
                "path": repo_name,
                "namespace_id": namespace_id,
                "visibility": "private",
            }
        ).encode()

        req = urllib.request.Request(
            f"{self._base_url}/api/v4/projects",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                return data["http_url_to_repo"]
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                return self._get_existing_repo(org, repo_name, headers)
            raise

    def _get_namespace_id(self, org: str, headers: dict) -> int:
        req = urllib.request.Request(
            f"{self._base_url}/api/v4/namespaces/{org}",
            headers=headers,
            method="GET",
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return data["id"]

    def _get_existing_repo(self, org: str, repo_name: str, headers: dict) -> str:
        encoded = quote(f"{org}/{repo_name}", safe="")
        req = urllib.request.Request(
            f"{self._base_url}/api/v4/projects/{encoded}",
            headers=headers,
            method="GET",
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return data["http_url_to_repo"]
