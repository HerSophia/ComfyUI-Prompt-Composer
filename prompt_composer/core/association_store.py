"""关联数据加载与查询。

从 data/associations.json 读取标签关联，提供按标签查关联列表的方法。

关联文件由离线脚本 tools/build_associations.py 产出并随仓库提交，
放在 data 目录、与索引文件同级，不放进 semantic 目录，避免被 TagStore
当成标签数据加载。

加载策略：
    进程内缓存。第一次查询时才读文件，读一次后常驻内存。
    文件缺失或格式异常时，关联表为空，任何查询都返回空列表，
    依赖关联的功能因此退化为无关联，保证默认行为不变。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ASSOCIATIONS_PATH = DATA_DIR / "associations.json"


def _normalize(value: str) -> str:
    """标签归一：去空白、转小写。与 core 其他模块保持一致。"""
    return value.strip().lower()


class AssociationStore:
    """标签关联的内存索引。

    数据结构：tag -> [ {"tag": 关联标签, "weight": 权重}, ... ]，
    每个标签的关联列表已在离线阶段按权重降序排好、设过上限。
    """

    def __init__(self, associations: Optional[Dict[str, List[Dict[str, object]]]] = None) -> None:
        self._by_tag: Dict[str, List[Dict[str, object]]] = {}
        if associations:
            for tag, items in associations.items():
                self._by_tag[_normalize(str(tag))] = self._clean_items(items)

    @staticmethod
    def _clean_items(items: object) -> List[Dict[str, object]]:
        """规整一个标签的关联列表，丢弃结构不合法的项。"""
        cleaned: List[Dict[str, object]] = []
        if not isinstance(items, list):
            return cleaned
        for item in items:
            if not isinstance(item, dict):
                continue
            tag = _normalize(str(item.get("tag", "") or ""))
            if not tag:
                continue
            try:
                weight = float(item.get("weight", 0.0) or 0.0)
            except (TypeError, ValueError):
                weight = 0.0
            cleaned.append({"tag": tag, "weight": weight})
        return cleaned

    @classmethod
    def from_file(cls, path: Optional[str | Path] = None) -> "AssociationStore":
        """从关联文件加载。文件缺失或格式异常时返回空实例，不抛异常。"""
        file_path = Path(path) if path is not None else ASSOCIATIONS_PATH
        if not file_path.exists():
            return cls()
        try:
            with file_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        return cls(raw)

    def related(self, tag: str, limit: int = 0) -> List[Dict[str, object]]:
        """返回某标签的关联列表，元素为 {"tag", "weight"}，按权重降序。

        limit > 0 时只取前若干项。标签不存在时返回空列表。
        """
        if not tag:
            return []
        items = self._by_tag.get(_normalize(tag))
        if not items:
            return []
        if limit and limit > 0:
            return [dict(item) for item in items[:limit]]
        return [dict(item) for item in items]

    def related_tags(self, tag: str, limit: int = 0) -> List[str]:
        """只返回关联标签名，按权重降序。"""
        return [item["tag"] for item in self.related(tag, limit=limit)]

    def weight_of(self, tag: str, other: str) -> float:
        """返回 tag 对 other 的关联权重，没有关联时返回 0.0。"""
        if not tag or not other:
            return 0.0
        target = _normalize(other)
        for item in self._by_tag.get(_normalize(tag), []):
            if item["tag"] == target:
                return float(item["weight"])
        return 0.0

    def has(self, tag: str) -> bool:
        """标签是否有关联数据。"""
        return _normalize(tag) in self._by_tag if tag else False

    def tags(self) -> List[str]:
        """所有有关联数据的标签。"""
        return list(self._by_tag.keys())


_DEFAULT_STORE: Optional[AssociationStore] = None


def load_default_association_store() -> AssociationStore:
    """加载默认关联数据，进程内缓存。第一次调用时读文件。"""
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = AssociationStore.from_file()
    return _DEFAULT_STORE
