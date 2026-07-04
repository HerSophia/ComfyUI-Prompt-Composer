"""Prompt Composer generation pipeline."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Dict, List, Optional, Set

from .ast_builder import ASTBuilder
from .compiler import create_compiler
from .constraint_resolver import ConstraintResolver
from .negatives import build_negative
from .models import (
    GenerationRequest,
    GenerationResponse,
    LogEntry,
    ResolverConfig,
    SamplingContext,
    TagEntry,
)
from .resolution import infer_resolution
from .sampler import create_sampler
from .tag_store import TagStore
from .identity_store import IdentityStore
from .identity_resolver import IdentityResolver
from .association_store import AssociationStore, load_default_association_store


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEMANTIC_DIR = DATA_DIR / "semantic"
RULES_PATH = SEMANTIC_DIR / "rules" / "overlay.json"
USER_DIR = DATA_DIR / "user"
IDENTITIES_DIR = SEMANTIC_DIR / "identities"


def load_default_store() -> TagStore:
    """按三层结构加载默认 TagStore。"""
    return TagStore.from_layers(
        semantic_dir=SEMANTIC_DIR,
        rules_path=RULES_PATH,
        user_dir=USER_DIR,
    )


def load_default_identity_store() -> IdentityStore:
    """加载默认 IdentityStore。"""
    return IdentityStore.from_directory(IDENTITIES_DIR)


class PromptComposerPipeline:
    """Core entry point for prompt generation."""

    def __init__(
        self,
        store: Optional[TagStore] = None,
        identity_store: Optional[IdentityStore] = None,
        association_store: Optional[AssociationStore] = None,
    ) -> None:
        self.store = store or load_default_store()
        self.identity_store = identity_store or load_default_identity_store()
        # 关联数据缺失时为空实例，任何关联查询返回空，默认行为不变。
        self.association_store = association_store or load_default_association_store()

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        logs: List[LogEntry] = []
        rng = random.Random(request.seed)
        disabled = {tag.strip().lower() for tag in request.disabled_tags if tag.strip()}
        fixed_names = [tag.strip() for tag in request.fixed_tags if tag.strip()]

        # 关联查询入口：给定已选标签，返回 {关联标签: 权重}。
        # 关联加成关闭时不会被采样器调用，开启时才参与加成。
        def association_lookup(tag: str) -> Dict[str, float]:
            return {
                item["tag"]: float(item["weight"])
                for item in self.association_store.related(tag)
            }

        # 冲突查询入口：给定标签，返回其 conflicts 集合（小写）。
        # 数据未补齐时返回空集，预检退化为不预检，最终由约束层兜底。
        def conflict_lookup(tag: str) -> Set[str]:
            entry = self.store.get(tag)
            if entry is None:
                return set()
            return {c.strip().lower() for c in entry.conflicts if c.strip()}

        context = SamplingContext(
            seed=request.seed,
            disabled_tags=disabled,
            fixed_tags={tag.lower() for tag in fixed_names},
            rating=request.rating,
            association_boost=request.association_boost,
            association_strength=request.association_strength,
            selected_tags=set(),
            association_lookup=association_lookup,
            conflict_lookup=conflict_lookup,
        )

        selected: List[TagEntry] = []
        order = 0

        # 二创：先展开 identity，得到一组固定 tag 和锁定特征。
        if request.identity:
            identity = self.identity_store.get(request.identity)
            if identity is None:
                logs.append(
                    LogEntry(
                        level="warning",
                        code="IDENTITY_NOT_FOUND",
                        message=f"Identity '{request.identity}' was not found.",
                        details={"identity": request.identity},
                    )
                )
            else:
                identity_tags, identity_logs = IdentityResolver(self.store).resolve(identity)
                logs.extend(identity_logs)
                for entry in identity_tags:
                    entry.order = order
                    selected.append(entry)
                    fixed_names.append(entry.tag)
                    order += 1

        for fixed_name in fixed_names[:]:
            entry = self.store.find(fixed_name)
            if entry is None:
                entry = TagEntry(tag=fixed_name, category="character", source="fixed", order=order)
                logs.append(
                    LogEntry(
                        level="warning",
                        code="FIXED_TAG_NOT_FOUND",
                        message=f"Fixed tag '{fixed_name}' was not found in TagStore. It was kept as a raw character tag.",
                        details={"tag": fixed_name},
                    )
                )
            else:
                entry = entry.clone(source="fixed", order=order)
            # identity 已经加过的同名 tag 不重复加。
            if any(t.tag.strip().lower() == fixed_name.strip().lower() for t in selected):
             continue
            selected.append(entry)
            order += 1

        # 已选集合用于关联加成。先把 identity 与固定标签装进去，
        # 采样循环里每选中一个就补进来。关闭时这个集合不影响采样。
        context.selected_tags = {t.tag.strip().lower() for t in selected}

        sampler = create_sampler(request.sampler)
        sample_categories = request.effective_categories()
        # explicit 时自动补上存在的 nsfw 分类（用户不用手写分类名）。
        if request.rating == "explicit":
            lock = {c.strip() for c in request.lock_categories}
            existing = set(sample_categories)
            for cat in self.store.categories():
                if cat.startswith("nsfw_") and cat not in existing and cat not in lock:
                    sample_categories.append(cat)
        for category in sample_categories:
            candidates = self.store.by_category(category)
            sampled = sampler.sample(candidates, context, rng)
            if sampled is None:
                logs.append(
                    LogEntry(
                        level="warning",
                        code="NO_CANDIDATE",
                        message=f"No candidate tag was available for category '{category}'.",
                        details={"category": category},
                    )
                )
                continue
            chosen = sampled.clone(source="sampled", order=order)
            selected.append(chosen)
            context.selected_tags.add(chosen.tag.strip().lower())
            order += 1

        # 顺序：先随机（采样），再禁用（过滤），最后联想（自动追加）。
        # 采样阶段本身会跳过禁用词，这里再做一次明确的过滤，
        # 把 identity 展开的角色特征等其他来源引入的禁用词一并清除，保证禁用彻底。
        # 用户手填的固定词是显式指定的，与禁用语义冲突时以显式指定优先，不清除。
        selected = self._apply_disabled(selected, disabled, logs)
        # identity 特征被禁用清除后，同步从 fixed_names 里剔除，
        # 避免约束解析把它当固定项保护，或经 requires 依赖被重新补回。
        kept = {t.tag.strip().lower() for t in selected}
        fixed_names = [n for n in fixed_names if n.strip().lower() in kept]
        context.selected_tags = {t.tag.strip().lower() for t in selected}

        # 禁用过滤之后、约束解析之前，按开关自动追加关联词。
        # 只对采样与固定得到的那套标签展开一轮，不递归。
        # 追加时同样排除禁用词，避免禁用被联想重新引回。
        # 两个开关关闭时无追加，行为与现在一致。
        selected, order = self._auto_add(request, selected, order, logs, disabled)

        resolver = ConstraintResolver(
            self.store, ResolverConfig(max_rounds=request.max_resolve_rounds)
        )
        resolved_tags, features, resolve_logs, discarded = resolver.resolve(
            selected, fixed_names
        )
        logs.extend(resolve_logs)

        ast = ASTBuilder().build(resolved_tags, features, logs)
        compiler = create_compiler(request.compiler, request.weights)
        prompt = compiler.compile(ast)

        # 根据最终参与的标签推断建议分辨率。
        width, height = infer_resolution(tag.tag for tag in resolved_tags)

        # 组装负面提示词。仅开关打开时才回收互斥淘汰标签，
        # 且回收标签要排除已出现在正向提示词里的，避免正负冲突。
        recycle_tags = None
        if request.recycle_conflict_negative:
            present = {tag.tag.strip().lower() for tag in resolved_tags}
            recycle_tags = [
                name for name in discarded if name.strip().lower() not in present
            ]
        negative = build_negative(
            rating=request.rating,
            use_builtin=request.use_builtin_negative,
            user_negative=request.user_negative,
            recycle_tags=recycle_tags,
        )

        return GenerationResponse(
            prompt=prompt,
            ast=ast,
            features=features,
            selected_tags=resolved_tags,
            logs=logs,
            width=width,
            height=height,
            negative=negative,
        )

    def _apply_disabled(
        self,
        selected: List[TagEntry],
        disabled: Set[str],
        logs: List[LogEntry],
    ) -> List[TagEntry]:
        """明确的禁用过滤步骤，位于采样之后、联想之前。

        把已选标签里命中禁用集合的清除掉。只有用户手填的固定词
       （source=fixed）在与禁用冲突时以显式指定优先，保留并记录一条 info 日志。
        角色（identity）展开的特征、采样得到的标签命中禁用时直接清除。
        禁用集合为空时原样返回，行为与原来一致。
        """
        if not disabled:
            return selected

        result: List[TagEntry] = []
        for entry in selected:
            key = entry.tag.strip().lower()
            if key not in disabled:
                result.append(entry)
                continue
            if entry.source == "fixed":
                # 用户既固定又禁用，显式指定优先，保留但提示。
                result.append(entry)
                logs.append(
                    LogEntry(
                        level="info",
                        code="DISABLED_TAG_KEPT_FIXED",
                        message=f"Disabled tag '{key}' was kept because it is a fixed tag.",
                        details={"tag": key},
                    )
                )
                continue
            logs.append(
                LogEntry(
                    level="info",
                    code="DISABLED_TAG_REMOVED",
                    message=f"Removed disabled tag '{key}'.",
                    details={"tag": key, "source": entry.source},
                )
            )
        return result

    def _auto_add(
        self,
        request: GenerationRequest,
        selected: List[TagEntry],
        order: int,
        logs: List[LogEntry],
        disabled: Optional[Set[str]] = None,
    ) -> tuple:
        """采样完成后按开关自动追加硬依赖 requires 与软关联 related。

        只对当前 selected 展开一轮，不递归。requires 从 TagStore 的 conflicts
        同源的约束字段取；related 从关联数据取，按强度与上限补。
        追加的词交给后续 constraint_resolver 处理冲突与去重。
        追加时排除禁用词，避免禁用被联想重新引回。
        两个开关关闭时无追加，行为与现在一致。
        """
        if not request.auto_add_requires and not request.auto_add_related:
            return selected, order

        disabled = disabled or set()
        present = {t.tag.strip().lower() for t in selected}
        # 只对采样与固定得到的这套标签展开，快照一份，不递归。
        base_tags = [t.tag for t in selected]

        # 自动追加硬依赖：把已选标签的 requires 依赖补进结果。
        if request.auto_add_requires:
            for name in base_tags:
                entry = self.store.get(name)
                if entry is None:
                    continue
                for req in entry.requires:
                    key = req.strip().lower()
                    if not key or key in present:
                        continue
                    # 禁用词不作为联想结果追加。
                    if key in disabled:
                        continue
                    req_entry = self.store.get(key)
                    if req_entry is None:
                        continue
                    present.add(key)
                    selected.append(req_entry.clone(source="auto_requires", order=order))
                    order += 1
                    logs.append(
                        LogEntry(
                            level="info",
                            code="AUTO_ADD_REQUIRES",
                            message=f"Auto added required tag '{key}' for '{name}'.",
                            details={"tag": key, "source": name},
                        )
                    )

        # 自动追加软关联：按关联强度与上限把 related 关联词补进结果。
        # 追加前排除已在结果里的标签，以及与已选存在 conflicts 的关联词。
        if request.auto_add_related:
            # 已选集合的冲突并集，用于过滤关联词。
            conflict_union: Set[str] = set()
            for name in list(present):
                entry = self.store.get(name)
                if entry is None:
                    continue
                conflict_union |= {
                    c.strip().lower() for c in entry.conflicts if c.strip()
                }

            for name in base_tags:
                for item in self.association_store.related(
                    name, limit=request.auto_add_related_limit
                ):
                    key = str(item["tag"]).strip().lower()
                    if not key or key in present:
                        continue
                    if key in conflict_union:
                        continue
                    # 禁用词不作为联想结果追加。
                    if key in disabled:
                        continue
                    rel_entry = self.store.get(key)
                    if rel_entry is None:
                        continue
                    present.add(key)
                    selected.append(rel_entry.clone(source="auto_related", order=order))
                    order += 1
                    logs.append(
                        LogEntry(
                            level="info",
                            code="AUTO_ADD_RELATED",
                            message=f"Auto added related tag '{key}' for '{name}'.",
                            details={"tag": key, "source": name, "weight": item["weight"]},
                        )
                    )

        return selected, order
