"""ComfyUI node adapter for Prompt Composer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from ..core import GenerationRequest, PromptComposerPipeline
from ..core.pipeline import load_default_identity_store
from ..core.association_store import load_default_association_store


# 复用一个 pipeline 实例，避免每次执行都重新加载数据。
_PIPELINE = None


def _get_pipeline() -> PromptComposerPipeline:
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = PromptComposerPipeline()
    return _PIPELINE


# 选项分隔符。用全角竖线，不易和 id 或中文名里的字符冲突，便于解析回 id。
_IDENTITY_SEP = " ｜ "


def _parse_identity(value: str) -> str:
    """从下拉选项文本里解析出角色 id。选项以 id 开头，取分隔符前的部分。"""
    text = (value or "").strip()
    if not text:
        return ""
    return text.split(_IDENTITY_SEP)[0].strip()


# 默认配置。config 为空或字段缺失时回退到这里，保证默认行为与改造前一致。
_DEFAULT_CONFIG = {
    "sampler": "weighted",
    "rating": "general",
    "identity": "",
    "fixed_tags": ["1girl"],
    "disabled_tags": [],
    "random_categories": [
        "hair",
        "eyes",
        "clothing",
        "expression",
        "pose",
        "hand",
        "leg",
        "camera",
        "composition",
        "background",
        "lighting",
    ],
    "lock_categories": [],
    "return_debug": True,
    # 分辨率模式：auto 按提示词推断，manual用下面两个手动值。
    "resolution_mode": "auto",
    "manual_width": 896,
    "manual_height": 1152,
    # 标签到权重的映射，空表示不加权。
    "weights": {},
    # 是否启用内置负面词。
    "use_builtin_negative": True,
    # 用户追加的负面词列表。
    "user_negative": [],
    # 是否把互斥淘汰标签回收进负面。
    "recycle_conflict_negative": False,
    # 关联加成：采样时根据已选标签抬高关联候选的权重，默认关闭。
    "association_boost": False,
    # 关联加成强度系数，为 0 等价于关闭。
    "association_strength": 0.5,
    # 采样完成后自动追加硬依赖 requires，默认关闭。
    "auto_add_requires": False,
    # 采样完成后自动追加软关联 related，默认关闭。
    "auto_add_related": False,
}


def _default_config_json() -> str:
    """默认 config 的 JSON 字符串，作为 config widget 的初始值。"""
    return json.dumps(_DEFAULT_CONFIG, ensure_ascii=False, indent=2)


def _coerce_list(value) -> List[str]:
    """把 config 里的字段规整成字符串列表。

    兼容两种写法：真正的数组，以及逗号分隔的字符串（方便手动编辑 config）。
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []

def _coerce_positive_int(value) -> int:
    """把值转成正整数，失败或非正时返回 0。"""
    try:
        result = int(value)
    except (TypeError, ValueError):
        return 0
    return result if result > 0 else 0


def _coerce_strength(value, default: float = 0.5) -> float:
    """把关联加成强度解析成浮点，非法回退默认，范围限定在 [0, 5]。"""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result < 0.0:
        return 0.0
    if result > 5.0:
        return 5.0
    return result


def _coerce_weights(value) -> dict:
    """把 config 里的 weights 规整成标签到浮点的字典。

    只接受字典且值能转成浮点，非法项跳过，避免一份坏数据就报错。
    """
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, raw in value.items():
        name = str(key).strip()
        if not name:
            continue
        try:
            result[name] = float(raw)
        except (TypeError, ValueError):
            continue
    return result



class PromptComposerGenerateNode:
    """Generate a structured prompt through Prompt Composer Core."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seed": ("INT", {"default": 0, "min": 0, "max": 2**31 - 1}),
                # 全部生成参数都收进这一个 JSON 配置里，由前端配置面板读写。
                # 节点定义加载时不做任何数据加载，保持启动零开销。
                "config": (
                    "STRING",
                    {"default": _default_config_json(), "multiline": True},
                ),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("prompt", "negative", "ast_json", "debug_log", "width", "height")
    FUNCTION = "generate"
    CATEGORY = "Prompt Composer"

    def generate(self, seed: int, config: str):
        cfg = self._parse_config(config)
        request = GenerationRequest(
                seed=seed,
            sampler=cfg["sampler"],
            rating=cfg["rating"],
            identity=(_parse_identity(cfg["identity"]) or None),
            fixed_tags=cfg["fixed_tags"],
            disabled_tags=cfg["disabled_tags"],
            random_categories=cfg["random_categories"],
            lock_categories=cfg["lock_categories"],
            compiler="danbooru",
            weights=cfg["weights"],
            use_builtin_negative=cfg["use_builtin_negative"],
            user_negative=cfg["user_negative"],
            recycle_conflict_negative=cfg["recycle_conflict_negative"],
            association_boost=cfg["association_boost"],
            association_strength=cfg["association_strength"],
            auto_add_requires=cfg["auto_add_requires"],
            auto_add_related=cfg["auto_add_related"],
        )
        response = _get_pipeline().generate(request)
        ast_json = json.dumps(response.ast.to_dict(), ensure_ascii=False, indent=2)
        debug_log = ""
        if cfg["return_debug"]:
            debug_log = json.dumps(
                [log.to_dict() for log in response.logs], ensure_ascii=False, indent=2
            )
        # 手动模式且宽高有效时用手动值，否则用推断值。
        if cfg["resolution_mode"] == "manual" and cfg["manual_width"] > 0 and cfg["manual_height"] > 0:
            width = cfg["manual_width"]
            height = cfg["manual_height"]
        else:
            width = int(response.width)
            height = int(response.height)
        resolution_text = f"{width} x {height}"
        # ui 字段回传给前端显示，不影响 result 下游连线。
        # negative 也回传，供前端历史记录使用。
        return {
            "ui": {
                "prompt": [response.prompt],
                "negative": [response.negative],
                "resolution": [resolution_text],
            },
            "result": (
                response.prompt,
                response.negative,
                ast_json,
                debug_log,
                width,
                height,
            ),
        }

    @staticmethod
    def _parse_config(config: str) -> dict:
        """解析 config JSON，容错处理。

        解析失败或字段缺失时回退默认值，保证不因一份坏 JSON 就报错，
        也保证 config 为空时等价于默认参数。
        """
        data = {}
        if isinstance(config, str) and config.strip():
            try:
                loaded = json.loads(config)
                if isinstance(loaded, dict):
                    data = loaded
            except (ValueError, TypeError):
                data = {}
        sampler = str(data.get("sampler", _DEFAULT_CONFIG["sampler"]) or "weighted")
        rating = str(data.get("rating", _DEFAULT_CONFIG["rating"]) or "general")
        identity = str(data.get("identity", _DEFAULT_CONFIG["identity"]) or "")
        # fixed_tags 缺失时用默认，显式给空数组时尊重用户选择。
        if "fixed_tags" in data:
            fixed_tags = _coerce_list(data.get("fixed_tags"))
        else:
            fixed_tags = list(_DEFAULT_CONFIG["fixed_tags"])
        disabled_tags = _coerce_list(data.get("disabled_tags"))
        if "random_categories" in data:
            random_categories = _coerce_list(data.get("random_categories"))
        else:
            random_categories = list(_DEFAULT_CONFIG["random_categories"])
        lock_categories = _coerce_list(data.get("lock_categories"))
        return_debug = bool(data.get("return_debug", _DEFAULT_CONFIG["return_debug"]))
        # 负面词与权重字段解析，都带默认与容错。
        weights = _coerce_weights(data.get("weights"))
        use_builtin_negative = bool(
            data.get("use_builtin_negative", _DEFAULT_CONFIG["use_builtin_negative"])
        )
        user_negative = _coerce_list(data.get("user_negative"))
        recycle_conflict_negative = bool(
            data.get(
                "recycle_conflict_negative",
                _DEFAULT_CONFIG["recycle_conflict_negative"],
            )
        )
        # 关联加成与自动追加字段解析，都带默认与容错。
        # 开关用 bool 包装，强度用浮点解析并限定范围。
        association_boost = bool(
            data.get("association_boost", _DEFAULT_CONFIG["association_boost"])
        )
        association_strength = _coerce_strength(
            data.get("association_strength", _DEFAULT_CONFIG["association_strength"]),
            float(_DEFAULT_CONFIG["association_strength"]),
        )
        auto_add_requires = bool(
            data.get("auto_add_requires", _DEFAULT_CONFIG["auto_add_requires"])
        )
        auto_add_related = bool(
            data.get("auto_add_related", _DEFAULT_CONFIG["auto_add_related"])
        )
        # 分辨率模式：非法值回退 auto；手动宽高解析失败或非正回退 0。
        mode = str(data.get("resolution_mode", _DEFAULT_CONFIG["resolution_mode"]) or "auto")
        if mode not in ("auto", "manual"):
            mode = "auto"
        manual_width = _coerce_positive_int(data.get("manual_width"))
        manual_height = _coerce_positive_int(data.get("manual_height"))
        return {
            "sampler": sampler,
            "rating": rating,
            "identity": identity,
            "fixed_tags": fixed_tags,
            "disabled_tags": disabled_tags,
            "random_categories": random_categories,
            "lock_categories": lock_categories,
            "return_debug": return_debug,
            "resolution_mode": mode,
            "manual_width": manual_width,
            "manual_height": manual_height,
            "weights": weights,
            "use_builtin_negative": use_builtin_negative,
            "user_negative": user_negative,
            "recycle_conflict_negative": recycle_conflict_negative,
            "association_boost": association_boost,
            "association_strength": association_strength,
            "auto_add_requires": auto_add_requires,
            "auto_add_related": auto_add_related,
        }

# ---------------------------------------------------------------------------
# 后端只读接口：为前端角色检索面板提供 identity 索引。
#
# 索引优先读取离线生成的 identities_index.json（进程内缓存），文件缺失时
# 回退到实时扫描 identity 目录。所有 ComfyUI 相关的 import 都放在 try/except
# 里，非 ComfyUI 环境（例如跑单元测试）时静默跳过，保证 core 不依赖 ComfyUI。
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_INDEX_PATH = _DATA_DIR / "identities_index.json"
_TAGS_INDEX_PATH = _DATA_DIR / "tags_index.json"
_SEMANTIC_DIR = _DATA_DIR / "semantic"

# 进程内缓存，首次请求后不再重复读盘或扫描。
_IDENTITY_INDEX_CACHE: Optional[List[dict]] = None
_TAGS_INDEX_CACHE: Optional[List[dict]] = None


def _build_index_from_store() -> List[dict]:
    """回退方案：索引文件缺失时，实时扫描 identity 目录生成等价结构。"""
    entries: List[dict] = []
    try:
        identities = load_default_identity_store().all()
    except Exception:
        return entries
    for identity in identities:
        display_tag = ""
        if identity.identity_tags:
            display_tag = str(identity.identity_tags[0]).strip()
        entries.append(
            {
                "id": identity.id,
                "name": identity.name or "",
                "display_tag": display_tag,
            }
        )
    entries.sort(key=lambda entry: entry["id"])
    return entries


def get_identity_index() -> List[dict]:
    """返回 identity 索引，带进程内缓存与缺失回退。"""
    global _IDENTITY_INDEX_CACHE
    if _IDENTITY_INDEX_CACHE is not None:
        return _IDENTITY_INDEX_CACHE
    if _INDEX_PATH.exists():
        try:
            with _INDEX_PATH.open("r", encoding="utf-8") as file:
                _IDENTITY_INDEX_CACHE = json.load(file)
            return _IDENTITY_INDEX_CACHE
        except Exception:
            pass
    # 文件缺失或读取失败：回退到实时扫描，并提示建议重建索引。
    print(
        "[Prompt Composer] identities_index.json 缺失或无法读取，"
        "已回退到实时扫描。建议运行 tools/build_identity_index.py 重建索引。"
    )
    _IDENTITY_INDEX_CACHE = _build_index_from_store()
    return _IDENTITY_INDEX_CACHE


def _build_tags_from_semantic() -> List[dict]:
    """回退方案：标签索引缺失时，实时扫描semantic 目录的分类 JSON。"""
    entries: List[dict] = []
    if not _SEMANTIC_DIR.exists():
        return entries
    for file_path in sorted(_SEMANTIC_DIR.glob("*.json")):
        try:
            with file_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except Exception:
            continue
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            tag = str(item.get("tag", "") or "").strip()
            if not tag:
                continue
            entries.append(
                {
                    "tag": tag,
                    "category": str(item.get("category", "") or "").strip(),
                    "label_zh": str(item.get("label_zh", "") or "").strip(),
                }
            )
    entries.sort(key=lambda entry: (entry["category"], entry["tag"]))
    return entries


def get_tags_index() -> List[dict]:
    """返回标签索引，带进程内缓存与缺失回退。"""
    global _TAGS_INDEX_CACHE
    if _TAGS_INDEX_CACHE is not None:
        return _TAGS_INDEX_CACHE
    if _TAGS_INDEX_PATH.exists():
        try:
            with _TAGS_INDEX_PATH.open("r", encoding="utf-8") as file:
                _TAGS_INDEX_CACHE = json.load(file)
            return _TAGS_INDEX_CACHE
        except Exception:
            pass
    print(
        "[Prompt Composer] tags_index.json 缺失或无法读取，"
        "已回退到实时扫描。建议运行 tools/build_tag_index.py 重建索引。"
    )
    _TAGS_INDEX_CACHE = _build_tags_from_semantic()
    return _TAGS_INDEX_CACHE


def get_associations(tag: str, limit: int = 0) -> List[dict]:
    """返回某标签的关联词列表，带进程内缓存。

    关联数据缺失时返回空列表，不报错。每项含关联标签与权重。
    """
    if not tag:
        return []
    store = load_default_association_store()
    return [dict(item) for item in store.related(tag, limit=limit)]


def _register_routes() -> None:
    """注册前端使用的只读路由。仅在 ComfyUI 环境下生效。"""
    try:
        from server import PromptServer
        from aiohttp import web
    except Exception:
        return

    @PromptServer.instance.routes.get("/prompt_composer/identities")
    async def _identities_route(request):
        return web.json_response(get_identity_index())

    @PromptServer.instance.routes.get("/prompt_composer/tags")
    async def _tags_route(request):
        return web.json_response(get_tags_index())

    @PromptServer.instance.routes.get("/prompt_composer/associations")
    async def _associations_route(request):
        # 按 tag 参数返回该标签的关联词列表。limit 可选，默认不限。
        tag = request.query.get("tag", "")
        try:
            limit = int(request.query.get("limit", "0"))
        except (TypeError, ValueError):
            limit = 0
        return web.json_response(get_associations(tag, limit=limit))


_register_routes()
