"""导入脚本：把 Danbooru CSV 和 zh_CN.yaml 合并成 Semantic 层数据。

用途：
    读取 Raw 层的 Danbooru CSV（提供 post_count 和 aliases），
    读取 zh_CN.yaml（提供细粒度分类和中文），
    通过 category_map.yaml 把 group 映射到我们的分类，
    通过 cleanup_rules.yaml 过滤不适合的 tag，
    只保留能匹配到分类的 tag，按分类分别写出 semantic JSON。

原则：
    1. 只生成分类和基础字段（tag、category、weight、aliases、label_zh、post_count）。
    2. 不生成 requires、conflicts、features，这些由人工在 rules overlay 里维护。
    3. 过滤 artist 类和 post_count 低于阈值的条目。
    4. 可重复运行。它只覆盖 semantic 分类文件，不动 rules 和 identities。

运行：
    python -m prompt_composer.tools.import_danbooru
    或
python prompt_composer/tools/import_danbooru.py
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

import yaml


# ---- 路径 ----
TOOLS_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = TOOLS_DIR.parent
PROJECT_ROOT = PACKAGE_DIR.parent

RAW_CSV = PACKAGE_DIR / "data" / "raw" / "danbooru_2026-04-01_pt20.csv"
ZH_YAML = PROJECT_ROOT / "来自其他插件的东西" / "zh_CN.yaml"
CATEGORY_MAP = TOOLS_DIR / "category_map.yaml"
CLEANUP_RULES = TOOLS_DIR / "cleanup_rules.yaml"
NSFW_TAGS = TOOLS_DIR / "nsfw_tags.yaml"
SEMANTIC_DIR = PACKAGE_DIR / "data" / "semantic"

# ---- 参数 ----
# Danbooru category 编码：0=general,1=artist,3=copyright,4=character,5=meta
ARTIST_CODE = "1"
# post_count 阈值。低于这个值的 tag 不导入，减少冷门噪音。
MIN_POST_COUNT = 200
# 每个分类最多保留多少个 tag，按 post_count 从高到低。0 表示不限制。
MAX_PER_CATEGORY = 400


def load_category_map() -> Tuple[Dict[str, str], object]:
    """读取 category_map.yaml，返回 (group键 -> 目标分类) 和默认值。"""
    data = yaml.safe_load(CATEGORY_MAP.read_text(encoding="utf-8"))
    mapping = {}
    for key, value in (data.get("mapping") or {}).items():
        mapping[key.strip()] = value
    default = data.get("default", None)
    return mapping, default


def load_cleanup_rules() -> dict:
    """读取清洗规则。"""
    if not CLEANUP_RULES.exists():
        return {}
    return yaml.safe_load(CLEANUP_RULES.read_text(encoding="utf-8")) or {}


def make_cleanup_filter(rules: dict):
    """根据清洗规则返回一个判断函数：should_drop(tag) -> bool。"""
    drop_substrings = [s.lower() for s in rules.get("drop_substrings", [])]
    drop_exact = {s.lower() for s in rules.get("drop_exact", [])}
    drop_prefixes = [s.lower() for s in rules.get("drop_prefixes", [])]

    def should_drop(tag: str) -> bool:
        low = tag.lower()
        if low in drop_exact:
            return True
        for sub in drop_substrings:
            if sub in low:
                return True
        for prefix in drop_prefixes:
            if low.startswith(prefix):
                return True
        return False

    return should_drop


def load_tag_categories(mapping: Dict[str, str], default) -> Dict[str, Tuple[str, str]]:
    """读取 zh_CN.yaml，返回 tag(小写,下划线) -> (目标分类, 中文)。

    一个 tag 可能出现在多个 group。取第一个能映射到有效分类的。
    """
    data = yaml.safe_load(ZH_YAML.read_text(encoding="utf-8"))
    result: Dict[str, Tuple[str, str]] = {}

    for top in data:
        top_name = str(top.get("name", "")).strip().strip('"').strip(":")
        for group in top.get("groups", []) or []:
            group_name = str(group.get("name", "")).strip().strip('"').strip(":")
            key = f"{top_name} > {group_name}"
            target = mapping.get(key, default)
            if not target:
                continue
            tags = group.get("tags", {}) or {}
            for raw_tag, zh in tags.items():
                tag = str(raw_tag).strip().lower()
                if not tag:
                    continue
                # 规范化：空格转下划线，Danbooru 规范写法用下划线。
                # 这样 "long hair" 和 "long_hair" 归一到同一个键，避免重复。
                tag = tag.replace(" ", "_")
                # 中文翻译里可能带 "A|B"，取第一个。
                label = str(zh).split("|")[0].strip()
                if tag not in result:
                    result[tag] = (target, label)
    return result


def load_csv_info() -> Dict[str, Tuple[str, int, List[str]]]:
    """读取 Danbooru CSV，返回 tag(小写) -> (category编码, post_count, aliases)。"""
    result: Dict[str, Tuple[str, int, List[str]]] = {}
    with RAW_CSV.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        for row in reader:
            if len(row) < 3:
                continue
            tag = row[0].strip().lower()
            code = row[1].strip()
            try:
                post_count = int(row[2])
            except ValueError:
                continue
            aliases_raw = row[3] if len(row) >= 4 else ""
            aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]
            result[tag] = (code, post_count, aliases)
    return result


def weight_from_count(post_count: int) -> float:
    """把 post_count 换算成合理权重。用对数避免热门 tag 权重过高。"""
    if post_count <= 0:
        return 1.0
    return round(math.log10(post_count + 10), 2)


def build_entries(
    tag_categories: Dict[str, Tuple[str, str]],
    csv_info: Dict[str, Tuple[str, int, List[str]]],
    should_drop=None,
) -> Dict[str, List[dict]]:
    """交叉两份数据，生成按目标分类分组的 TagEntry 字典列表。"""
    by_category: Dict[str, List[dict]] = {}
    dropped = 0

    for tag, (category, label) in tag_categories.items():
        if should_drop is not None and should_drop(tag):
            dropped += 1
            continue

        info = csv_info.get(tag)
        if info is None:
            # CSV 里没有这个 tag（可能是别名或冷门）。仍然导入，但用默认权重。
            code, post_count, aliases = "0", 0, []
        else:
            code, post_count, aliases = info
            if code == ARTIST_CODE:
                continue
            if post_count < MIN_POST_COUNT:
                continue

        entry = {
            "tag": tag,
            "category": category,
            "weight": weight_from_count(post_count),
            "aliases": aliases,
            "label_zh": label,
            "post_count": post_count,
        }
        by_category.setdefault(category, []).append(entry)

    # 每个分类内按 post_count 降序，并按上限截断。
    for category, entries in by_category.items():
        entries.sort(key=lambda e: e["post_count"], reverse=True)
        if MAX_PER_CATEGORY > 0 and len(entries) > MAX_PER_CATEGORY:
            by_category[category] = entries[:MAX_PER_CATEGORY]

    print(f"  清洗丢弃 {dropped} 个 tag")
    return by_category


def write_output(by_category: Dict[str, List[dict]]) -> None:
    SEMANTIC_DIR.mkdir(parents=True, exist_ok=True)
    for category, entries in sorted(by_category.items()):
        out_path = SEMANTIC_DIR / f"{category}.json"
        out_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  {category}.json : {len(entries)} tags")


def load_nsfw_tags() -> Dict[str, Tuple[str, str]]:
    """读取 NSFW 词表，返回 tag -> (目标分类, 中文)。"""
    if not NSFW_TAGS.exists():
        return {}
    data = yaml.safe_load(NSFW_TAGS.read_text(encoding="utf-8")) or {}
    result: Dict[str, Tuple[str, str]] = {}
    for tag, value in (data.get("tags") or {}).items():
        tag = str(tag).strip().lower()
        if not tag or not isinstance(value, list) or len(value) < 2:
            continue
        category = str(value[0]).strip()
        label = str(value[1]).strip()
        result[tag] = (category, label)
    return result


def build_nsfw_entries(
    nsfw_tags: Dict[str, Tuple[str, str]],
    csv_info: Dict[str, Tuple[str, int, List[str]]],
    existing_tags=None,
) -> Dict[str, List[dict]]:
    """生成 NSFW 分类的 TagEntry 字典列表。

    NSFW 词不走 cleanup 清洗、不走 MIN_POST_COUNT 过滤，全部标 rating=explicit。
    从 CSV 取 post_count 和 aliases，没有就用默认值。
    已在普通分类出现的 tag 跳过，避免跨分类重复。
    """
    existing= existing_tags or set()
    by_category: Dict[str, List[dict]] = {}
    for tag, (category, label) in nsfw_tags.items():
        if tag in existing:
            continue
        info = csv_info.get(tag)
        if info is None:
            post_count, aliases = 0, []
        else:
            _code, post_count, aliases = info
        entry = {
            "tag": tag,
            "category": category,
            "weight": weight_from_count(post_count),
            "aliases": aliases,
            "label_zh": label,
            "post_count": post_count,
            "rating": "explicit",
        }
        by_category.setdefault(category, []).append(entry)

    for category, entries in by_category.items():
        entries.sort(key=lambda e: e["post_count"], reverse=True)
    return by_category


def main() -> None:
    print("读取分类映射表 ...")
    mapping, default = load_category_map()
    print(f"  映射条目 {len(mapping)}")

    print("读取清洗规则 ...")
    cleanup_rules = load_cleanup_rules()
    should_drop = make_cleanup_filter(cleanup_rules)

    print("读取 zh_CN.yaml 分类 ...")
    tag_categories = load_tag_categories(mapping, default)
    print(f"  已分类 tag {len(tag_categories)}")

    print("读取 Danbooru CSV ...")
    csv_info = load_csv_info()
    print(f"  CSV tag {len(csv_info)}")

    print("交叉并生成 semantic 数据 ...")
    by_category = build_entries(tag_categories, csv_info, should_drop)

    print("读取 NSFW 词表 ...")
    nsfw_tags = load_nsfw_tags()
    print(f"  NSFW tag {len(nsfw_tags)}")
    existing_tags = {e["tag"] for entries in by_category.values() for e in entries}
    nsfw_by_category = build_nsfw_entries(nsfw_tags, csv_info, existing_tags)
    for category, entries in nsfw_by_category.items():
        by_category[category] = entries

    total = sum(len(v) for v in by_category.values())
    print(f"写出 {len(by_category)} 个分类，共 {total} 个 tag：")
    write_output(by_category)
    print("完成。")


if __name__ == "__main__":
    main()
