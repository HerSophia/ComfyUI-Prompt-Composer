"""Identity 解析。

把一个 Identity 展开成一组固定 TagEntry，供 Pipeline 在采样前注入。

要点：
    1. identity_tags 作为角色tag，source=identity，在冲突解析里保持高优先级。
       与用户手填的固定词（source=fixed）区分开：角色特征可被禁用词清除，
       用户手填的固定词被禁用时保留。
    2. locked_features 合并到主 identity_tag的 features 上。
       这样它作为固定项参与约束流程时优先级最高，随机项与之冲突会被移除。
    3. default_tags 按分类展开为固定 tag。
    4. default_clothing 作为固定 clothing tag。
    5. tag 若在 TagStore 里存在，用库里的数据；不存在则新建。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .models import Identity, LogEntry, TagEntry
from .tag_store import TagStore


# 固定项的优先级，保证在冲突中优先保留。
FIXED_PRIORITY = 100


class IdentityResolver:
    """把 Identity 展开为固定 TagEntry 列表。"""

    def __init__(self, store: TagStore) -> None:
        self.store = store

    def resolve(
        self, identity: Identity, include_default_clothing: bool = True
    ) -> Tuple[List[TagEntry], List[LogEntry]]:
        result: List[TagEntry] = []
        logs: List[LogEntry] = []
        order = 0
        seen = set()

        def make_entry(name: str, category_hint: str) -> Optional[TagEntry]:
            nonlocal order
            key = name.strip().lower()
            if not key or key in seen:
                return None
            existing = self.store.find(name)
            if existing is not None:
                entry = existing.clone(source="identity", order=order)
            else:
                entry = TagEntry(
                    tag=name.strip(),
                    category=category_hint,
                    source="identity",
                        order=order,
                )
            entry.priority = max(entry.priority, FIXED_PRIORITY)
            order += 1
            seen.add(key)
            return entry

        # 1. identity_tags，主 tag 承载 locked_features。
        for index, name in enumerate(identity.identity_tags):
            entry = make_entry(name, "character")
            if entry is None:
                continue
            if index == 0 and identity.locked_features:
                merged = dict(entry.features)
                merged.update(identity.locked_features)
                entry.features = merged
            result.append(entry)

        # 若没有 identity_tags 但有 locked_features，用一个载体 tag 承载。
        if not identity.identity_tags and identity.locked_features:
            carrier = TagEntry(
                tag=identity.id,
                category="character",
                source="identity",
                order=order,
                priority=FIXED_PRIORITY,
                features=dict(identity.locked_features),
            )
            order += 1
            result.append(carrier)

        # 2. default_tags，按分类展开。
        for category, names in identity.default_tags.items():
            for name in names:
                entry = make_entry(name, category)
                if entry is not None:
                    result.append(entry)

        # 3. default_clothing。
        if include_default_clothing:
            for name in identity.default_clothing:
                entry = make_entry(name, "clothing")
                if entry is not None:
                    result.append(entry)

        logs.append(
            LogEntry(
                level="info",
                code="IDENTITY_RESOLVED",
                message=f"Identity '{identity.id}' expanded into {len(result)} fixed tags.",
                details={"identity": identity.id, "tags": [e.tag for e in result]},
            )
        )
        return result, logs
