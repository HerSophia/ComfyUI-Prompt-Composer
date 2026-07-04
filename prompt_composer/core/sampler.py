"""Sampler implementations."""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Sequence, Set

from .models import SamplingContext, TagEntry


# 关联加成对基础权重的乘法因子上下限，防止单个候选被抬得过高或压得过低。
_BOOST_MIN = 1.0
_BOOST_MAX = 4.0


class BaseSampler:
    """Sampler interface."""

    def sample(
        self, candidates: Sequence[TagEntry], context: SamplingContext, rng: random.Random
    ) -> Optional[TagEntry]:
        raise NotImplementedError


def _filter_candidates(
    candidates: Sequence[TagEntry], context: SamplingContext
) -> List[TagEntry]:
    result: List[TagEntry] = []
    for entry in candidates:
        if not entry.enabled:
            continue
        if entry.tag.strip().lower() in context.disabled_tags:
            continue
        # 分级过滤：general 请求不选 explicit 内容（双保险）。
        if context.rating != "explicit" and entry.rating == "explicit":
            continue
        result.append(entry)
    return result


class RandomSampler(BaseSampler):
    """Uniform random selection."""

    def sample(
        self, candidates: Sequence[TagEntry], context: SamplingContext, rng: random.Random
    ) -> Optional[TagEntry]:
        pool = _filter_candidates(candidates, context)
        if not pool:
            return None
        return rng.choice(pool)


def _boost_factor(entry: TagEntry, context: SamplingContext) -> float:
    """根据已选集合对当前候选算一个乘法加成因子。

    基础因子 1.0。已选集合里的标签对当前候选有关联时，按关联强度
    与强度系数累加。加成前先做 conflicts 预检：候选与已选集合里任一
    标签存在 conflicts 关系时，不加成。开关关闭或强度为 0 时返回 1.0。
    """
    if not context.association_boost or context.association_strength <= 0:
        return 1.0
    if context.association_lookup is None or not context.selected_tags:
        return 1.0

    candidate = entry.tag.strip().lower()

    # conflicts预检：候选与已选集合存在冲突时不加成。
    if context.conflict_lookup is not None:
        conflicts = context.conflict_lookup(candidate)
        if conflicts and (conflicts & context.selected_tags):
            return 1.0

    total = 0.0
    for chosen in context.selected_tags:
        related = context.association_lookup(chosen)
        if not related:
            continue
        strength = related.get(candidate, 0.0)
        if strength > 0:
            total += strength

    if total <= 0:
        return 1.0
    factor = 1.0 + total * context.association_strength
    if factor < _BOOST_MIN:
        return _BOOST_MIN
    if factor > _BOOST_MAX:
        return _BOOST_MAX
    return factor


class WeightedSampler(BaseSampler):
    """Weighted random selection based on the weight field."""

    def sample(
        self, candidates: Sequence[TagEntry], context: SamplingContext, rng: random.Random
    ) -> Optional[TagEntry]:
        pool = _filter_candidates(candidates, context)
        weighted = [entry for entry in pool if entry.weight > 0]
        if not weighted:
            if pool:
                return rng.choice(pool)
            return None
        # 关联加成关闭或强度为 0 时，_boost_factor 恒返 1.0，与原逻辑一致。
        weights = [entry.weight * _boost_factor(entry, context) for entry in weighted]
        return rng.choices(weighted, weights=weights, k=1)[0]


class FixedSampler(BaseSampler):
    """Return the first available candidate, used for fixed selections."""

    def sample(
        self, candidates: Sequence[TagEntry], context: SamplingContext, rng: random.Random
    ) -> Optional[TagEntry]:
        pool = _filter_candidates(candidates, context)
        if not pool:
            return None
        return pool[0]


_SAMPLERS = {
    "random": RandomSampler,
    "weighted": WeightedSampler,
    "fixed": FixedSampler,
}


def create_sampler(name: str) -> BaseSampler:
    key = (name or "").strip().lower()
    sampler_cls = _SAMPLERS.get(key)
    if sampler_cls is None:
        raise ValueError(f"Unknown sampler: {name}")
    return sampler_cls()
