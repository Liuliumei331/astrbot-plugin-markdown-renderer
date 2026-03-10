"""AstrBot 插件入口。

这个文件只负责两件事：
1. 接到 AstrBot 的 LLM 响应事件。
2. 把原始 Markdown 文本交给渲染器转换，再写回响应对象。

真正的 Markdown -> 文本逻辑全部放在 markdown_renderer.py，避免入口文件变成大杂烩。
"""

import importlib.util
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star, register


def _load_transformer_class():
    """按文件路径加载同目录模块。

    AstrBot 的插件加载方式不一定会把插件目录自动塞进 sys.path，
    直接 `from markdown_renderer import ...` 在部分部署方式下会失败。
    这里改为基于 main.py 所在目录显式加载 sibling module，避免依赖宿主的导入细节。
    """

    module_path = Path(__file__).resolve().parent / "markdown_renderer.py"
    spec = importlib.util.spec_from_file_location(
        "astrbot_plugin_markdown_text_renderer.markdown_renderer", module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load markdown renderer from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MarkdownTextTransformer


MarkdownTextTransformer = _load_transformer_class()


@register(
    "astrbot_plugin_markdown_text_renderer",
    "Codex",
    "将 LLM 输出的 Markdown 渲染为纯文本或 ASCII 风格文本",
    "0.1.3",
    "https://github.com/Liuliumei331/astrbot-plugin-markdown-renderer",
)
class MarkdownTextRendererPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # AstrBot 会把插件配置注入进来。这里不直接散落使用 config，
        # 而是交给渲染器自己读取一份，保证“事件入口”和“渲染逻辑”职责分离。
        self.config = config
        self.transformer = MarkdownTextTransformer(config)

    @filter.on_llm_response()
    async def on_llm_response(
        self, event: AstrMessageEvent, resp: LLMResponse, *args
    ):
        # 插件级总开关。关闭后应尽早返回，避免无意义解析。
        if not self.config.get("enabled", True):
            return
        # 只处理真实的 LLM 文本响应。空响应和非文本响应直接跳过。
        if not resp or not resp.completion_text:
            return

        original_text = resp.completion_text
        # 检测开关默认开启：
        # 不是每条 LLM 输出都含 Markdown，先做一次轻量级特征判断，
        # 可以减少不必要的 parse / render 开销，也避免纯文本被“重排”。
        if self.config.get("detect_markdown_only", True):
            if not self.transformer.looks_like_markdown(original_text):
                return

        rendered_text = self.transformer.render(original_text)
        # 如果渲染结果为空，或者和原文完全一致，就不要回写，
        # 这样可以减少对下游插件链和日志的干扰。
        if not rendered_text or rendered_text == original_text:
            return

        # 直接改写 LLMResponse 的 completion_text，
        # 让后续发送到聊天平台的就是文本化后的结果。
        resp.completion_text = rendered_text

        if self.config.get("debug_log", False):
            logger.info(
                "[Markdown Text Renderer] mode=%s before=%r after=%r",
                self.config.get("mode", "ascii"),
                original_text[:80],
                rendered_text[:80],
            )
