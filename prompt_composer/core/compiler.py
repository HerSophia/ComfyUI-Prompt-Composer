"""Prompt compilers."""

from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional, Set

from .models import ASTNode, PromptAST


# 权重取值范围。经验上高于 1.5 或低于 0.6 都容易让画面出问题。
WEIGHT_MIN = 0.6
WEIGHT_MAX = 1.5


def format_weighted_tag(tag: str, weight: float) -> str:
    """按 A1111/ComfyUI 常见的圆括号写法给标签加权。

    规则：
    - 权重截断到 WEIGHT_MIN 到 WEIGHT_MAX。
    - 权重保留两位小数。
    - 权重等于 1.0 时不加括号，直接返回原标签。
    - 标签内的圆括号做转义，避免破坏权重语法。
    """
    try:
        value = float(weight)
    except (TypeError, ValueError):
        return tag
    if value < WEIGHT_MIN:
        value = WEIGHT_MIN
    elif value > WEIGHT_MAX:
        value = WEIGHT_MAX
    value = round(value, 2)
    if value == 1.0:
        return tag
    escaped = tag.replace("(", "\\(").replace(")", "\\)")
    return f"({escaped}:{value:.2f})"


def _normalize_weights(weights: Optional[Dict[str, float]]) -> Dict[str, float]:
    """把权重映射规整成小写键到浮点值的字典，非法项跳过。"""
    result: Dict[str, float] = {}
    if not weights:
        return result
    for key, value in weights.items():
        name = str(key).strip().lower()
        if not name:
            continue
        try:
            result[name] = float(value)
        except (TypeError, ValueError):
            continue
    return result


class BaseCompiler:
    """Compiler interface."""

    def compile(self, ast: PromptAST) -> str:
        raise NotImplementedError


class DanbooruCompiler(BaseCompiler):
    """Compile PromptAST into comma separated Danbooru tags."""

    ORDER = [
        ("character", "gender"),
        ("character", "body"),
        ("character", "face"),
        ("character", "hair"),
        ("character", "eyes"),
        ("character", "ears"),
        ("character", "clothing"),
        ("character", "accessory"),
        ("pose", "expression"),
        ("pose", "body"),
        ("pose", "hand"),
        ("pose", "leg"),
        ("camera", "angle"),
        ("camera", "shot"),
        ("camera", "composition"),
        ("nsfw", "body"),
        ("nsfw", "act"),
        ("nsfw", "gear"),
        ("environment", "background"),
        ("environment", "weather"),
        ("environment", "lighting"),
           ("style", "style_tags"),
        ("style", "quality"),
    ]

    def __init__(self, weights: Optional[Dict[str, float]] = None) -> None:
        # 权重映射的键统一按小写比对，与去重逻辑一致。空表示不加权。
        self.weights = _normalize_weights(weights)

    def compile(self, ast: PromptAST) -> str:
        tags: List[str] = []
        seen: Set[str] = set()
        for section_name, leaf_name in self.ORDER:
            section = getattr(ast, section_name)
            for value in section.get(leaf_name, []):
                tag = _node_value(value)
                key = tag.strip().lower()
                if not tag or key in seen:
                    continue
                if key in self.weights:
                    tags.append(format_weighted_tag(tag, self.weights[key]))
                else:
                    tags.append(tag)
                seen.add(key)
        return ", ".join(tags)


class DebugJsonCompiler(BaseCompiler):
    """Compile PromptAST to formatted JSON for debugging."""

    def compile(self, ast: PromptAST) -> str:
        return json.dumps(ast.to_dict(), ensure_ascii=False, indent=2)


def _node_value(value) -> str:
    if isinstance(value, ASTNode):
        return value.value
    if isinstance(value, dict):
        return str(value.get("value", ""))
    return str(value)


_COMPILERS = {
    "danbooru": DanbooruCompiler,
    "debug_json": DebugJsonCompiler,
    "json": DebugJsonCompiler,
}


def create_compiler(
    name: str, weights: Optional[Dict[str, float]] = None
) -> BaseCompiler:
    key = (name or "").strip().lower()
    compiler_cls = _COMPILERS.get(key)
    if compiler_cls is None:
        raise ValueError(f"Unknown compiler: {name}")
    # 只有 Danbooru 编译器支持权重，其余保持无参构造。
    if compiler_cls is DanbooruCompiler:
        return DanbooruCompiler(weights)
    return compiler_cls()
