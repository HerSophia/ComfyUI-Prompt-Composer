"""批量生成二创角色 identity 模板。

用 Danbooru 共现数据，为热度最高的一批角色自动推断发色、眼色、发型、
眼睛、服装，生成 identity JSON 文件。

数据来源：
    - 角色列表与热度：data/raw/danbooru_2026-04-01_pt20.csv（分类码 4 为角色）。
    - 角色共现：data/raw/danbooru_tags_cooccurrence.csv（tag_a, tag_b, count）。
    - 特征归类依据：data/semantic/*.json（标签 -> 分类、标签 -> post_count）。
    - 中文名：来自其他插件的东西/zh_CN.yaml。

生成的文件写到 data/semantic/identities/。默认不覆盖已存在的文件，
避免冲掉手写模板；加 --force 才会覆盖。

用法：
    python prompt_composer/tools/build_identities.py            # 生成热度前 150
    python prompt_composer/tools/build_identities.py --top 50   # 生成热度前 50
    python prompt_composer/tools/build_identities.py --force    # 覆盖已存在文件
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import yaml

# ---- 路径 ----
TOOLS_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = TOOLS_DIR.parent
PROJECT_ROOT = PACKAGE_DIR.parent

RAW_CSV = PACKAGE_DIR / "data" / "raw" / "danbooru_2026-04-01_pt20.csv"
COOCC_CSV = PACKAGE_DIR / "data" / "raw" / "danbooru_tags_cooccurrence.csv"
SEMANTIC_DIR = PACKAGE_DIR / "data" / "semantic"
IDENTITIES_DIR = SEMANTIC_DIR / "identities"
ZH_YAML = PROJECT_ROOT / "来自其他插件的东西" / "zh_CN.yaml"
# 10 万条 danbooru 标签中文翻译，覆盖广但含机翻噪音，作为中文名补充源。
ZH_TXT = PACKAGE_DIR / "data" / "raw" / "danbooru-10w-zh_cn.txt"

# ---- 参数 ----
# Danbooru category 编码：0=general,1=artist,3=copyright,4=character,5=meta
CHARACTER_CODE = "4"
# 第一批生成的角色数量。
DEFAULT_TOP = 150
# 手写模板的 id。这几个永远不被自动生成覆盖，即使加 --force。
PROTECTED_IDS = {"hatsune_miku", "hakurei_reimu", "artoria_pendragon"}

# 发色 / 眼色识别用的颜色词表。
COLORS = {
    "blue", "red", "green", "black", "brown", "blonde", "pink", "purple",
    "white", "grey", "gray", "silver", "aqua", "orange", "yellow",
    "light_brown", "light_blue", "dark_blue", "dark_green", "dark_skin",
    "multicolored", "two-tone", "gradient", "platinum_blonde", "streaked",
    "colored_inner",
}

# 发色 / 眼色推断时要跳过的状态词（它们分类是 eyes/hair 但不是颜色）。
EYE_STATE_WORDS = {"closed_eyes", "one_eye_closed", "half-closed_eyes"}

# 发型推断时要排除的通用词（发长、刘海，几乎每个角色都有，不算特色发型）。
HAIR_LENGTH_WORDS = {
    "long_hair", "short_hair", "medium_hair", "very_long_hair",
    "absurdly_long_hair", "hair_between_eyes",
}

# 发型每个角色最多取几个。
MAX_HAIR_STYLE = 3
# 眼睛描述最多取几个（一般只保留眼色，这里给一点余量）。
MAX_EYES = 1
# 服装最多取几个。
MAX_CLOTHING = 4


def load_characters(top: int) -> List[Tuple[str, int]]:
    """读取角色 CSV，返回热度前 top 的 [(标签, post_count)]。"""
    chars: List[Tuple[str, int]] = []
    with RAW_CSV.open("r", encoding="utf-8", newline="") as file:
        for row in csv.reader(file):
            if len(row) < 3:
                continue
            tag, code, count = row[0], row[1], row[2]
            if code != CHARACTER_CODE:
                continue
            try:
                chars.append((tag, int(count)))
            except ValueError:
                continue
    chars.sort(key=lambda x: x[1],reverse=True)
    return chars[:top]


def load_semantic_index() -> Tuple[Dict[str, str], Dict[str, int]]:
    """加载语义库，返回 (标签 -> 分类, 标签 -> post_count)。"""
    tag_category:Dict[str, str] = {}
    tag_post_count: Dict[str, int] = {}
    for json_file in SEMANTIC_DIR.glob("*.json"):
        entries = json.loads(json_file.read_text(encoding="utf-8"))
        for entry in entries:
            tag = str(entry.get("tag", "")).strip()
            if not tag:
                continue
            tag_category[tag] = str(entry.get("category", ""))
            try:
                tag_post_count[tag] = int(entry.get("post_count", 0))
            except (ValueError, TypeError):
                tag_post_count[tag] = 0
    return tag_category, tag_post_count


def _clean_zh_label(raw: str) -> str:
    """清洗一条中文翻译。

    翻译里可能有多个候选（空格或竖线分隔），且混有拼音、英文残留。
    规则：切成候选，取第一个含中文字符的候选；都不含中文则返回空串。
    """
    text = str(raw).strip()
    if not text:
        return ""
    parts: List[str] = []
    for chunk in text.replace("|", " ").split(" "):
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    for part in parts:
        if any("\u4e00" <= ch <= "\u9fff" for ch in part):
            return part
    return ""


def load_zh_names() -> Dict[str, str]:
    """加载中文名，返回 标签(小写) -> 中文名。

    合并两个源：zh_CN.yaml（人工翻译，优先）和 danbooru-10w-zh_cn.txt
    （覆盖广，补充）。先填 yaml，再用 txt 补齐 yaml 里没有的标签。
    """
    result: Dict[str, str] = {}

    if ZH_YAML.exists():
        data = yaml.safe_load(ZH_YAML.read_text(encoding="utf-8")) or []
        for top in data:
            for group in top.get("groups", []) or []:
                tags = group.get("tags", {}) or {}
                for raw_tag, zh in tags.items():
                    tag = str(raw_tag).strip().lower()
                    if not tag:
                        continue
                    label = _clean_zh_label(str(zh).split("|")[0])
                    if tag and label and tag not in result:
                        result[tag] = label

    if ZH_TXT.exists():
        for line in ZH_TXT.read_text(encoding="utf-8").splitlines():
            if "," not in line:
                continue
            raw_tag, zh = line.split(",", 1)
            tag = raw_tag.strip().lower()
            if not tag or tag in result:
                continue
            label = _clean_zh_label(zh)
            if label:
                result[tag] = label

    return result



def load_existing_identity_tags() -> Dict[str, str]:
    """扫描已存在的 identity 文件，返回 已占用标签(小写) -> 所属文件名。

    用于保护手写模板：如果一个角色标签已被某个现有模板占用（包括
    identity_tags 里的带后缀标签），就不再重复生成。
    """
    occupied: Dict[str, str] ={}
    if not IDENTITIES_DIR.exists():
        return occupied
    for file_path in IDENTITIES_DIR.glob("*.json"):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for tag in data.get("identity_tags", []) or []:
            occupied[str(tag).strip().lower()] = file_path.name
    return occupied


def scan_cooccurrence(targets: set) -> Dict[str, Dict[str, float]]:
    """流式扫共现 CSV，返回 角色 -> {伙伴标签: 共现次数}。

    共现是双向存储的，tag_a 和 tag_b 两列都要处理。
    """
    partners: Dict[str, Dict[str, float]] = {t: defaultdict(float) for t in targets}
    with COOCC_CSV.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)  # 跳过表头
        for row in reader:
            if len(row) < 3:
                continue
            a, b, raw_count = row[0], row[1], row[2]
            if a not in targets and b not in targets:
                continue
            try:
                count = float(raw_count)
            except ValueError:
                continue
            if a in targets:
                partners[a][b] += count
            if b in targets:
                partners[b][a] += count
    return partners


def split_color(tag: str, suffix: str) -> Optional[str]:
    """从 'blue_hair' 这类标签里取颜色部分，不是颜色词则返回 None。"""
    if not tag.endswith(suffix):
        return None
    prefix = tag[: -len(suffix)]
    return prefix if prefix in COLORS else None


def infer_features(
    character: str,
    partners: Dict[str, float],
    tag_category: Dict[str, str],
    tag_post_count: Dict[str, int],
) -> Dict[str, object]:
    """根据共现伙伴推断一个角色的特征。"""
    ranked = sorted(partners.items(), key=lambda x: x[1], reverse=True)

    hair_color_tag = None
    hair_color = None
    eye_color_tag = None
    eye_color = None
    hair_styles: List[str] = []
    eyes: List[str] = []
    clothing_scored: List[Tuple[str, float]] = []

    for tag, count in ranked:
        category = tag_category.get(tag)
        if category not in ("hair", "eyes", "clothing"):
            continue

        hc = split_color(tag, "_hair")
        ec = split_color(tag, "_eyes")

        if category == "hair":
            if hc is not None:
                # 发色：只取共现最高的第一个。
                if hair_color is None:
                    hair_color = hc
                    hair_color_tag = tag
            elif tag not in HAIR_LENGTH_WORDS:
                # 发型：排除发色词和发长通用词后的 hair 标签。
                if len(hair_styles) < MAX_HAIR_STYLE:
                    hair_styles.append(tag)
        elif category == "eyes":
            if tag in EYE_STATE_WORDS:
                continue
            if ec is not None:
                if eye_color is None:
                    eye_color = ec
                    eye_color_tag = tag
            else:
                if len(eyes) < MAX_EYES:
                    eyes.append(tag)
        elif category == "clothing":
            # 相对显著度：共现次数 / 该服装全局热度。
            global_count = tag_post_count.get(tag, 0)
            if global_count <= 0:
                continue
            salience = count / global_count
            clothing_scored.append((tag, salience))

    clothing_scored.sort(key=lambda x: x[1], reverse=True)
    clothing = [tag for tag, _ in clothing_scored[:MAX_CLOTHING]]

    return {
        "hair_color": hair_color,
        "hair_color_tag": hair_color_tag,
        "eye_color": eye_color,
        "eye_color_tag": eye_color_tag,
        "hair_styles": hair_styles,
        "eyes": eyes,
        "clothing": clothing,
    }


def safe_id(character_tag: str) -> str:
    """把角色标签转成安全的 id / 文件名：去掉括号后缀里的特殊字符。"""
    # 例如 artoria_pendragon_(fate) -> artoria_pendragon_fate
    cleaned = re.sub(r"[()]", "", character_tag)
    cleaned = re.sub(r"[^a-z0-9_]", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned


def build_identity(
    character_tag: str,
    features: Dict[str, object],
    zh_names: Dict[str, str],
) -> Dict[str, object]:
    """把推断出的特征组装成 identity 字典。"""
    identity_id = safe_id(character_tag)

    #中文名：先查完整标签，再查去括号后缀的标签。
    base_tag = character_tag.split("(")[0].strip("_")
    name = zh_names.get(character_tag.lower(), "") or zh_names.get(base_tag.lower(), "")

    locked_features: Dict[str, str] = {}
    if features["hair_color"]:
        locked_features["hair_color"] = features["hair_color"]
    if features["eye_color"]:
        locked_features["eye_color"] = features["eye_color"]

    default_tags: Dict[str, List[str]] = {}
    hair_list: List[str] = []
    if features["hair_color_tag"]:
        hair_list.append(features["hair_color_tag"])
    hair_list.extend(features["hair_styles"])
    if hair_list:
        default_tags["hair"] = hair_list
    eyes_list: List[str] = []
    if features["eye_color_tag"]:
        eyes_list.append(features["eye_color_tag"])
    eyes_list.extend(features["eyes"])
    if eyes_list:
        default_tags["eyes"] = eyes_list

    return {
        "id": identity_id,
        "name": name,
        "identity_tags": [character_tag],
        "locked_features": locked_features,
        "default_tags": default_tags,
        "default_clothing": features["clothing"],
        "optional_clothing": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="批量生成二创角色 identity 模板。")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP, help="生成热度前多少个角色。")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的 identity 文件。")
    args = parser.parse_args()

    print("读取角色列表 ...")
    characters = load_characters(args.top)
    print(f"  取热度前 {len(characters)} 个角色")

    print("加载语义库 ...")
    tag_category, tag_post_count = load_semantic_index()
    print(f"  语义库标签 {len(tag_category)}")

    print("加载中文名 ...")
    zh_names = load_zh_names()
    print(f"  中文名条目 {len(zh_names)}")

    occupied = load_existing_identity_tags()
    print(f"  已存在模板占用标签 {len(occupied)}")

    target_tags = {tag for tag, _ in characters}
    print("扫描共现数据（文件较大，请稍候）...")
    partners = scan_cooccurrence(target_tags)
    print("  共现扫描完成")

    IDENTITIES_DIR.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped: List[str] = []
    report_rows: List[Tuple[str, Dict[str, object], str, bool]] = []

    for character_tag, _count in characters:
        features = infer_features(
            character_tag, partners.get(character_tag, {}), tag_category, tag_post_count
        )
        identity = build_identity(character_tag, features, zh_names)
        out_path = IDENTITIES_DIR / f"{identity['id']}.json"

        # 手写模板永远保护：命中保护 id，或角色标签被保护模板占用，不受 --force 影响。
        occupied_file = occupied.get(character_tag.strip().lower(), "")
        protected = identity["id"] in PROTECTED_IDS or occupied_file[:-5] in PROTECTED_IDS
        # 普通已存在：非 force 时跳过，force 时覆盖。
        already = out_path.exists() or character_tag.strip().lower() in occupied
        if protected or (already and not args.force):
            skipped.append(identity["id"])
            report_rows.append((character_tag, features, identity["name"], True))
            continue

        out_path.write_text(
            json.dumps(identity, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written += 1
        report_rows.append((character_tag, features, identity["name"], False))

    # ---- 报告 ----
    print("\n==================== 生成报告 ====================")
    for character_tag, features, name, was_skipped in report_rows:
        flag = "  [跳过,已存在]" if was_skipped else ""
        name_show = name if name else "(无中文名)"
        print(f"\n{character_tag}  {name_show}{flag}")
        print(f"  发色: {features['hair_color_tag']}  眼色: {features['eye_color_tag']}")
        print(f"  发型: {features['hair_styles']}")
        print(f"  服装: {features['clothing']}")

    print("\n==================== 汇总 ====================")
    print(f"  写出 {written} 个，跳过 {len(skipped)} 个")
    no_name = sum(1 for _, _,name, _ in report_rows if not name)
    print(f"  无中文名 {no_name} 个")
    if skipped:
        print(f"  跳过的角色: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
