"""负面提示词数据与组装逻辑。

维护一份内置负面词，按分级分组，并提供一个组装函数，把内置负面词、
用户负面词、以及可选的互斥回收标签合并去重后输出成负面提示词字符串。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence


# 内置负面词，按分级分组。
# general 组是任何分级都会用到的通用负面词。
# explicit 组是成人分级时在 general 之外再追加的负面词。
BUILTIN_NEGATIVES: Dict[str, List[str]] = {
    "general": [
        "lowres",
        "worst quality",
        "low quality",
        "normal quality",
        "jpeg artifacts",
        "blurry",
        "bad anatomy",
        "bad hands",
        "bad proportions",
        "extra limbs",
        "extra digits",
        "fewer digits",
        "missing fingers",
        "mutated hands",
        "malformed limbs",
        "long neck",
        "cropped",
        "signature",
        "watermark",
        "username",
        "text",
        "error",
    ],
    "explicit": [
        "censored",
        "mosaic censoring",
        "bar censor",
    ],
}


def builtin_negatives_for(rating: str) -> List[str]:
    """按分级返回内置负面词。explicit 在 general 基础上追加 explicit组。"""
    result = list(BUILTIN_NEGATIVES.get("general", []))
    if str(rating).strip().lower() == "explicit":
        result.extend(BUILTIN_NEGATIVES.get("explicit", []))
    return result


def build_negative(
    rating: str = "general",
    use_builtin: bool = True,
    user_negative: Optional[Sequence[str]] = None,
    recycle_tags: Optional[Sequence[str]] = None,
) -> str:
    """组装负面提示词字符串。

    参数：
    - rating：分级，决定内置负面词的取用范围。
    - use_builtin：是否启用内置负面词。
    - user_negative：用户追加的负面词列表。
    - recycle_tags：可选的互斥回收标签列表。

    去重按小写比对，保留首次出现的原文，用逗号加空格连接。
    全部为空时返回空字符串。
    """
    parts: List[str] = []
    if use_builtin:
        parts.extend(builtin_negatives_for(rating))
    if user_negative:
        parts.extend(str(item) for item in user_negative)
    if recycle_tags:
        parts.extend(str(item) for item in recycle_tags)

    seen = set()
    result: List[str] = []
    for item in parts:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return ", ".join(result)
