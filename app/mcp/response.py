from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class MCPResponse:
    summary: str
    data: dict = field(default_factory=dict)
    error: dict | None = None

    def to_json(self) -> str:
        return json.dumps({"summary": self.summary, "data": self.data, "error": self.error})

    @staticmethod
    def err(message: str, code: str = "error") -> MCPResponse:
        return MCPResponse(
            summary=message,
            data={},
            error={"error": code, "detail": message},
        )
