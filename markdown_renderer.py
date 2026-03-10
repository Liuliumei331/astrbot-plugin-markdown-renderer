"""Markdown -> 文本渲染器。

整体思路不是“正则把 Markdown 删掉”，而是：
1. 先用 markdown-it-py 把 Markdown 解析成 token 流。
2. 再按 block / inline 两层结构把 token 渲染成目标文本。

这样做的好处是：
- 能正确处理嵌套结构，而不是只会替换局部字符串。
- 表格、列表、引用、代码块可以走各自的专门逻辑。
- 后面如果要扩展 HTML、任务列表、数学公式，也有明确的挂点。
"""

import html
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from markdown_it import MarkdownIt
from markdown_it.token import Token

try:
    # wcwidth 用来按“显示宽度”计算字符占位，尤其是中日韩宽字符。
    # 如果环境里没有这个依赖，也不应该导致插件启动失败，所以做降级兜底。
    from wcwidth import wcswidth as _wcswidth
except ImportError:
    def _wcswidth(text: str) -> int:
        # 标准库兜底版本：
        # 全角 / 宽字符按 2 列算，其余按 1 列算。
        # 它不如 wcwidth 完整，但比直接 len(text) 更接近终端真实显示宽度。
        width = 0
        for char in text:
            width += 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
        return width


HTML_TAG_RE = re.compile(r"<[^>]+>")
MARKDOWN_HINT_RE = re.compile(
    r"(?m)(^#{1,6}\s)|(^>\s)|(^\s*[-*+]\s)|(^\s*\d+\.\s)|(```)|(\[[^\]]+\]\([^)]+\))|(\|.+\|)"
)


@dataclass
class RenderConfig:
    """渲染配置的最小归一化结果。

    这里故意只保留渲染器真正关心的字段，避免直接把外部配置对象
    带进整个渲染流程，后面做单元测试也更容易。
    """

    mode: str = "ascii"
    keep_links: bool = True
    strip_html: bool = True
    detect_markdown_only: bool = True
    table_mode: str = "ascii"
    keep_code_language: bool = True
    preserve_inline_semantics: bool = True


class MarkdownTextTransformer:
    def __init__(self, config: dict):
        # 这里先把 mode 做合法值收敛，避免出现拼写错误时渲染流程进入未知分支。
        mode = str(config.get("mode", "ascii")).lower()
        table_mode = str(config.get("table_mode", "ascii")).lower()
        if mode not in {"ascii", "plain"}:
            mode = "ascii"
        if table_mode not in {"ascii", "plain"}:
            table_mode = "ascii"

        self.config = RenderConfig(
            mode=mode,
            keep_links=bool(config.get("keep_links", True)),
            strip_html=bool(config.get("strip_html", True)),
            detect_markdown_only=bool(config.get("detect_markdown_only", True)),
            table_mode=table_mode,
            keep_code_language=bool(config.get("keep_code_language", True)),
            preserve_inline_semantics=bool(
                config.get("preserve_inline_semantics", True)
            ),
        )

        # 用 CommonMark 作为基底，再手动打开我们 v1 真正需要的扩展。
        # 这样行为边界比“模糊的全家桶 preset”更容易把控。
        self.md = MarkdownIt("commonmark", {"breaks": True, "linkify": True})
        self.md.enable(["table", "strikethrough"])

    def looks_like_markdown(self, text: str) -> bool:
        # 这里只做轻量判断，不追求完全准确。
        # 目的只是“值得不值得进入完整解析流程”，不是替代真正解析器。
        return bool(MARKDOWN_HINT_RE.search(text))

    def render(self, text: str) -> str:
        # markdown-it-py 输出的是线性 token 流。
        # 后续的 _render_blocks / _render_inline 会根据 nesting 信息递归消费它。
        tokens = self.md.parse(text)
        rendered = self._render_blocks(tokens, 0, len(tokens))
        return self._normalize_output(rendered)

    def _render_blocks(
        self, tokens: list[Token], start: int, end: int, compact: bool = False
    ) -> str:
        """渲染块级 token。

        这里处理段落、标题、列表、引用、表格、代码块等 block 元素。
        block 层只负责“整体结构”，行内强调、链接、图片则交给 inline 层。
        """

        blocks: list[str] = []
        idx = start
        while idx < end:
            token = tokens[idx]
            if token.type == "heading_open":
                # heading_open ... heading_close 之间通常会包含一个 inline token，
                # 所以先找闭合位置，再把中间那段交给 inline 渲染。
                close = self._find_close(tokens, idx)
                content = self._render_inline_range(tokens, idx + 1, close)
                blocks.append(self._render_heading(content, token.tag))
                idx = close + 1
                continue
            if token.type == "paragraph_open":
                close = self._find_close(tokens, idx)
                content = self._render_inline_range(tokens, idx + 1, close)
                if content.strip():
                    blocks.append(content.strip())
                idx = close + 1
                continue
            if token.type in {"bullet_list_open", "ordered_list_open"}:
                # 列表本身是一个容器，真正的条目在 list_item_open / close 里。
                close = self._find_close(tokens, idx)
                ordered = token.type == "ordered_list_open"
                start_num = int(self._attr(token, "start") or "1")
                blocks.append(
                    self._render_list(tokens, idx + 1, close, ordered, start_num)
                )
                idx = close + 1
                continue
            if token.type == "blockquote_open":
                # 引用块先把内部内容正常渲染，再统一加前缀。
                # 这样内部如果再嵌列表 / 表格 / 代码块，也能保留结构。
                close = self._find_close(tokens, idx)
                body = self._render_blocks(tokens, idx + 1, close, compact=True)
                blocks.append(self._prefix_lines(body, "❝ ", "❝ "))
                idx = close + 1
                continue
            if token.type in {"fence", "code_block"}:
                blocks.append(self._render_code_block(token))
                idx += 1
                continue
            if token.type == "table_open":
                # 表格必须走专门逻辑，不能把内部 token 直接拼文本，
                # 否则最终只会剩下一堆单元格内容而丢掉列结构。
                close = self._find_close(tokens, idx)
                blocks.append(self._render_table(tokens, idx + 1, close))
                idx = close + 1
                continue
            if token.type == "hr":
                blocks.append("-" * 24)
                idx += 1
                continue
            if token.type == "html_block":
                html_text = (
                    token.content
                    if not self.config.strip_html
                    else self._strip_html(token.content)
                )
                if html_text.strip():
                    blocks.append(html_text.strip())
                idx += 1
                continue
            if token.type == "inline":
                # 某些场景里 inline token 可能直接出现在当前层。
                # 这里兜底渲染，避免文本被吞掉。
                content = self._render_inline(token.children or [])
                if content.strip():
                    blocks.append(content.strip())
            idx += 1
        separator = "\n" if compact else "\n\n"
        return separator.join(block for block in blocks if block.strip())

    def _render_list(
        self,
        tokens: list[Token],
        start: int,
        end: int,
        ordered: bool,
        start_num: int,
    ) -> str:
        items: list[str] = []
        idx = start
        number = start_num
        while idx < end:
            token = tokens[idx]
            if token.type != "list_item_open":
                idx += 1
                continue
            close = self._find_close(tokens, idx)
            # 每个 list item 内部仍然可能是多个 block：
            # 段落、子列表、引用块都可能出现，所以继续复用 block 渲染。
            body = self._render_blocks(tokens, idx + 1, close, compact=True).strip()

            task_match = None
            if not ordered:
                task_match = re.match(r"^\[(x|X| )\]\s+(.*)$", body, flags=re.DOTALL)

            if task_match:
                checked = task_match.group(1).lower() == "x"
                marker = "[x] " if checked else "[ ] "
                body = task_match.group(2).strip()
            else:
                marker = f"{number}. " if ordered else "- "

            indent = " " * len(marker)
            items.append(self._prefix_lines(body, marker, indent))
            number += 1
            idx = close + 1
        return "\n".join(item for item in items if item.strip())

    def _render_table(self, tokens: list[Token], start: int, end: int) -> str:
        """把 markdown-it 的表格 token 还原成行列结构，再选一种文本策略输出。"""

        rows: list[list[str]] = []
        header_count = 0
        idx = start
        in_head = False

        while idx < end:
            token = tokens[idx]
            if token.type == "thead_open":
                in_head = True
            elif token.type == "thead_close":
                in_head = False
            elif token.type == "tr_open":
                close = self._find_close(tokens, idx)
                row = self._parse_table_row(tokens, idx + 1, close)
                rows.append(row)
                if in_head:
                    header_count += 1
                idx = close
            idx += 1

        if not rows:
            return ""

        if self.config.table_mode == "plain":
            return self._render_plain_table(rows, header_count)
        return self._render_ascii_table(rows, header_count)

    def _parse_table_row(self, tokens: list[Token], start: int, end: int) -> list[str]:
        # th / td 内部仍然是 inline token，因此单元格内容也统一走 inline 渲染。
        cells: list[str] = []
        idx = start
        while idx < end:
            token = tokens[idx]
            if token.type not in {"th_open", "td_open"}:
                idx += 1
                continue
            close = self._find_close(tokens, idx)
            cells.append(self._render_inline_range(tokens, idx + 1, close).strip())
            idx = close + 1
        return cells

    def _render_plain_table(self, rows: list[list[str]], header_count: int) -> str:
        # plain 模式不追求“像表格”，只追求可复制和轻量阅读。
        # 用 tab 分列，适合终端、日志和二次处理。
        lines: list[str] = []
        header = rows[:header_count] if header_count else []
        body = rows[header_count:] if header_count else rows

        if header:
            lines.append("\t".join(header[0]))
            lines.append("\t".join("-" for _ in header[0]))

        for row in body:
            lines.append("\t".join(row))
        return "\n".join(lines)

    def _render_ascii_table(self, rows: list[list[str]], header_count: int) -> str:
        # ASCII 表格需要两步：
        # 1. 先把每行补到相同列数。
        # 2. 再按显示宽度求每列最大宽度，最后统一拼边框。
        col_count = max(len(row) for row in rows)
        normalized_rows = [row + [""] * (col_count - len(row)) for row in rows]
        widths = [
            max(self._display_width(cell) for cell in column)
            for column in zip(*normalized_rows)
        ]
        separator = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

        lines = [separator]
        for row_index, row in enumerate(normalized_rows):
            padded = [self._pad_display(cell, widths[i]) for i, cell in enumerate(row)]
            lines.append("| " + " | ".join(padded) + " |")
            if row_index + 1 == header_count or row_index == len(normalized_rows) - 1:
                lines.append(separator)
        if header_count == 0 and lines[-1] != separator:
            lines.append(separator)
        return "\n".join(lines)

    def _render_heading(self, text: str, tag: str) -> str:
        # plain 模式尽量简洁，ascii 模式适当强化层级感。
        level = int(tag[1]) if tag.startswith("h") else 1
        text = text.strip()
        if not text:
            return ""
        if self.config.mode == "plain":
            return f"{'#' * level} {text}"
        if level == 1:
            bar = "=" * max(self._display_width(text), 3)
            return f"{text}\n{bar}"
        if level == 2:
            bar = "-" * max(self._display_width(text), 3)
            return f"{text}\n{bar}"
        if level == 3:
            # 三级标题改成更接近侧边栏的标记，和引用区分开。
            return f"▎{text}"
        if level == 4:
            # 四级标题继续弱化一个层级，但不缩进正文所在列。
            return f"▹ {text}"
        return f"{'#' * level} {text}"

    def _render_code_block(self, token: Token) -> str:
        # fenced code block 的 info 字段里通常包含语言名，例如 python / json。
        code = token.content.rstrip("\n")
        info = (
            (token.info or "").strip().split()[0]
            if getattr(token, "info", "")
            else ""
        )
        if self.config.mode == "plain":
            lines = code.splitlines() or [""]
            if self.config.keep_code_language and info:
                lines.insert(0, f"[code:{info}]")
            return "\n".join(f"    {line}" for line in lines)

        label = "[code]"
        if self.config.keep_code_language and info:
            label = f"[code:{info}]"
        return "\n".join([label, code, "[/code]"]).strip()

    def _render_inline_range(self, tokens: list[Token], start: int, end: int) -> str:
        # block 里的 inline 通常还会套一层 inline token。
        # 这里只抽取那一层真正的 children 去渲染。
        parts: list[str] = []
        for token in tokens[start:end]:
            if token.type == "inline":
                parts.append(self._render_inline(token.children or []))
        return "".join(parts)

    def _render_inline(self, tokens: list[Token]) -> str:
        """渲染行内 token。

        这里不去保留 Markdown 原始符号，而是保留其“语义后的文本”：
        - emphasis / strong / strikethrough 会转成普通文本标记
        - link 渲染成 `label (url)` 或仅 `label`
        - image 渲染成图片占位文本
        """

        parts: list[str] = []
        idx = 0
        while idx < len(tokens):
            token = tokens[idx]
            if token.type == "text":
                parts.append(token.content)
            elif token.type == "code_inline":
                parts.append(token.content)
            elif token.type in {"em_open", "strong_open", "s_open"}:
                close = self._find_close(tokens, idx)
                content = self._render_inline(tokens[idx + 1 : close]).strip()
                if content:
                    parts.append(self._render_inline_semantic(token.type, content))
                idx = close
            elif token.type in {"softbreak", "hardbreak"}:
                parts.append("\n")
            elif token.type == "html_inline":
                html_text = (
                    token.content
                    if not self.config.strip_html
                    else self._strip_html(token.content)
                )
                parts.append(html_text)
            elif token.type == "image":
                alt = token.content or "image"
                src = self._attr(token, "src")
                if self.config.keep_links and src:
                    parts.append(f"[图片: {alt}] ({src})")
                else:
                    parts.append(f"[图片: {alt}]")
            elif token.type == "link_open":
                # 链接内部可能还有强调、code_inline 等子节点，所以不能直接拿 content，
                # 必须递归渲染 link_open 到 link_close 之间的内容。
                close = self._find_close(tokens, idx)
                label = self._render_inline(tokens[idx + 1 : close]).strip()
                href = self._attr(token, "href")
                if self.config.keep_links and href:
                    if label and label != href:
                        parts.append(f"{label} ({href})")
                    else:
                        parts.append(href)
                else:
                    parts.append(label or (href or ""))
                idx = close
            idx += 1
        return html.unescape("".join(parts))

    def _render_inline_semantic(self, token_type: str, content: str) -> str:
        """把 emphasis / strong / strikethrough 渲染成不依赖 Markdown 解释器的文本标记。"""

        if not self.config.preserve_inline_semantics:
            return content

        if token_type == "em_open":
            return f"「{content}」"
        if token_type == "strong_open":
            return f"【{content}】"
        if token_type == "s_open":
            return f"已删除：{content}"
        return content

    def _find_close(self, tokens: list[Token], start: int) -> int:
        """找到当前 open token 对应的 close token。

        markdown-it 是线性 token 流，不是树结构，所以这里靠 nesting 计数
        手动配对开闭标签。这是整个渲染器里最关键的基础设施之一。
        """

        depth = 0
        for idx in range(start, len(tokens)):
            nesting = tokens[idx].nesting
            if nesting == 1:
                depth += 1
            elif nesting == -1:
                depth -= 1
                if depth == 0:
                    return idx
        return start

    def _attr(self, token: Token, name: str) -> Optional[str]:
        # markdown-it-py 的 token.attrGet 是首选接口；
        # 这里兼容直接 attrs 字典，避免不同版本细节差异导致崩溃。
        if hasattr(token, "attrGet"):
            return token.attrGet(name)
        attrs = getattr(token, "attrs", None) or {}
        return attrs.get(name)

    def _strip_html(self, text: str) -> str:
        return HTML_TAG_RE.sub("", text)

    def _display_width(self, text: str) -> int:
        # 终端对中英文宽度的占位不同，ASCII 表格必须用“显示宽度”算列宽。
        width = _wcswidth(text)
        return width if width > 0 else len(text)

    def _pad_display(self, text: str, width: int) -> str:
        padding = max(width - self._display_width(text), 0)
        return text + (" " * padding)

    def _prefix_lines(self, text: str, first_prefix: str, rest_prefix: str) -> str:
        # 给多行文本统一加前缀，常用于列表和引用。
        # 第一行和后续行前缀分开传，是为了让列表首行用 "- "，
        # 后续行则只做缩进对齐。
        lines = text.splitlines() or [""]
        prefixed: list[str] = []
        for idx, line in enumerate(lines):
            prefix = first_prefix if idx == 0 else rest_prefix
            prefixed.append(prefix + line if line else prefix.rstrip())
        return "\n".join(prefixed)

    def _normalize_output(self, text: str) -> str:
        # 最后收尾：去掉行尾空格，压缩过多空行，避免文本风格忽胖忽瘦。
        lines = [line.rstrip() for line in text.splitlines()]
        normalized = "\n".join(lines)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()
