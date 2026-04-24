# API Contract: Clone URL Endpoint

## GET /api/v1/workspaces/{workspace_id}/clone-url

Returns the remote git clone URL and setup instructions for a workspace's Obsidian vault.

### Authentication
Bearer token required. Caller must be an authenticated member of the workspace (any role: reader, editor, admin) or a platform admin.

### Path Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | UUID | Workspace identifier |

### Success Response — 200 OK
```json
{
  "clone_url": "https://github.com/acme/wiki-engineering-team.git",
  "workspace_slug": "engineering-team",
  "last_push_at": "2026-04-24T14:32:00Z",
  "setup": {
    "clone_command": "git clone https://github.com/acme/wiki-engineering-team.git ~/wiki-engineering-team",
    "obsidian_note": "Open the cloned folder as an Obsidian vault. Install the 'Obsidian Git' community plugin and set auto-pull interval to 60 seconds for live updates.",
    "plugin_url": "https://github.com/denolehov/obsidian-git"
  }
}
```

### Error Responses
| Status | Condition |
|--------|-----------|
| 401 | Missing or invalid bearer token |
| 403 | Authenticated but not a member of this workspace |
| 404 | Workspace does not exist |
| 409 | Workspace exists but remote sync is not configured (`git_remote_url` is null) |

### 409 Response Body
```json
{
  "detail": "Remote sync is not configured for this workspace. Contact your administrator to enable git remote push."
}
```

### Notes
- The `clone_url` is the public HTTPS URL without embedded credentials. Users clone with their own git credentials or using a read-only token provided separately by the admin.
- `last_push_at` is null if the workspace has never been pushed to remote.
- This endpoint does NOT expose the provider token — it only returns the clone URL.
