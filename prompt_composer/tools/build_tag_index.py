"""把各分类标签合并成一个精简索引，供前端标签检索面板使用。

扫描 data/semantic/ 直属的各分类 JSON 文件（identities 与 rules 是子目录，
glob 只取一层，不会被扫到），每个标签只保留检索需要的三个字段：

    tag       danbooru 标签
    category  所属分类
    label_zh  中文名

输出到 data/tags_index.json，按 category 与 tag 排序，UTF-8 编码。
索引文件不放在 semantic/ 目录内，避免被 TagStore 当成标签数据加载。
这个索引由本脚本离线生成、随仓库提交，不在 ComfyUI 启动时自动生成。

用法：
    python prompt_composer/tools/build_tag_index.py
    python prompt_composer/tools/build_tag_index.py --dry-run   # 只统计不写入
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

TOOLS_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = TOOLS_DIR.parent
SEMANTIC_DIR = PACKAGE_DIR / "data" / "semantic"
INDEX_PATH = PACKAGE_DIR / "data" / "tags_index.json"


def build_index() -> List[Dict[str, str]]:
    """扫描各分类 JSON，返回精简后的索引条目列表，按 category 与 tag 排序。"""
    entries: List[Dict[str, str]] = []
    if not SEMANTIC_DIR.exists():
        return entries
    for file_path in sorted(SEMANTIC_DIR.glob("*.json")):
        with file_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        # 分类文件应是标签数组，非数组的直接跳过。
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            tag = str(item.get("tag", "") or "").strip()
            if not tag:
                continue
            category = str(item.get("category", "") or "").strip()
            label_zh = str(item.get("label_zh", "") or "").strip()
            entries.append(
                {
                    "tag": tag,
                    "category": category,
                    "label_zh": label_zh,
                }
            )
    entries.sort(key=lambda entry: (entry["category"], entry["tag"]))
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="生成标签检索索引。")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印统计信息，不写入索引文件。",
    )
    args = parser.parse_args()

    entries = build_index()
    labeled = sum(1 for entry in entries if entry["label_zh"])
    print(f"  扫描到标签 {len(entries)} 个，其中有中文名 {labeled} 个。")

    if args.dry_run:
        print("  --dry-run：不写入文件。")
        return

    with INDEX_PATH.open("w", encoding="utf-8") as file:
        json.dump(entries, file, ensure_ascii=False, indent=2)
    print(f"  已写入索引：{INDEX_PATH}")


if __name__ == "__main__":
    main()
