# markdown_renderer

`markdown_renderer` 是一个 AstrBot 插件，用于将 LLM 输出中的 Markdown 渲染为更适合聊天平台展示的文本内容。

仓库地址：<https://github.com/Liuliumei331/astrbot-plugin-markdown-renderer>

## 特性

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

## 渲染风格

默认提供两种模式：

- `ascii`：保留较强的结构感，适合表格、标题、代码块和引用
- `plain`：输出更轻量的纯文本结果

当前默认样式：

- 斜体 `*text*` -> `「text」`
- 粗体 `**text**` -> `『text』`
- 删除线 `~~text~~` -> `已删除：text`
- 行内代码 `` `code` `` -> `<code>`
- 一级标题 `# title` -> `● title`
- 二级标题 `## title` -> `◆ title`
- 三级标题 `### title` -> `▹ title`
- 四级标题 `#### title` -> `▹ title`
- 引用 `> quote` -> `❝ quote`

表格规则：

- 宽度不超过 `45` 时，`ascii` 模式输出 ASCII 表格
- 宽度超过 `45` 时，自动降级为卡片式字段视图，避免手机端换行错位

## 输出示例

输入 Markdown：

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
● 今日结果

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

宽表格示例：

```md
| 姓名 | 分数 | 备注 |
| --- | --- | --- |
| 张三 | 95 | 已完成第一阶段验证，需要继续观察后续表现 |
```

渲染结果：

```text
[1]
姓名：张三
分数：95
备注：已完成第一阶段验证，需要继续观察后续表现
```

## 安装

1. 将插件目录放入 AstrBot 的 `data/plugins/` 下
2. 安装依赖 `markdown-it-py` 与 `wcwidth`
3. 重载或重启 AstrBot

Docker 部署时，依赖需要安装到 AstrBot 容器内的 Python 环境，而不是本地开发 `.venv`。

## 运行说明

- 插件默认只在检测到 Markdown 特征时处理文本
- 插件会直接改写 `LLMResponse.completion_text`
- 对于普通纯文本回复，通常不会触发重渲染

## 兼容性说明

如果同时启用了 `meme_manager`，其备用标记功能可能会误处理 Markdown 中的 `[]` 和 `()`，从而影响：

- 链接 `[text](url)`
- 任务列表 `- [x] item`
- 图片 `![alt](url)`

建议关闭 `meme_manager` 的 `remove_invalid_alternative_markup`。

## 本地开发环境

建议使用 `uv` 管理本地开发环境：

```bash
python3 -m uv venv .venv --python /path/to/astrbot/python
python3 -m uv sync
```

本地 `.venv` 仅用于开发和测试。部署时仍需将依赖安装到 AstrBot 实际运行的 Python 环境中。

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

## 已验证能力

- 标题
- 斜体 / 粗体 / 删除线
- 行内代码 / 代码块
- 链接
- 表格
- 任务列表
- 有序列表 / 无序列表 / 嵌套列表
- 引用
- 图片语法

## 后续计划

- 更复杂的嵌套列表
- HTML 块的结构化降级
- 数学公式的保留策略
- 更细粒度的表格降级策略

## License

MIT
