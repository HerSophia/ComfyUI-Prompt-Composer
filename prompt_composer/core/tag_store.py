"""Tag data loading and lookup.

三层数据加载：
    Semantic 层：data/semantic/*.json，提供分类和基础字段。
    Rules overlay：data/semantic/rules/overlay.json，人工维护的约束规则。
    User 层：data/user/*.json，用户覆盖，可为空。

合并优先级：Semantic -> Rules -> User，后者覆盖前者。
只有出现在 Semantic 层、被明确分类的 tag，才会进入候选。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .models import TagEntry


# overlay 里允许叠加的约束字段。基础字段（weight、aliases 等）不在这里覆盖。
_OVERLAY_FIELDS = ("requires", "conflicts", "implies", "features", "priority", "enabled")


class TagStore:
    """In-memory index for tag entries."""

    def __init__(self, entries: Iterable[TagEntry]) -> None:
        self._by_tag: Dict[str, TagEntry] = {}
        self._by_alias: Dict[str, TagEntry] = {}
        self._by_category: Dict[str, List[TagEntry]] = {}

        for entry in entries:
            self.add(entry)

    @classmethod
    def from_directory(cls, data_dir: str | Path) -> "TagStore":
        """从单个目录加载所有 *.json（不递归子目录）。第一版接口，保留兼容。"""
        path = Path(data_dir)
        if not path.exists():
            raise FileNotFoundError(f"Tag data directory does not exist: {path}")
        entries = cls._load_dir(path)
        return cls(entries)

    @classmethod
    def from_layers(
        cls,
        semantic_dir: str | Path,
        rules_path: Optional[str | Path] = None,
        user_dir: Optional[str | Path] = None,
    ) -> "TagStore":
        """三层加载：Semantic 目录 + Rules overlay + User 目录。"""
        semantic = Path(semantic_dir)
        if not semantic.exists():
            raise FileNotFoundError(f"Semantic directory does not exist: {semantic}")

        store = cls(cls._load_dir(semantic))

        if rules_path is not None:
            rules = Path(rules_path)
            if rules.exists():
                store.apply_overlay_file(rules)

        if user_dir is not None:
            user = Path(user_dir)
            if user.exists():
                for entry in cls._load_dir(user):
                    store.upsert(entry)

        return store

    @staticmethod
    def _load_dir(path: Path) -> List[TagEntry]:
        """加载一个目录下所有 *.json（一层，不递归）。"""
        entries: List[TagEntry] = []
        for file_path in sorted(path.glob("*.json")):
            with file_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
            if not isinstance(raw, list):
                raise ValueError(f"Tag data file must contain a list: {file_path}")
            for item in raw:
                try:
                    entries.append(TagEntry.from_dict(item))
                except ValueError as exc:
                    raise ValueError(f"Invalid tag entry in {file_path}: {exc}") from exc
        return entries

    def add(self, entry: TagEntry) -> None:
        key = _normalize(entry.tag)
        if key in self._by_tag:
            raise ValueError(f"Duplicate tag entry: {entry.tag}")
        self._by_tag[key] = entry

        for alias in entry.aliases:
            alias_key = _normalize(alias)
            if alias_key and alias_key not in self._by_tag:
                self._by_alias[alias_key] = entry

        self._by_category.setdefault(entry.category, []).append(entry)

    def upsert(self, entry: TagEntry) -> None:
        """存在则替换，不存在则新增。用于 User 层覆盖。"""
        key = _normalize(entry.tag)
        existing = self._by_tag.get(key)
        if existing is None:
            self.add(entry)
            return
        # 替换分类索引里的旧对象。
        bucket = self._by_category.get(existing.category, [])
        self._by_category[existing.category] = [e for e in bucket if e is not existing]
        self._by_tag[key] = entry
        self._by_category.setdefault(entry.category, []).append(entry)
        for alias in entry.aliases:
            alias_key = _normalize(alias)
            if alias_key and alias_key not in self._by_tag:
                self._by_alias[alias_key] = entry

    def apply_overlay_file(self, rules_path: str | Path) -> None:
        """读取 overlay 文件并叠加约束规则。"""
        path = Path(rules_path)
        with path.open("r", encoding="utf-8") as file:
            rules = json.load(file)
        if not isinstance(rules, list):
            raise ValueError(f"Rules overlay must contain a list: {path}")
        for rule in rules:
            self.apply_overlay(rule)

    def apply_overlay(self, rule: dict) -> None:
        """把一条 overlay 规则叠加到对应 tag。tag 不存在则忽略。"""
        tag = rule.get("tag")
        if not isinstance(tag, str):
            return
        entry = self._by_tag.get(_normalize(tag))
        if entry is None:
            return
        for field_name in _OVERLAY_FIELDS:
            if field_name not in rule:
                continue
            value = rule[field_name]
            if field_name in ("requires", "conflicts", "implies"):
                setattr(entry, field_name, list(value))
            elif field_name == "features":
                merged = dict(entry.features)
                merged.update(value)
                entry.features = merged
            elif field_name == "priority":
                entry.priority = int(value)
            elif field_name == "enabled":
                entry.enabled = bool(value)

    def get(self, tag: str) -> Optional[TagEntry]:
        return self._by_tag.get(_normalize(tag))

    def find(self, name: str) -> Optional[TagEntry]:
        key = _normalize(name)
        return self._by_tag.get(key) or self._by_alias.get(key)

    def by_category(self, category: str, include_disabled: bool = False) -> List[TagEntry]:
        entries = list(self._by_category.get(category, []))
        if include_disabled:
            return entries
        return [entry for entry in entries if entry.enabled]

    def categories(self) -> List[str]:
        return sorted(self._by_category.keys())

    def all(self) -> List[TagEntry]:
        return list(self._by_tag.values())


def _normalize(value: str) -> str:
    return value.strip().lower()
