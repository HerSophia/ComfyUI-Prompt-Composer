"""根据提示词内容推断合理的图片分辨率。

思路分两步：先判断画面朝向（竖向或横向），再按镜头景别选择竖长程度档位。

- 朝向：默认竖向。当标签里出现明确的横向信号时改为横向。
  横向信号包括风景为主体（scenery 等）和多人群像（multiple_girls 等）。
- 景别：取 camera 分类里的景别标签，映射到强度档。特写最接近正方形，
  全身或极端构图最竖长。命中多个景别时取最竖长的一档。

映射表和信号集合集中定义为常量，方便后续调整。core 不依赖 ComfyUI。
"""

from __future__ import annotations

from typing import Iterable, Set, Tuple


# 景别标签到强度档的映射。档位数字越大，画面越竖长（横向时越宽）。
# 0 最接近正方形，4 最狭长。
_SHOT_LEVELS = {
    # 特写、脸部、肖像：接近正方形。
    "close-up": 0,
    "close_up": 0,
    "closeup": 0,
    "face_focus": 0,
    "eyes_focus": 0,
    "portrait": 0,
    "profile": 0,
    # 上半身。
    "upper_body": 1,
    "bust": 1,
    # 上半身到大腿、中景。
    "cowboy_shot": 2,
    "medium_shot": 2,
    # 全身、下半身。
    "full_shot": 3,
    "wide_shot": 3,
    "lower_body": 3,
    # 脚部、臀部特写等极端构图。
    "foot_focus": 4,
    "feet_focus": 4,
    "pov_feet": 4,
    "hip_focus": 4,
    "hips": 4,
}


# 竖向各强度档的宽高。
_PORTRAIT_BY_LEVEL = {
    0: (1024, 1024),  # 1:1
    1: (896, 1152),   # 3:4
    2: (832, 1216),   # 5:8
    3: (768, 1344),   # 9:16
    4: (640, 1536),   # 9:21
}


# 横向各强度档的宽高（竖向的宽高对调）。
_LANDSCAPE_BY_LEVEL = {
    0: (1024, 1024),  # 1:1
    1: (1152, 896),   # 4:3
    2: (1216, 832),   # 8:5
    3: (1344, 768),   # 16:9
    4: (1536, 640),   # 21:9
}


# 无景别标签时的默认档：竖向 3:4，横向 16:9。
_DEFAULT_PORTRAIT_LEVEL = 1
_DEFAULT_LANDSCAPE_LEVEL = 3


# 横向信号标签。命中任意一个则判为横向。
_LANDSCAPE_SIGNALS = {
    # 风景为主体。
    "scenery",
    "landscape",
    "cityscape",
    "nature",
    "horizon",
    # 多人群像。
    "multiple_girls",
    "multiple_boys",
    "2girls",
    "3girls",
    "4girls",
    "5girls",
    "6+girls",
    "2boys",
    "3boys",
    "multiple_people",
    "group",
    "crowd",
    "everyone",
}


def _normalize(tags: Iterable[str]) -> Set[str]:
    """把标签规整为小写、去空白的集合。"""
    result: Set[str] = set()
    for tag in tags:
        if not tag:
            continue
        key = str(tag).strip().lower()
        if key:
            result.add(key)
    return result


def infer_resolution(tags: Iterable[str]) -> Tuple[int, int]:
    """根据标签集合推断分辨率，返回 (width, height)。

    先判断朝向，再按景别取最竖长的一档；无景别时取默认档。
    """
    tag_set = _normalize(tags)

    # 第一步：判断朝向。默认竖向，命中横向信号则转横向。
    is_landscape = bool(tag_set & _LANDSCAPE_SIGNALS)

    # 第二步：按景别取强度档。命中多个时取最大（最竖长）。
    levels = [_SHOT_LEVELS[tag] for tag in tag_set if tag in _SHOT_LEVELS]
    if levels:
        level = max(levels)
    else:
        level = _DEFAULT_LANDSCAPE_LEVEL if is_landscape else _DEFAULT_PORTRAIT_LEVEL

    table = _LANDSCAPE_BY_LEVEL if is_landscape else _PORTRAIT_BY_LEVEL
    return table[level]
