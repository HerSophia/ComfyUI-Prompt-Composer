"""把所有 identity 文件合并成一个精简索引，供前端角色检索面板使用。

扫描data/semantic/identities/ 下全部 identity 文件，每个角色只保留检索
和回填需要的三个字段：

    id          角色 id
    name        中文名
    display_tag identity_tags 的第一个原始 danbooru 标签，用于展示出处

输出到 data/identities_index.json，按 id 排序，UTF-8 编码。
注意索引文件不放在 semantic/ 目录内，避免被 TagStore 当成标签数据加载。
这个索引由本脚本离线生成、随仓库提交，不在 ComfyUI 启动时自动生成，
以避免启动时逐个读取上千个小文件带来的开销。

用法：
    python prompt_composer/tools/build_identity_index.py
    python prompt_composer/tools/build_identity_index.py --dry-run   # 只统计不写入
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

TOOLS_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = TOOLS_DIR.parent
IDENTITIES_DIR =PACKAGE_DIR / "data" / "semantic" / "identities"
INDEX_PATH = PACKAGE_DIR / "data" / "identities_index.json"


def build_index() -> List[Dict[str, str]]:
    """扫描 identity 目录，返回精简后的索引条目列表，按 id 排序。"""
    entries: List[Dict[str, str]] = []
    if not IDENTITIES_DIR.exists():
        return entries
    for file_path in sorted(IDENTITIES_DIR.glob("*.json")):
        with file_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        # 一个文件可以是单个 identity，也可以是 identity 列表。
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            identity_id = str(item.get("id", "")).strip()
            if not identity_id:
                continue
            name = str(item.get("name", "") or "").strip()
            identity_tags = item.get("identity_tags") or []
            display_tag = ""
            if isinstance(identity_tags, list) and identity_tags:
                display_tag = str(identity_tags[0]).strip()
            entries.append(
                {
                    "id": identity_id,
                    "name": name,
                    "display_tag": display_tag,
                }
            )
    entries.sort(key=lambda entry: entry["id"])
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 identity 检索索引。")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印统计信息，不写入索引文件。",
    )
    args = parser.parse_args()

    entries = build_index()
    named = sum(1 for entry in entries if entry["name"])
    print(f"  扫描到 identity {len(entries)} 个，其中有中文名 {named} 个。")

    if args.dry_run:
        print("  --dry-run：不写入文件。")
        return

    with INDEX_PATH.open("w", encoding="utf-8") as file:
        json.dump(entries, file, ensure_ascii=False, indent=2)
    print(f"  已写入索引：{INDEX_PATH}")


if __name__ == "__main__":
    main()
