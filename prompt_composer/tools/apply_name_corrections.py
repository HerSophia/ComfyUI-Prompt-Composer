"""把人工校对的中文名应用到 identity 文件。

读取 name_corrections/ 目录下所有 JSON，合并成一张 id -> 中文名 的表，
然后逐个更新 data/semantic/identities/ 下对应文件的 name 字段。

只改 name 字段，其余内容不动。跳过空值和以下划线开头的注释键。

用法：
    python prompt_composer/tools/apply_name_corrections.py
    python prompt_composer/tools/apply_name_corrections.py --dry-run   #只预览不写入
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict

TOOLS_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = TOOLS_DIR.parent
CORRECTIONS_DIR = TOOLS_DIR / "name_corrections"
IDENTITIES_DIR = PACKAGE_DIR / "data" / "semantic" / "identities"


def load_corrections() -> Dict[str, str]:
    """合并 name_corrections 目录下所有 JSON，返回 id -> 中文名。"""
    merged: Dict[str, str] = {}
    if not CORRECTIONS_DIR.exists():
        return merged
    for json_file in sorted(CORRECTIONS_DIR.glob("*.json")):
        data = json.loads(json_file.read_text(encoding="utf-8"))
        for key, value in data.items():
            key = str(key).strip()
            value = str(value).strip()
            # 跳过注释键和空值。
            if not key or key.startswith("_") or not value:
                continue
            merged[key] = value
    return merged


def main() ->None:
    parser = argparse.ArgumentParser(description="把人工校对的中文名应用到 identity 文件。")
    parser.add_argument("--dry-run", action="store_true", help="只预览要改动的项，不写入。")
    args = parser.parse_args()

    corrections = load_corrections()
    print(f"合并后校对条目 {len(corrections)}")

    changed = 0
    unchanged = 0
    missing = []

    for cid, new_name in sorted(corrections.items()):
        path = IDENTITIES_DIR / f"{cid}.json"
        if not path.exists():
            missing.append(cid)
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        old_name = data.get("name", "")
        if old_name == new_name:
            unchanged += 1
            continue
        if args.dry_run:
            print(f"  [预览] {cid}: '{old_name}' -> '{new_name}'")
        else:
            data["name"] = new_name
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        changed += 1

    print("\n==================== 汇总 ====================")
    action = "将改动" if args.dry_run else "已改动"
    print(f"  {action} {changed} 个，无需改动 {unchanged} 个")
    if missing:
        print(f"  校对表里有 {len(missing)} 个 id 在库里找不到（可能拼写不符或不在前1000）：")
        print("   ", ", ".join(missing))


if __name__ == "__main__":
    main()
