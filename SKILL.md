---
name: soul-forge
version: 2.0.0
description: >
  从家庭/团队群聊记录提炼数字人格。
  输出 soul.md（集体人格）+ 每位成员的 persona 文件，可直接用于 AI agent 的人格底座。
  关键词：群聊分析、家庭人格、soul、persona、数字人格、聊天记录、微信导出、人格提炼。
author: zengury
requires:
  - python3
---

# SKILL: Soul Forge — 家庭数字人格提炼

这个 skill 把一份群聊记录变成可用于 AI agent 的人格文件。
**不需要额外配置任何 API key**——所有 LLM 工作由当前 agent 使用自己的模型完成。

---

## 触发条件

- 用户说"帮我分析聊天记录"、"生成 soul 文件"、"提炼人格"
- 用户提供了 `.json` / `.csv` 聊天导出文件路径
- 用户说"运行 soul-forge"

---

## 架构说明

```
阶段 1-2：Python 脚本（数据处理，无需 LLM）
阶段 3：  Agent 循环处理（用当前配置的模型提取行为模式）
阶段 4：  Agent 一次性综合（用当前配置的模型生成 soul + persona）
```

无论用户配置的是 Claude、Kimi、Qwen 还是本地模型，soul-forge 都能工作。

---

## 执行流程

### 第一步：确认输入

询问用户：
1. 聊天记录文件路径
2. 输出目录（默认：`~/soul-forge-output/`）
3. 成员角色配置（谁是 dad / mom / child，或自定义角色名）

把配置写入 `{output_dir}/.forge_config.json`：
```json
{
  "input_file": "/path/to/chat.json",
  "output_dir": "~/soul-forge-output",
  "members": {
    "微信昵称A": {"role": "dad", "display": "爸爸"},
    "微信昵称B": {"role": "mom", "display": "妈妈"},
    "微信昵称C": {"role": "child", "display": "孩子"}
  }
}
```

### 第二步：阶段 1-2（脚本处理，30秒-1分钟）

```bash
python3 {SKILL_DIR}/scripts/run_forge.py --stage 1 --config {config_path}
python3 {SKILL_DIR}/scripts/run_forge.py --stage 2 --config {config_path}
```

完成后会生成：
- `{output_dir}/data/messages.jsonl` — 标准化消息
- `{output_dir}/data/chunks.jsonl` — 按时间分割的对话块

告知用户："✓ 数据处理完成，共 N 个对话块，开始分析…"

### 第三步：阶段 3（Agent 提取行为模式）

读取提取 prompt：
```bash
python3 {SKILL_DIR}/scripts/run_forge.py --stage 3 --next-batch --config {config_path}
```

该命令返回一批（约20个）未处理的对话块，格式：
```
[BATCH:1/25]
--- chunk-1 (2021-03-01) ---
妈妈: 今天做了红烧肉
爸爸: 闻到了
孩子: 我要吃！
--- chunk-2 (2021-03-02) ---
...
[PROMPT_FILE:{SKILL_DIR}/prompts/extract_patterns.md]
```

**Agent 动作**：
1. 读取 `[PROMPT_FILE]` 里的提取 prompt
2. 对这批对话块进行分析，按 prompt 要求输出结构化 JSON
3. 调用保存命令：
```bash
python3 {SKILL_DIR}/scripts/run_forge.py --stage 3 --save-batch --config {config_path} --result '{JSON输出}'
```
4. 重复，直到命令返回 `[BATCH:DONE]`

进度汇报格式：`"已处理 X/N 批（每批约20个对话块）"`

### 第四步：阶段 4（Agent 综合生成）

```bash
python3 {SKILL_DIR}/scripts/run_forge.py --stage 4 --load-observations --config {config_path}
```

该命令返回所有提取的观察记录（分组摘要形式）。

**Agent 动作**：
1. 读取 `{SKILL_DIR}/prompts/synthesize_soul.md`，生成 soul.md 内容
2. 调用保存：
```bash
python3 {SKILL_DIR}/scripts/run_forge.py --stage 4 --save --file soul.md --config {config_path}
```
3. 依次为每个成员读取 `{SKILL_DIR}/prompts/synthesize_persona.md`，生成 persona 内容
4. 调用保存

### 第五步：完成

输出文件清单，询问用户是否要将 soul.md 安装为当前 agent 的 SOUL.md。

---

## 进阶选项

| 用户说 | 动作 |
|--------|------|
| "只更新 soul" | 跳过阶段 3，直接从已有观察记录重新综合 soul.md |
| "只刷新 persona" | 跳过阶段 3，重新综合各 persona |
| "继续上次的任务" | 检查进度，从上次中断的批次继续 |
| "soul-forge 状态" | 显示当前进度和已处理的块数 |
| "soul-forge 分时运行" | 获取避免 rate limit 的调度方案 |

---

## Rate Limit 处理：分时运行

**背景**：阶段3需要处理大量对话块，密集调用模型可能触发 rate limit。

**建议方案：** 告诉 agent：

```
soul-forge 用分时模式处理，每小时 3 批，今晚开始
```

Agent 会执行：
```bash
python3 {SKILL_DIR}/scripts/run_forge.py --stage 3 --next-batch \
  --config {config_path} --max-batches 3 --delay 10
```

- `--max-batches 3`：每次只处理 3 批（60 个对话块），然后停止
- `--delay 10`：每批之间等 10 秒
- 每次运行后进度自动保存，下次从断点继续，**不重复处理**

**获取完整调度方案**（含 cron 配置）：
```bash
python3 {SKILL_DIR}/scripts/run_forge.py --schedule --config {config_path} --max-batches 3
```

**人工分次模式**：每次在 OpenClaw 说"处理下一批"，agent 处理 3 批后停止，用户可随时继续。

---

## 输出文件

```
soul-forge-output/
├── soul.md              ← 集体人格，可直接作为 agent SOUL.md 使用
├── persona_dad.md
├── persona_mom.md
├── persona_child.md
└── data/                ← 中间数据（可删除）
    ├── messages.jsonl
    ├── chunks.jsonl
    └── observations.jsonl
```

---

## 方法论

基于**数字民族志**（Digital Ethnography）：

- 阶段1-2：田野记录整理（去噪、结构化原始数据）
- 阶段3：系统性观察（提取五维度行为模式：语言/情感/价值观/关系/集体人格）
- 阶段4：民族志分析（综合「厚描」——不是行为清单，而是解释框架）

> Clifford Geertz：「浅描记录行为，厚描解释意义。」
