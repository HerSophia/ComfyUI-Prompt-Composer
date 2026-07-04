"""Core data models for Prompt Composer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Set


JsonDict = Dict[str, Any]


@dataclass
class LogEntry:
    """A structured log entry emitted by the core pipeline."""

    level: str
    code: str
    message: str
    details: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class TagEntry:
    """A tag entry loaded from JSON data."""

    tag: str
    category: str
    aliases: List[str] = field(default_factory=list)
    weight: float = 1.0
    requires: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    implies: List[str] = field(default_factory=list)
    features: JsonDict = field(default_factory=dict)
    priority: int = 0
    enabled: bool = True
    label_zh: str = ""
    post_count: int = 0
    rating: str = "general"
    source: str = "sampled"
    order: int = 0

    @classmethod
    def from_dict(cls, data: JsonDict, source: str = "sampled") -> "TagEntry":
        if not isinstance(data, dict):
            raise ValueError("Tag entry must be an object.")
        tag = data.get("tag")
        category = data.get("category")
        if not isinstance(tag, str) or not tag.strip():
            raise ValueError("Tag entry is missing required string field 'tag'.")
        if not isinstance(category, str) or not category.strip():
            raise ValueError(f"Tag '{tag}' is missing required string field 'category'.")

        return cls(
            tag=tag.strip(),
            category=category.strip(),
            aliases=list(data.get("aliases", [])),
            weight=float(data.get("weight", 1.0)),
            requires=list(data.get("requires", [])),
            conflicts=list(data.get("conflicts", [])),
            implies=list(data.get("implies", [])),
            features=dict(data.get("features", {})),
            priority=int(data.get("priority", 0)),
            enabled=bool(data.get("enabled", True)),
            label_zh=str(data.get("label_zh", "")),
            post_count=int(data.get("post_count", 0)),
            rating=str(data.get("rating", "general")),
            source=source,
        )

    def clone(self, source: Optional[str] = None, order: Optional[int] = None) -> "TagEntry":
        return TagEntry(
            tag=self.tag,
            category=self.category,
            aliases=list(self.aliases),
            weight=self.weight,
            requires=list(self.requires),
            conflicts=list(self.conflicts),
            implies=list(self.implies),
            features=dict(self.features),
            priority=self.priority,
            enabled=self.enabled,
            label_zh=self.label_zh,
            post_count=self.post_count,
            rating=self.rating,
            source=self.source if source is None else source,
            order=self.order if order is None else order,
        )

    def to_dict(self) -> JsonDict:
        return {
            "tag": self.tag,
            "category": self.category,
            "aliases": list(self.aliases),
            "weight": self.weight,
            "requires": list(self.requires),
            "conflicts": list(self.conflicts),
            "implies": list(self.implies),
            "features": dict(self.features),
            "priority": self.priority,
            "enabled": self.enabled,
            "label_zh": self.label_zh,
            "post_count": self.post_count,
            "rating": self.rating,
            "source": self.source,
            "order": self.order,
        }


@dataclass
class ASTNode:
    """A value node inside PromptAST."""

    value: str
    category: str
    source: str = "sampled"
    weight: float = 1.0
    priority: int = 0

    @classmethod
    def from_tag(cls, tag: TagEntry) -> "ASTNode":
        return cls(
            value=tag.tag,
            category=tag.category,
            source=tag.source,
            weight=tag.weight,
            priority=tag.priority,
        )

    def to_dict(self) -> JsonDict:
        return {
            "value": self.value,
            "category": self.category,
            "source": self.source,
            "weight": self.weight,
            "priority": self.priority,
        }


@dataclass
class PromptAST:
    """Structured prompt representation."""

    character: JsonDict = field(
        default_factory=lambda: {
            "gender": [],
            "body": [],
            "face": [],
            "hair": [],
            "eyes": [],
            "ears": [],
            "clothing": [],
            "accessory": [],
        }
    )
    pose: JsonDict = field(
        default_factory=lambda: {"body": [], "hand": [], "leg": [], "expression": []}
    )
    camera: JsonDict = field(
        default_factory=lambda: {"angle": [], "shot": [], "composition": []}
    )
    environment: JsonDict = field(
        default_factory=lambda: {"background": [], "weather": [], "lighting": []}
    )
    style: JsonDict = field(default_factory=lambda: {"quality": [], "style_tags": []})
    nsfw: JsonDict = field(
        default_factory=lambda: {"act": [], "body": [], "gear": []}
    )
    meta: JsonDict = field(
        default_factory=lambda: {"features": {}, "source_tags": [], "logs": [], "unknown_tags": []}
    )

    def add_node(self, path: Sequence[str], node: ASTNode) -> None:
        target: Any = self
        for part in path[:-1]:
            target = getattr(target, part) if hasattr(target, part) else target[part]
        leaf = path[-1]
        container = getattr(target, leaf) if hasattr(target, leaf) else target[leaf]
        container.append(node)

    def to_dict(self) -> JsonDict:
        return {
            "character": _nodes_to_dict(self.character),
            "pose": _nodes_to_dict(self.pose),
            "camera": _nodes_to_dict(self.camera),
            "environment": _nodes_to_dict(self.environment),
            "style": _nodes_to_dict(self.style),
            "nsfw": _nodes_to_dict(self.nsfw),
            "meta": _nodes_to_dict(self.meta),
        }


def _nodes_to_dict(value: Any) -> Any:
    if isinstance(value, ASTNode):
        return value.to_dict()
    if isinstance(value, LogEntry):
        return value.to_dict()
    if isinstance(value, TagEntry):
        return value.to_dict()
    if isinstance(value, list):
        return [_nodes_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: _nodes_to_dict(item) for key, item in value.items()}
    return value


@dataclass
class ResolverConfig:
    max_rounds: int = 5


@dataclass
class SamplingContext:
    seed: int = 0
    disabled_tags: Set[str] = field(default_factory=set)
    fixed_tags: Set[str] = field(default_factory=set)
    rating: str = "general"
    # 关联加成开关。默认关闭，关闭时采样与原来完全一致。
    association_boost: bool = False
    # 加成强度系数。为 0 等价于关闭。
    association_strength: float = 0.0
    # 已选标签集合（小写），采样循环里动态维护。
    selected_tags: Set[str] = field(default_factory=set)
    # 关联查询入口：给定已选标签，返回 {关联标签: 权重}。为 None 表示无关联。
    association_lookup: Optional[Callable[[str], Dict[str, float]]] = None
    # 冲突查询入口：给定标签，返回其冲突标签集合。为 None 表示不预检。
    conflict_lookup: Optional[Callable[[str], Set[str]]] = None


@dataclass
class GenerationRequest:
    seed: int = 0
    categories: List[str] = field(
        default_factory=lambda: [
            "pose",
            "hand",
            "leg",
            "expression",
            "camera",
            "composition",
            "clothing",
            "background",
            "lighting",
        ]
    )
    fixed_tags: List[str] = field(default_factory=list)
    disabled_tags: List[str] = field(default_factory=list)
    sampler: str = "weighted"
    compiler: str = "danbooru"
    max_resolve_rounds: int = 5
    # 二创相关字段。
    # identity 为空表示原创；非空时锁定对应角色。
    identity: Optional[str] = None
    # 锁定不参与随机的分类（通常是角色识别特征所在分类）。
    lock_categories: List[str] = field(default_factory=list)
    # 参与随机的分类。为 None 时回退到 categories。
    random_categories: Optional[List[str]] = None
    # 分级。general 只出全年龄；explicit 放出 NSFW 内容。
    rating: str = "general"
    # 标签到权重的映射，空表示不加权。键是标签原文。
    weights: Dict[str, float] = field(default_factory=dict)
    # 是否启用内置负面词，默认启用。
    use_builtin_negative: bool = True
    # 用户追加的负面词列表。
    user_negative: List[str] = field(default_factory=list)
    # 是否把互斥淘汰的标签回收进负面，默认关闭。
    recycle_conflict_negative: bool = False
    # 关联加成：采样时根据已选标签抬高关联候选的权重，默认关闭。
    association_boost: bool = False
    # 关联加成强度系数，为 0 等价于关闭。
    association_strength: float = 0.0
    # 采样完成后自动追加已选标签的硬依赖 requires，默认关闭。
    auto_add_requires: bool = False
    # 采样完成后自动追加已选标签的软关联 related，默认关闭。
    auto_add_related: bool = False
    # 自动追加软关联时，每个已选标签最多补多少个关联词。
    auto_add_related_limit: int = 3

    def effective_categories(self) -> List[str]:
        """实际参与采样的分类。random_categories 优先，否则用 categories。

        rating 为 general 时过滤掉 nsfw_ 开头的分类，防止误入 NSFW。
        explicit 时的 nsfw 分类补充由 pipeline 负责。
        """
        cats = self.random_categories if self.random_categories is not None else self.categories
        lock = {c.strip() for c in self.lock_categories}
        result = [c for c in cats if c not in lock]
        if self.rating != "explicit":
            result = [c for c in result if not c.startswith("nsfw_")]
        return result


@dataclass
class Identity:
    """一个已有角色的身份。锁定的是特征和固定 tag。"""

    id: str
    name: str = ""
    identity_tags: List[str] = field(default_factory=list)
    locked_features: JsonDict = field(default_factory=dict)
    default_tags: JsonDict = field(default_factory=dict)
    default_clothing: List[str] = field(default_factory=list)
    optional_clothing: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: JsonDict) -> "Identity":
        if not isinstance(data, dict):
            raise ValueError("Identity must be an object.")
        identity_id = data.get("id")
        if not isinstance(identity_id, str) or not identity_id.strip():
            raise ValueError("Identity is missing required string field 'id'.")
        return cls(
            id=identity_id.strip(),
            name=str(data.get("name", "")),
            identity_tags=list(data.get("identity_tags", [])),
            locked_features=dict(data.get("locked_features", {})),
            default_tags=dict(data.get("default_tags", {})),
            default_clothing=list(data.get("default_clothing", [])),
            optional_clothing=list(data.get("optional_clothing", [])),
        )

    def to_dict(self) -> JsonDict:
        return {
            "id": self.id,
            "name": self.name,
            "identity_tags": list(self.identity_tags),
            "locked_features": dict(self.locked_features),
            "default_tags": dict(self.default_tags),
            "default_clothing": list(self.default_clothing),
            "optional_clothing": list(self.optional_clothing),
        }


@dataclass
class GenerationResponse:
    prompt: str
    ast: PromptAST
    features: JsonDict
    selected_tags: List[TagEntry]
    logs: List[LogEntry]
    # 根据提示词推断出的建议分辨率。默认 3:4。
    width: int = 896
    height: int = 1152
    # 组装出的负面提示词，默认空串。
    negative: str = ""

    def to_dict(self) -> JsonDict:
        return {
            "prompt": self.prompt,
            "ast": self.ast.to_dict(),
            "features": dict(self.features),
            "selected_tags": [tag.to_dict() for tag in self.selected_tags],
            "logs": [log.to_dict() for log in self.logs],
            "width": self.width,
            "height": self.height,
            "negative": self.negative,
        }
