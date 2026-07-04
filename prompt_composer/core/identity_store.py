"""Identity 加载。

从 data/semantic/identities/ 加载角色 Identity。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .models import Identity


class IdentityStore:
    """In-memory index for identities."""

    def __init__(self, identities: List[Identity]) -> None:
        self._by_id: Dict[str, Identity] = {}
        for identity in identities:
            self._by_id[identity.id.strip().lower()] = identity

    @classmethod
    def from_directory(cls, data_dir: str | Path) -> "IdentityStore":
        path = Path(data_dir)
        identities: List[Identity] = []
        if path.exists():
            for file_path in sorted(path.glob("*.json")):
                with file_path.open("r", encoding="utf-8") as file:
                    raw = json.load(file)
                # 一个文件可以是单个 Identity，也可以是 Identity 列表。
                items = raw if isinstance(raw, list) else [raw]
                for item in items:
                    try:
                        identities.append(Identity.from_dict(item))
                    except ValueError as exc:
                        raise ValueError(f"Invalid identity in {file_path}: {exc}") from exc
        return cls(identities)

    def get(self, identity_id: str) -> Optional[Identity]:
        if not identity_id:
            return None
        return self._by_id.get(identity_id.strip().lower())

    def all(self) -> List[Identity]:
        return list(self._by_id.values())

    def ids(self) -> List[str]:
        return sorted(self._by_id.keys())
