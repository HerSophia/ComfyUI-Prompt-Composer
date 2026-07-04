"""Feature inference from selected tags."""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from .models import JsonDict, TagEntry


class FeatureConflict:
    """Record of a conflicting feature value."""

    def __init__(self, feature: str, existing_value, existing_tag: str, new_value, new_tag: str):
        self.feature = feature
        self.existing_value = existing_value
        self.existing_tag = existing_tag
        self.new_value = new_value
        self.new_tag = new_tag

    def to_dict(self) -> JsonDict:
        return {
            "feature": self.feature,
            "existing_value": self.existing_value,
            "existing_tag": self.existing_tag,
            "new_value": self.new_value,
            "new_tag": self.new_tag,
        }


class FeatureInference:
    """Merge features from tags and detect conflicts."""

    def infer(self, tags: Sequence[TagEntry]) -> Tuple[JsonDict, List[FeatureConflict]]:
        features: JsonDict = {}
        owners: Dict[str, str] = {}
        conflicts: List[FeatureConflict] = []

        for tag in tags:
            for name, value in tag.features.items():
                if name not in features:
                    features[name] = value
                    owners[name] = tag.tag
                    continue
                if features[name] != value:
                    conflicts.append(
                        FeatureConflict(
                            feature=name,
                            existing_value=features[name],
                            existing_tag=owners[name],
                            new_value=value,
                            new_tag=tag.tag,
                        )
                    )

            for implied in tag.implies:
                key = implied.strip()
                if key and key not in features:
                    features[key] = True

        return features, conflicts
