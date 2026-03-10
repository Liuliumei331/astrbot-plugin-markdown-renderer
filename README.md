# markdown_renderer

`markdown_renderer` 是一个 AstrBot 插件，用于把 LLM 输出的 Markdown 渲染成更适合聊天平台展示的纯文本或 ASCII 风格文本，而不是简单删除语法。

仓库地址：

- https://github.com/Liuliumei331/astrbot-plugin-markdown-renderer

## 设计目标

- 不靠正则硬删全部 Markdown
- 先解析 Markdown 结构，再渲染为文本
- 支持两种输出模式：`plain` 和 `ascii`
- 对表格做专门处理，避免只剩下杂乱的 `|` 和 `---`

## 当前已实现

- 标题
- 段落
- 无序列表 / 有序列表
- 任务列表识别（`[x]` / `[ ]`）
- 引用
- 行内代码 / 代码块
- 链接
- 图片占位文本
- GFM 风格表格
- 水平分隔线
- 行内强调 / 加粗 / 删除线的文本语义保留
- 基础 HTML 标签剥离

当前默认语义样式：

- 斜体 `*text*` -> `「text」`
- 粗体 `**text**` -> `【text】`
- 删除线 `~~text~~` -> `已删除：text`
- 行内代码 `` `code` `` -> `<code>`
- 一级标题 `# title` -> `title` + 下方 `====`
- 二级标题 `## title` -> `title` + 下方 `----`
- 三级标题 `### title` -> `▎title`
- 四级标题 `#### title` -> `▹ title`
- 引用 `> quote` -> `❝ quote`

## 实机验证

当前版本已经在真实 AstrBot 对话链路里验证通过，以下能力已确认可用：

- 标题
- 斜体 / 粗体 / 删除线
- 链接
- 表格
- 任务列表
- 有序列表 / 无序列表 / 嵌套列表
- 引用
- 代码块
- 图片语法

## 输出示例

输入：

```md
# 今日结果

| 姓名 | 分数 |
| --- | --- |
| 张三 | 95 |

- [x] 完成
- [ ] 待办

> 需要继续跟进

访问 [官网](https://example.com)
```

`ascii` 模式输出：

```text
今日结果
========

+------+------+
| 姓名 | 分数 |
+------+------+
| 张三 | 95   |
+------+------+

[x] 完成
[ ] 待办

❝ 需要继续跟进

访问 官网 (https://example.com)
```

## 安装

1. 将插件目录放入 AstrBot 的 `data/plugins/` 下
2. 安装依赖 `markdown-it-py` 与 `wcwidth`
3. 重载或重启 AstrBot

如果你用 Docker 部署 AstrBot，依赖需要安装到 AstrBot 容器的 Python 环境里，而不是仅安装到本地开发 `.venv`。

## 兼容性说明

如果你同时启用了 `meme_manager`，请注意它的备用标记功能可能会误处理 Markdown 中的 `[]` 和 `()`，从而影响：

- 链接 `[text](url)`
- 任务列表 `- [x] item`
- 图片 `![alt](url)`

实机测试中，关闭 `meme_manager` 的 `remove_invalid_alternative_markup` 后可以正常共存。

## 本地开发环境

建议用 `uv` 单独建开发环境，但要注意一件事：

- 这个 `.venv` 只用于本地开发、调试和测试
- 插件真正上线时，依赖仍然需要安装到 AstrBot 实际运行的 Python 环境里
- 最稳的做法是让本地 `.venv` 使用和 AstrBot 运行时相同的大版本 Python

常用命令：

```bash
python3 -m uv venv .venv --python /path/to/astrbot/python
python3 -m uv sync
```

如果你暂时拿不到 AstrBot 的 Python 路径，也可以先用当前本地解释器创建 `.venv`，后续再重建。

## 配置项

- `enabled`: 是否启用插件
- `mode`: 文本模式，`ascii` 或 `plain`
- `table_mode`: 表格模式，`ascii` 或 `plain`
- `keep_links`: 是否保留链接 URL
- `keep_code_language`: 是否保留代码块语言名
- `preserve_inline_semantics`: 是否保留强调 / 加粗 / 删除线的文本语义
- `strip_html`: 是否剥离 HTML 标签
- `detect_markdown_only`: 仅在检测到 Markdown 特征时处理
- `debug_log`: 输出调试日志

## 后续建议

当前版本已经比“只删 Markdown 标记”的方案稳定，但如果你要继续增强，下一步最值得补的是：

- 更复杂的嵌套列表
- HTML 块的结构化降级
- 数学公式的保留策略
- 超宽表格的自动换行或截断

## License

当前仓库尚未单独添加开源许可证文件。如需公开发布，建议补充 `LICENSE`。
