"""ComfyUI custom node entry for Prompt Composer."""

from .prompt_composer.nodes import PromptComposerGenerateNode

NODE_CLASS_MAPPINGS = {
    "PromptComposerGenerate": PromptComposerGenerateNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PromptComposerGenerate": "Prompt Composer Generate",
}

# 前端脚本目录。ComfyUI 会自动加载该目录下的 js 作为扩展。
# 只是声明一个静态目录，不带来启动开销。
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
