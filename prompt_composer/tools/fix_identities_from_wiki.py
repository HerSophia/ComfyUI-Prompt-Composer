"""用 Danbooru wiki 修正已有角色identity 的发色、主发型、眼色。

背景：
    早期 identity 由共现挖掘生成，会把多个互斥发型都塞进一个角色，
    甚至连主发型、发色都可能挖错。Danbooru wiki 里有人工维护的外观
    描述句（"She has [[...]] hair, [[...]] eyes"），比共现统计准确。
    这个工具离线读取 wiki，解析出发色、一个主发型、眼色，写回 identity。

原则：
    1. 只离线运行，产出数据后进仓库。运行时不碰网络。
    2. 发型只取一个主发型。wiki 没提扎发的角色判为披发（不加扎发标签）。
    3. wiki 没提到的附属特征（刘海、呆毛等）保留现有值，不丢信息。
4. wiki 缺失或解析不出的角色，保持原样跳过。
    5. 分阶段：先 fetch 缓存 wiki，再 apply 写回。缓存在 raw 目录，不进仓库。

用法：
    先设置代理（如需）：
        set HTTP_PROXY=http://127.0.0.1:7890
      set HTTPS_PROXY=http://127.0.0.1:7890
    抓取 wiki 到缓存（分批，可重复运行，已缓存的跳过）：
        python prompt_composer/tools/fix_identities_from_wiki.py fetch
        python prompt_composer/tools/fix_identities_from_wiki.py fetch --limit 100
    预览修正（不写文件）：
        python prompt_composer/tools/fix_identities_from_wiki.py preview
  应用修正（写回 identity 文件）：
        python prompt_composer/tools/fix_identities_from_wiki.py apply
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---- 路径 ----
TOOLS_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = TOOLS_DIR.parent
SEMANTIC_DIR = PACKAGE_DIR / "data" / "semantic"
IDENTITIES_DIR = SEMANTIC_DIR / "identities"
WIKI_CACHE_DIR = PACKAGE_DIR / "data" / "raw" / "wiki_cache"

# ---- API ----
WIKI_API = "https://danbooru.donmai.us/wiki_pages.json"
USER_AGENT = "prompt-composer-fix/1.0"
REQUEST_INTERVAL = 0.5
BATCH_SLEEP = 2.0
BATCH_SIZE = 50
MAX_RETRY = 3

# ---- 颜色词表（与 build_identities 保持一致）----
COLORS = {
    "blue", "red", "green", "black", "brown", "blonde", "pink", "purple",
    "white", "grey", "gray", "silver", "aqua", "orange", "yellow",
    "light_brown", "light_blue", "dark_blue", "dark_green",
    "multicolored", "two-tone", "gradient", "platinum_blonde", "streaked",
    "colored_inner",
}

# 发长词，不算发色也不算主发型样式。
HAIR_LENGTH = {
    "long_hair", "short_hair", "medium_hair", "very_long_hair",
    "absurdly_long_hair",
}

# 眼睛状态词，不是眼色。
EYE_STATE = {"closed_eyes", "empty_eyes", "one_eye_closed", "half-closed_eyes"}

# wiki里可能出现的发型标签 -> 语义库标准标签。
STYLE_ALIAS = {
    "twin_drills": "drill_hair",
    "drill_hair": "drill_hair",
    "low_twintails": "twintails",
    "twintails": "twintails",
    "double_bun": "double_bun",
    "hair_bun": "hair_bun",
    "twin_braids": "twin_braids",
    "single_braid": "twin_braids",
    "braided_ponytail": "braided_ponytail",
    "high_ponytail": "high_ponytail",
 "side_ponytail": "side_ponytail",
    "low_ponytail": "low_ponytail",
    "short_ponytail": "short_ponytail",
    "ponytail": "ponytail",
    "hime_cut": "hime_cut",
    "bob_cut": "bob_cut",
}

# 主发型优先级：越靠前越优先保留。
STYLE_ORDER = [
    "twin_drills", "drill_hair",
    "double_bun", "hair_bun", "twin_braids", "single_braid",
    "braided_ponytail",
    "high_ponytail", "side_ponytail", "low_ponytail", "short_ponytail",
    "low_twintails", "twintails", "ponytail",
    "hime_cut", "bob_cut",
]

# 所有发型样式标准标签（用于从现有 hair 列表里剔除旧发型）。
ALL_STYLE_TAGS = set(STYLE_ALIAS.values())


def load_semantic_tags() -> Dict[str, set]:
    """返回 分类 -> 该分类下所有标签集合。"""
    result: Dict[str, set] = {}
    for json_file in SEMANTIC_DIR.glob("*.json"):
        entries = json.loads(json_file.read_text(encoding="utf-8"))
        for entry in entries:
            tag = str(entry.get("tag", "")).strip()
            cat = str(entry.get("category", "")).strip()
            if not tag or not cat:
                continue
            result.setdefault(cat, set()).add(tag)
    return result


def safe_name(char_tag: str) -> str:
    """把角色标签转成安全的缓存文件名。"""
    return urllib.parse.quote(char_tag, safe="")


def fetch_wiki_body(char_tag: str) -> Optional[str]:
    """请求 wiki，返回 body 文本。失败返回 None，无 wiki 返回空串。"""
    q = urllib.parse.quote(char_tag)
    url = f"{WIKI_API}?search[title]={q}"
    for attempt in range(MAX_RETRY):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            if data:
                return data[0].get("body", "")
            return ""
        except Exception as exc:
            if attempt == MAX_RETRY - 1:
                print(f"[失败] {char_tag}: {exc}")
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def iter_identity_files() -> List[Tuple[Path, dict]]:
    """遍历所有 identity 文件，返回 [(路径, 数据)]。"""
    result = []
    for f in sorted(IDENTITIES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        result.append((f, data))
    return result


def primary_char_tag(data: dict) -> Optional[str]:
    """取角色主标签（identity_tags 第一个）。"""
    tags = data.get("identity_tags", []) or []
    return str(tags[0]).strip() if tags else None


def appearance_segment(body: str) -> str:
    """从 wiki body 里取外观描述段：含 hair 且含 eyes 的那一行。"""
    for chunk in re.split(r"[\r\n]+", body):
        low = chunk.lower()
        if "hair" in low and "eyes" in low:
            return chunk
    return ""


def extract_tags(text: str) -> List[str]:
    """提取 [[tag]] 或 [[tag|alias]] 里的标准标签。"""
    raw = re.findall(r"\[\[([^\]]+)\]\]", text)
    out = []
    for item in raw:
        name = item.split("|")[0].strip().lower().replace(" ", "_")
        out.append(name)
    return out


def parse_features(body: str) -> Dict[str, Optional[str]]:
    """从 wiki body解析发色、主发型、眼色。解析不出的字段为 None。"""
    seg = appearance_segment(body)
    tags = extract_tags(seg)
    hair_color_tag = None
    hair_color = None
    eye_color_tag = None
    eye_color = None
    for tag in tags:
        if tag.endswith("_hair") and tag not in HAIR_LENGTH and hair_color_tag is None:
            prefix = tag[: -len("_hair")]
            if prefix in COLORS:
                hair_color_tag = tag
                hair_color = prefix
        if tag.endswith("_eyes") and tag not in EYE_STATE and eye_color_tag is None:
            prefix = tag[: -len("_eyes")]
            if prefix in COLORS:
                eye_color_tag = tag
                eye_color = prefix
    hair_style = None
    tag_set = set(tags)
    for style in STYLE_ORDER:
        if style in tag_set:
            hair_style = STYLE_ALIAS[style]
            break
    return {
        "hair_color": hair_color,
        "hair_color_tag": hair_color_tag,
        "hair_style": hair_style,
        "eye_color": eye_color,
        "eye_color_tag": eye_color_tag,
    }


def cmd_fetch(limit: int) -> None:
    """抓取 wiki 到缓存。已缓存的跳过。"""
    WIKI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    files = iter_identity_files()
    todo = []
    for path, data in files:
        char = primary_char_tag(data)
        if not char:
            continue
        cache_file = WIKI_CACHE_DIR / (safe_name(char) + ".json")
        if cache_file.exists():
            continue
        todo.append(char)
    if limit > 0:
        todo = todo[:limit]
    print(f"待抓取 {len(todo)} 个角色（已缓存的跳过）")
    for i, char in enumerate(todo, 1):
        body = fetch_wiki_body(char)
        cache_file = WIKI_CACHE_DIR / (safe_name(char) + ".json")
        if body is not None:
            cache_file.write_text(
                json.dumps({"body": body}, ensure_ascii=False), encoding="utf-8"
            )
        print(f"  [{i}/{len(todo)}] {char}  ({'ok' if body else 'empty/fail'})")
        time.sleep(REQUEST_INTERVAL)
        if i % BATCH_SIZE == 0:
            print(f"  --- 已处理 {i} 个，休息 {BATCH_SLEEP}s ---")
            time.sleep(BATCH_SLEEP)
    print("抓取完成。")


def load_cached_body(char: str) -> Optional[str]:
    """从缓存读 wiki body。无缓存返回 None。"""
    cache_file = WIKI_CACHE_DIR / (safe_name(char) + ".json")
    if not cache_file.exists():
        return None
    try:
        return json.loads(cache_file.read_text(encoding="utf-8")).get("body", "")
    except (ValueError, OSError):
        return None


def is_color_hair(tag: str) -> bool:
    return tag.endswith("_hair") and tag[:-5] in COLORS


def compute_fix(
    data: dict, feats: Dict[str, Optional[str]], sem_tags: Dict[str, set]
) -> dict:
    """根据 wiki 特征算出修正后的 identity（返回新对象，不改原对象）。"""
    new = json.loads(json.dumps(data, ensure_ascii=False))
    hair_tags_lib = sem_tags.get("hair", set())
    eyes_tags_lib = sem_tags.get("eyes", set())

    locked = new.setdefault("locked_features", {})
    default_tags = new.setdefault("default_tags", {})
    hair_list = list(default_tags.get("hair", []))
    eyes_list = list(default_tags.get("eyes", []))

    # 附属特征：非发色、非发型样式的 hair 标签（刘海、呆毛、发长等）。
    extra = [t for t in hair_list if not is_color_hair(t) and t not in ALL_STYLE_TAGS]

    new_hair: List[str] = []
    # 1. 发色
    hc_tag = feats.get("hair_color_tag")
    if hc_tag and hc_tag in hair_tags_lib:
        new_hair.append(hc_tag)
        locked["hair_color"] = feats["hair_color"]
    else:
        for t in hair_list:
            if is_color_hair(t):
                new_hair.append(t)
                break
    # 2. 主发型：wiki 有才加，且必须在库里。
    hs = feats.get("hair_style")
    if hs and hs in hair_tags_lib:
        new_hair.append(hs)
    # 3. 附属特征保留
    for t in extra:
        if t not in new_hair:
            new_hair.append(t)
    if new_hair:
        default_tags["hair"] = new_hair

    # 4. 眼色
    ec_tag = feats.get("eye_color_tag")
    if ec_tag and ec_tag in eyes_tags_lib:
        non_color_eyes = [
            t for t in eyes_list if not (t.endswith("_eyes") and t[:-5] in COLORS)
        ]
        default_tags["eyes"] = [ec_tag] + non_color_eyes
        locked["eye_color"] = feats["eye_color"]

    return new


def summarize(char: str, old: dict, new: dict) -> Optional[str]:
    """生成一行变更摘要。无变化返回 None。"""
    o_hair = old.get("default_tags", {}).get("hair", [])
    n_hair = new.get("default_tags", {}).get("hair", [])
    o_eyes = old.get("default_tags", {}).get("eyes", [])
    n_eyes = new.get("default_tags", {}).get("eyes", [])
    if o_hair == n_hair and o_eyes == n_eyes:
        return None
    return (
        f"{char}\n"
        f"    hair: {o_hair}\n"
        f"       -> {n_hair}\n"
        f"    eyes: {o_eyes} -> {n_eyes}"
    )


def cmd_preview(apply: bool) -> None:
    """预览或应用修正。apply=True 时写回文件。"""
    sem_tags = load_semantic_tags()
    files = iter_identity_files()
    changed = 0
    skipped_no_wiki = 0
    written = 0
    for path, data in files:
        char = primary_char_tag(data)
        if not char:
            continue
        body = load_cached_body(char)
        if body is None or not body.strip():
            skipped_no_wiki += 1
            continue
        feats = parse_features(body)
        if not any(
            [feats["hair_color_tag"], feats["hair_style"], feats["eye_color_tag"]]
        ):
            continue
        new = compute_fix(data, feats, sem_tags)
        diff = summarize(char, data, new)
        if diff is None:
            continue
        changed += 1
        print(diff)
        if apply:
            path.write_text(
                json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            written += 1
    print("-" * 60)
    print(f"有变更的角色: {changed}")
    print(f"无 wiki 缓存/空 wiki 跳过: {skipped_no_wiki}")
    if apply:
        print(f"已写回文件: {written}")
    else:
        print("（预览模式，未写文件。确认后用 apply 应用。）")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="用 Danbooru wiki修正角色发型/发色/眼色。"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_fetch = sub.add_parser("fetch", help="抓取 wiki 到缓存")
    p_fetch.add_argument(
        "--limit", type=int, default=0, help="本次最多抓取多少个（0 表示全部）"
    )
    sub.add_parser("preview", help="预览修正，不写文件")
    sub.add_parser("apply", help="应用修正，写回 identity 文件")

    args = parser.parse_args()
    if args.cmd == "fetch":
        cmd_fetch(args.limit)
    elif args.cmd == "preview":
        cmd_preview(apply=False)
    elif args.cmd == "apply":
        cmd_preview(apply=True)


if __name__ == "__main__":
    main()
