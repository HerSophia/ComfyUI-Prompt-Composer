"""从原始数据离线算出标签关联，产出 related 关联文件与三类候选清单。

这个脚本读取三份数据：

    data/raw/danbooru_tags_cooccurrence.csv   成对共现次数（tag_a,tag_b,count）
    data/raw/tags.json                        单标签频次 n 与 wiki 关联链接
    data/semantic/*.json                      我们分类过的候选标签

只在出现于语义层的标签之间计算关联，语义层没有的标签不进结果，
避免关联到不在候选里的标签。

产出两类结果：

    data/associations.json            每个标签一份关联列表，每项含关联标签与权重，
                                      按权重排序、设数量上限，供 core 按标签查询。
    data/association_candidates.json  requires、conflicts、implies 三类候选清单，
                                      单独输出供人工审核，本轮不写入 overlay。

这个脚本由人工离线运行、产物随仓库提交，不在 ComfyUI 启动时执行，
保持插件启动零开销。原始数据只读，不复制、不进插件目录同步。

关联强度：
    默认用 cosine 共现指标 cooc(a,b) / sqrt(n(a) * n(b))，对称、落在 [0,1]，
    对热门标签有归一效果。也支持条件概率与点互信息，便于各算一版抽查后选定。

wiki 关联互斥过滤：
    tags.json 的 is_linking_to / is_linked_by 把语义相关但画面互斥的标签也列了进去
    （例如 1girl 链接到 2girls、long_hair 链接到 short_hair）。用共现强度反过来筛：
    一对标签共现强度低于阈值就不进 related，即使被 wiki 互相链接；如果同时属于同一
    分类，归入 conflicts 候选。只有共现强度也高的 wiki 链接才提权为高置信 related。

用法：
    python prompt_composer/tools/build_associations.py
    python prompt_composer/tools/build_associations.py --dry-run   # 只统计不写入
    python prompt_composer/tools/build_associations.py --metric condprob
    python prompt_composer/tools/build_associations.py --max-cooc-rows 100000
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# csv 单字段可能很长，放开默认字段大小限制。
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

# ---- 路径 ----
TOOLS_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = TOOLS_DIR.parent
RAW_DIR = PACKAGE_DIR / "data" / "raw"
SEMANTIC_DIR = PACKAGE_DIR / "data" / "semantic"
COOC_CSV = RAW_DIR / "danbooru_tags_cooccurrence.csv"
TAGS_JSON = RAW_DIR / "tags.json"
ASSOCIATIONS_PATH = PACKAGE_DIR / "data" / "associations.json"
CANDIDATES_PATH = PACKAGE_DIR / "data" / "association_candidates.json"

# ---- 默认参数 ----
# related 关联强度下限。低于这个值的关联不进关联文件。
DEFAULT_MIN_STRENGTH = 0.05
# 每个标签最多保留多少个关联，按权重从高到低截断，避免文件过大。
DEFAULT_MAX_RELATED = 30
# wiki 链接且共现强度达标时的提权系数。
DEFAULT_WIKI_BOOST = 1.3
# 条件概率 P(b|a) 达到此值，把 a->b 记为 implies 候选（a 出现强烈暗示 b）。
DEFAULT_IMPLIES_COND = 0.60
# 条件概率 P(b|a) 达到此值，且 b明显更普遍时，把 a->b 记为 requires 候选。
DEFAULT_REQUIRES_COND = 0.85
# requires 候选要求 b 的频次至少是 a 的这个倍数（b 更基础、更像父级）。
DEFAULT_REQUIRES_RATIO = 3.0
# 各类候选清单的输出上限，避免文件过大。
DEFAULT_CANDIDATE_LIMIT = 2000


def normalize(value: str) -> str:
    """标签归一：去空白、转小写。与 core 的归一保持一致。"""
    return value.strip().lower()


def load_semantic_tags(semantic_dir: Path) -> Dict[str, Dict[str, object]]:
    """扫描 data/semantic/ 直属分类 JSON，返回 tag -> {category, post_count}。

    identities 与 rules 是子目录，glob 只取一层，不会被扫到。
    """
    result: Dict[str, Dict[str, object]] = {}
    if not semantic_dir.exists():
        return result
    for file_path in sorted(semantic_dir.glob("*.json")):
        with file_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            tag = normalize(str(item.get("tag", "") or ""))
            if not tag:
                continue
            category = str(item.get("category", "") or "").strip()
            try:
                post_count = int(item.get("post_count", 0) or 0)
            except (TypeError, ValueError):
                post_count = 0
            # 同名标签只保留第一次出现的。
            if tag not in result:
                result[tag] = {"category": category, "post_count": post_count}

    return result


def load_tag_stats(
    tags_json: Path,
    keep: Set[str],
) -> Dict[str, Dict[str, object]]:
    """从 tags.json 读单标签频次 n 与 wiki 链接，只保留 keep 集合内的标签。

    返回 tag -> {"n": int, "linking_to": set, "linked_by": set}。
    tags.json 很大，整体加载后立即抽取需要字段再释放。
    """
    result: Dict[str, Dict[str, object]] = {}
    if not tags_json.exists():
        return result
    with tags_json.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        return result
    for raw_tag, info in data.items():
        tag = normalize(str(raw_tag))
        if tag not in keep or not isinstance(info, dict):
            continue
        try:
            n = int(info.get("n", 0) or 0)
        except (TypeError, ValueError):
            n = 0
        linking_to = {
            normalize(str(t))
            for t in (info.get("is_linking_to") or [])
            if str(t).strip()
        }
        linked_by = {
            normalize(str(t))
            for t in (info.get("is_linked_by") or [])
            if str(t).strip()
        }
        # 只保留 wiki 链接里同样落在候选集合内的目标。
        linking_to &= keep
        linked_by &= keep
        result[tag] = {"n": n, "linking_to": linking_to, "linked_by": linked_by}
    del data
    return result


def load_cooccurrence(
    cooc_csv: Path,
    keep: Set[str],
    max_rows: int = 0,
) -> Dict[str, Dict[str, int]]:
    """流式读取共现 csv，只保留双方都在 keep 集合内的行。

    返回对称的嵌套字典 cooc[a][b] = count。
    max_rows > 0 时只读取前若干行，用于小样本抽查。
    """
    cooc: Dict[str, Dict[str, int]] = {}
    if not cooc_csv.exists():
        return cooc
    with cooc_csv.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)  # 跳过表头 tag_a,tag_b,count
        read = 0
        for row in reader:
            if max_rows and read >= max_rows:
                break
            read += 1
            if len(row) < 3:
                continue
            a = normalize(row[0])
            b = normalize(row[1])
            if a == b or a not in keep or b not in keep:
                continue
            try:
                count = int(float(row[2]))
            except (TypeError, ValueError):
                continue
            if count <= 0:
                continue
            cooc.setdefault(a, {})[b] = count
            cooc.setdefault(b, {})[a] = count
    return cooc


def compute_strength(
    cooc_ab: int,
    n_a: int,
    n_b: int,
    metric: str = "cosine",
    total: int = 0,
) -> float:
    """由成对共现次数与单标签频次算出关联强度。

    cosine   : cooc / sqrt(n_a * n_b)，对称、落在 [0,1]。
    condprob : min(P(a|b), P(b|a))，取两个方向条件概率的较小值。
    pmi      : 归一化点互信息，落在 [-1, 1]，需要总样本数 total。

    共现 csv 与 tags.json 的频次取自不同数据快照，口径不完全一致，
    偶尔会出现 cooc 略大于单标签频次的情况。cosine 与 condprob 语义上
    应落在 [0, 1]，这里统一截断到 1.0，避免个别取值越界。
    """
    if cooc_ab <= 0 or n_a <= 0 or n_b <= 0:
        return 0.0
    if metric == "condprob":
        return min(1.0, cooc_ab / n_a, cooc_ab / n_b)
    if metric == "pmi":
        if total <= 0:
            return 0.0
        p_ab = cooc_ab / total
        p_a = n_a / total
        p_b = n_b / total
        if p_ab <= 0 or p_a <= 0 or p_b <= 0:
            return 0.0
        pmi = math.log(p_ab / (p_a * p_b))
        denom = -math.log(p_ab)
        if denom <= 0:
            return 0.0
        return pmi / denom
    # 默认 cosine
    return min(1.0, cooc_ab / math.sqrt(n_a * n_b))


def cond_prob(cooc_ab: int, n_a: int) -> float:
    """条件概率 P(b|a) = cooc(a,b) / n(a)。a 出现时 b 也出现的比例。

    频次口径差异可能让比值略微越过 1，这里截断到 1.0。
    """
    if cooc_ab <= 0 or n_a <= 0:
        return 0.0
    return min(1.0, cooc_ab / n_a)


def _resolve_freq(
    tag: str,
    stats: Dict[str, Dict[str, object]],
    semantic_tags: Dict[str, Dict[str, object]],
) -> int:
    """取单标签频次：优先 tags.json 的 n，缺失回退语义层 post_count。"""
    info = stats.get(tag)
    if info is not None:
        n = int(info.get("n", 0) or 0)
        if n > 0:
            return n
    sem = semantic_tags.get(tag)
    if sem is not None:
        return int(sem.get("post_count", 0) or 0)
    return 0


def compute_associations(
    semantic_tags: Dict[str, Dict[str, object]],
    stats: Dict[str, Dict[str, object]],
    cooc: Dict[str, Dict[str, int]],
    metric: str = "cosine",
    min_strength: float = DEFAULT_MIN_STRENGTH,
    max_related: int = DEFAULT_MAX_RELATED,
    wiki_boost: float = DEFAULT_WIKI_BOOST,
    implies_cond: float = DEFAULT_IMPLIES_COND,
    requires_cond: float = DEFAULT_REQUIRES_COND,
    requires_ratio: float = DEFAULT_REQUIRES_RATIO,
) -> Tuple[Dict[str, List[Dict[str, object]]], Dict[str, List[Dict[str, object]]]]:
    """算出 related 关联与三类候选清单。

    返回 (related, candidates)：
        related     : tag -> [ {"tag": b, "weight": w}, ... ]，按权重降序、设上限。
        candidates  : {"requires": [...], "conflicts": [...], "implies": [...]}。
    """
    # 频次表：所有候选标签的频次，缺失回退 post_count。
    freq: Dict[str, int] = {}
    for tag in semantic_tags:
        freq[tag] = _resolve_freq(tag, stats, semantic_tags)

    # pmi 需要总样本数，用候选标签频次的最大值近似总帖子数。
    total = max(freq.values()) if freq else 0

    related: Dict[str, List[Dict[str, object]]] = {}
    requires_cand: List[Dict[str, object]] = []
    conflicts_cand: List[Dict[str, object]] = []
    implies_cand: List[Dict[str, object]] = []
    # conflicts 去重：同一对只记一次。
    seen_conflict: Set[Tuple[str, str]] = set()

    for a in sorted(semantic_tags):
        n_a = freq.get(a, 0)
        cat_a = str(semantic_tags[a].get("category", ""))
        info_a = stats.get(a, {})
        wiki_links: Set[str] = set()
        if info_a:
            wiki_links = set(info_a.get("linking_to", set())) | set(
                info_a.get("linked_by", set())
            )

        # 候选来自共现邻居与 wiki 链接目标，合并后逐个评估。
        neighbors = set(cooc.get(a, {}).keys()) | wiki_links
        scored: List[Dict[str, object]] = []

        for b in neighbors:
            if b == a or b not in semantic_tags:
                continue
            cooc_ab = cooc.get(a, {}).get(b, 0)
            n_b = freq.get(b, 0)
            strength = compute_strength(cooc_ab, n_a, n_b, metric=metric, total=total)
            is_wiki = b in wiki_links

            # wiki 链接但共现强度不达标：画面互斥，不进 related。
            # 若同分类，记为conflicts 候选。
            if is_wiki and strength < min_strength:
                if cat_a and cat_a == str(semantic_tags[b].get("category", "")):
                    key = tuple(sorted((a, b)))
                    if key not in seen_conflict:
                        seen_conflict.add(key)
                        conflicts_cand.append(
                            {
                                "tag": key[0],
                                "other": key[1],
                                "category": cat_a,
                                "strength": round(strength, 4),
                            }
                        )
                continue

            if strength < min_strength:
                continue

            # 共现强度达标的 wiki 链接提权为高置信关联。
            weight = strength * wiki_boost if is_wiki else strength
            scored.append(
                {
                    "tag": b,
                    "weight": round(weight, 4),
                    "wiki": is_wiki,
                }
            )

            # 条件概率方向性判断，产出 requires / implies 候选。
            p_b_given_a = cond_prob(cooc_ab, n_a)
            if p_b_given_a >= requires_cond and n_b >= n_a * requires_ratio:
                requires_cand.append(
                    {
                        "tag": a,
                        "target": b,
                        "cond": round(p_b_given_a, 4),
                        "n_a": n_a,
                        "n_b": n_b,
                    }
                )
            elif p_b_given_a >= implies_cond:
                implies_cand.append(
                    {
                        "tag": a,
                        "target": b,
                        "cond": round(p_b_given_a, 4),
                    }
                )

        if not scored:
            continue
        scored.sort(key=lambda item: item["weight"], reverse=True)
        if max_related > 0:
            scored = scored[:max_related]
        related[a] = [
            {"tag": item["tag"], "weight": item["weight"]} for item in scored
        ]

    requires_cand.sort(key=lambda item: item["cond"], reverse=True)
    implies_cand.sort(key=lambda item: item["cond"], reverse=True)
    conflicts_cand.sort(key=lambda item: item["tag"])

    candidates = {
        "requires": requires_cand[:DEFAULT_CANDIDATE_LIMIT],
        "conflicts": conflicts_cand[:DEFAULT_CANDIDATE_LIMIT],
        "implies": implies_cand[:DEFAULT_CANDIDATE_LIMIT],
    }
    return related, candidates


def _print_samples(related: Dict[str, List[Dict[str, object]]]) -> None:
    """抽查几个热门标签的关联结果，便于人工判断质量。"""
    samples = ["1girl", "long_hair", "blue_eyes", "school_uniform", "cat_ears"]
    print("抽查样例：")
    for tag in samples:
        items = related.get(tag)
        if not items:
            continue
        preview = ", ".join(f"{it['tag']}({it['weight']})" for it in items[:8])
        print(f"  {tag} -> {preview}")


def main() -> None:
    parser = argparse.ArgumentParser(description="从原始数据挖掘标签关联。")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印统计信息，不写入文件。",
    )
    parser.add_argument(
        "--metric",
        choices=["cosine", "condprob", "pmi"],
        default="cosine",
        help="关联强度指标，默认 cosine。",
    )
    parser.add_argument(
        "--min-strength",
        type=float,
        default=DEFAULT_MIN_STRENGTH,
        help="related 关联强度下限。",
    )
    parser.add_argument(
        "--max-related",
        type=int,
        default=DEFAULT_MAX_RELATED,
        help="每个标签保留的关联数量上限。",
    )
    parser.add_argument(
        "--max-cooc-rows",
        type=int,
        default=0,
        help="只读取共现 csv 的前若干行，用于小样本抽查。0 表示不限。",
    )
    parser.add_argument(
        "--tags-json",
        type=Path,
        default=TAGS_JSON,
        help="tags.json 路径，便于用小样本替换。",
    )
    parser.add_argument(
        "--cooc-csv",
        type=Path,
        default=COOC_CSV,
        help="共现 csv 路径，便于用小样本替换。",
    )
    args = parser.parse_args()

    print("读取语义层候选标签 ...")
    semantic_tags = load_semantic_tags(SEMANTIC_DIR)
    keep =set(semantic_tags.keys())
    print(f"  语义层标签 {len(keep)} 个")

    print("读取 tags.json 单标签频次与 wiki 链接 ...")
    stats = load_tag_stats(args.tags_json, keep)
    print(f"  命中频次数据 {len(stats)} 个")

    print("读取共现 csv ...")
    cooc = load_cooccurrence(args.cooc_csv, keep, max_rows=args.max_cooc_rows)
    total_pairs = sum(len(v) for v in cooc.values()) // 2
    print(f"  语义层内共现对 {total_pairs} 对，涉及标签 {len(cooc)} 个")

    print(f"计算关联（metric={args.metric}）...")
    related, candidates = compute_associations(
        semantic_tags,
        stats,
        cooc,
        metric=args.metric,
        min_strength=args.min_strength,
        max_related=args.max_related,
    )
    related_pairs = sum(len(v) for v in related.values())
    print(
        f"  产出关联标签 {len(related)} 个，关联项 {related_pairs} 条；"
        f"候选 requires {len(candidates['requires'])}、"
        f"conflicts {len(candidates['conflicts'])}、"
        f"implies {len(candidates['implies'])}"
    )

    if args.dry_run:
        print("  --dry-run：不写入文件。")
        _print_samples(related)
        return

    with ASSOCIATIONS_PATH.open("w", encoding="utf-8") as file:
        json.dump(related, file, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"  已写入关联文件：{ASSOCIATIONS_PATH}")

    with CANDIDATES_PATH.open("w", encoding="utf-8") as file:
        json.dump(candidates, file, ensure_ascii=False, indent=2)
    print(f"  已写入候选清单：{CANDIDATES_PATH}")

    _print_samples(related)


if __name__ == "__main__":
    main()
