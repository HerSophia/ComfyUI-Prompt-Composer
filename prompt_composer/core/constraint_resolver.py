"""Constraint resolver: requires completion, conflict removal, feature conflicts."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

from .feature_inference import FeatureInference
from .models import JsonDict, LogEntry, ResolverConfig, TagEntry
from .tag_store import TagStore


class ConstraintResolver:
    """Rule based resolver. This is not a general purpose solver."""

    def __init__(self, store: TagStore, config: ResolverConfig | None = None) -> None:
        self.store = store
        self.config = config or ResolverConfig()
        self.inference = FeatureInference()

    def resolve(
        self, tags: Sequence[TagEntry], fixed_tags: Sequence[str]
    ) -> Tuple[List[TagEntry], JsonDict, List[LogEntry], List[str]]:
        fixed = {tag.strip().lower() for tag in fixed_tags}
        current = list(tags)
        logs: List[LogEntry] = []
        # 因互斥而被淘汰的标签原文记录。只记因冲突淘汰的，
        # 不记因采样未中而未出现的。默认仅作数据产出，不改变取舍与日志。
        discarded: List[str] = []

        for _round in range(self.config.max_rounds):
            changed = False

            current, requires_logs, requires_changed = self._complete_requires(current)
            logs.extend(requires_logs)
            changed = changed or requires_changed

            current,conflict_logs, conflict_changed, conflict_dropped = self._remove_conflicts(
                current, fixed
            )
            logs.extend(conflict_logs)
            discarded.extend(conflict_dropped)
            changed = changed or conflict_changed

            current, feature_logs, feature_changed, feature_dropped = self._resolve_feature_conflicts(
                current, fixed
            )
            logs.extend(feature_logs)
            discarded.extend(feature_dropped)
            changed = changed or feature_changed

            if not changed:
                break
        else:
            logs.append(
                LogEntry(
                    level="warning",
                    code="MAX_ROUNDS_REACHED",
                    message="Constraint resolver reached the maximum number of rounds.",
                    details={"max_rounds": self.config.max_rounds},
                )
            )

        features, conflicts = self.inference.infer(current)
        for conflict in conflicts:
            logs.append(
                LogEntry(
                    level="warning",
                    code="FEATURE_CONFLICT_LEFT",
                    message=f"Feature conflict remains on '{conflict.feature}'.",
                    details=conflict.to_dict(),
                )
            )
        # 对被淘汰标签去重，保留首次出现的原文。
        deduped: List[str] = []
        seen_discarded = set()
        for name in discarded:
            key = name.strip().lower()
            if not key or key in seen_discarded:
                continue
            seen_discarded.add(key)
            deduped.append(name)
        return current, features, logs, deduped

    def _complete_requires(
        self, tags: List[TagEntry]
    ) -> Tuple[List[TagEntry], List[LogEntry], bool]:
        logs: List[LogEntry] = []
        present = {tag.tag.strip().lower() for tag in tags}
        result = list(tags)
        changed = False

        for tag in tags:
            for required in tag.requires:
                key = required.strip().lower()
                if key in present:
                    continue
                entry = self.store.find(required)
                if entry is None:
                    logs.append(
                        LogEntry(
                            level="warning",
                            code="REQUIRES_NOT_FOUND",
                            message=f"Required tag '{required}' for '{tag.tag}' was not found.",
                            details={"tag": tag.tag, "requires": required},
                        )
                    )
                    continue
                added = entry.clone(source="required", order=len(result))
                result.append(added)
                present.add(key)
                changed = True
                logs.append(
                    LogEntry(
                        level="info",
                        code="REQUIRES_ADDED",
                        message=f"Added '{added.tag}' because '{tag.tag}' requires it.",
                        details={"tag": tag.tag, "added": added.tag},
                    )
                )

        return result, logs, changed

    def _remove_conflicts(
        self, tags: List[TagEntry], fixed: Set[str]
    ) -> Tuple[List[TagEntry], List[LogEntry], bool, List[str]]:
        logs: List[LogEntry] = []
        result = list(tags)
        changed = False
        dropped: List[str] = []

        while True:
            pair = self._find_conflict_pair(result)
            if pair is None:
                break
            a, b = pair
            keep, drop = self._choose_keep(a, b, fixed)
            result.remove(drop)
            changed = True
            dropped.append(drop.tag)
            logs.append(
                LogEntry(
                    level="warning",
                    code="CONFLICT_REMOVED",
                    message=f"Removed '{drop.tag}' because it conflicts with '{keep.tag}'.",
                    details={"kept": keep.tag, "removed": drop.tag},
                )
            )

        return result, logs, changed, dropped

    def _find_conflict_pair(self, tags: List[TagEntry]) -> Optional[Tuple[TagEntry, TagEntry]]:
        for tag in tags:
            conflict_keys = {conflict.strip().lower() for conflict in tag.conflicts}
            if not conflict_keys:
                continue
            for other in tags:
                if other is tag:
                    continue
                if other.tag.strip().lower() in conflict_keys:
                    return tag, other
        return None

    def _resolve_feature_conflicts(
        self, tags: List[TagEntry], fixed: Set[str]
    ) -> Tuple[List[TagEntry], List[LogEntry], bool, List[str]]:
        logs: List[LogEntry] = []
        result = list(tags)
        changed = False
        dropped: List[str] = []

        owners: Dict[str, TagEntry] = {}
        for tag in list(result):
            if tag not in result:
                continue
            for name, value in tag.features.items():
                if name not in owners:
                    owners[name] = tag
                    continue
                existing = owners[name]
                if existing.features.get(name) == value:
                    continue
                keep, drop = self._choose_keep(existing, tag, fixed)
                if drop in result:
                    result.remove(drop)
                    changed = True
                    dropped.append(drop.tag)
                    logs.append(
                        LogEntry(
                            level="warning",
                            code="FEATURE_CONFLICT_REMOVED",
                            message=f"Removed '{drop.tag}' due to conflicting feature '{name}'.",
                            details={"feature": name, "kept": keep.tag, "removed": drop.tag},
                        )
                    )
                owners[name] = keep
                if drop is tag:
                    break

        return result, logs, changed, dropped

    def _choose_keep(
        self, a: TagEntry, b: TagEntry, fixed: Set[str]
    ) -> Tuple[TagEntry, TagEntry]:
        a_fixed = a.tag.strip().lower() in fixed or a.source == "fixed"
        b_fixed = b.tag.strip().lower() in fixed or b.source == "fixed"
        if a_fixed and not b_fixed:
            return a, b
        if b_fixed and not a_fixed:
            return b, a

        if a.priority != b.priority:
            return (a, b) if a.priority > b.priority else (b, a)

        return (a, b) if a.order <= b.order else (b, a)
