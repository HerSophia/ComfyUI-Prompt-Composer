"""Build PromptAST from resolved tags."""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from .models import ASTNode, JsonDict, LogEntry, PromptAST, TagEntry


CATEGORY_PATHS: Dict[str, Tuple[str, str]] = {
    "gender": ("character", "gender"),
    "character": ("character", "gender"),
    "body": ("character", "body"),
    "face": ("character", "face"),
    "hair": ("character", "hair"),
    "eyes": ("character", "eyes"),
    "ears": ("character", "ears"),
    "clothing": ("character", "clothing"),
    "accessory": ("character", "accessory"),
    "pose": ("pose", "body"),
    "hand": ("pose", "hand"),
    "leg": ("pose", "leg"),
    "expression": ("pose", "expression"),
    "camera": ("camera", "shot"),
    "camera_angle": ("camera", "angle"),
    "composition": ("camera", "composition"),
    "background": ("environment", "background"),
    "weather": ("environment", "weather"),
    "lighting": ("environment", "lighting"),
    "style": ("style", "style_tags"),
    "quality": ("style", "quality"),
    "nsfw_act": ("nsfw", "act"),
    "nsfw_body": ("nsfw", "body"),
    "nsfw_gear": ("nsfw", "gear"),
}


class ASTBuilder:
    """Convert tags into the first version of PromptAST."""

    def build(
        self,
        tags: Sequence[TagEntry],
        features: JsonDict,
        logs: Sequence[LogEntry],
    ) -> PromptAST:
        ast = PromptAST()

        for tag in tags:
            node = ASTNode.from_tag(tag)
            path = CATEGORY_PATHS.get(tag.category)
            if path is None:
                ast.meta.setdefault("unknown_tags", []).append(node)
                continue
            section_name, leaf_name = path
            section = getattr(ast, section_name)
            section[leaf_name].append(node)

        ast.meta["features"] = dict(features)
        ast.meta["source_tags"] = [tag.to_dict() for tag in tags]
        ast.meta["logs"] = [log.to_dict() for log in logs]
        return ast
