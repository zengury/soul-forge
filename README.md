# soul-forge

> 从家庭群聊记录提炼数字人格。一份聊天导出 → soul.md + persona 文件集。

## 快速安装

### 方法一：ClawHub（推荐）

在 OpenClaw 中说：
```
安装 skill soul-forge
```

### 方法二：手动安装

```bash
# 如已安装旧版本先删除
rm -rf ~/.openclaw/workspace/skills/soul-forge

# 克隆到 OpenClaw skills 目录
git clone https://github.com/zengury/soul-forge ~/.openclaw/workspace/skills/soul-forge

# 安装 Python 依赖（Mac 用 pip3）
pip3 install -r ~/.openclaw/workspace/skills/soul-forge/requirements.txt
```

## 使用

在 OpenClaw 对话中说：

```
帮我分析这份聊天记录：/path/to/群聊_三头怪.json
```

或：

```
soul-forge 运行 ~/Downloads/wechat_export.json
```

Agent 会自动处理四个阶段，完成后输出：

```
soul-forge-output/
├── soul.md          ← AI agent 人格底座
├── persona_dad.md
├── persona_mom.md
└── persona_child.md
```

## 进阶用法

```
soul-forge 只更新 soul         # --soul-only：跳过 persona
soul-forge 只刷新 persona      # --persona-only：跳过 soul
soul-forge 继续上次的任务       # --resume：断点续跑，不重复计费
soul-forge 状态                # --status：查看当前进度
```

## 需要什么

- Python 3.9+
- `ANTHROPIC_API_KEY` 环境变量（需要 Claude API 权限）
- 微信群聊 JSON 导出（Mac 用 WeFlow 工具导出）

## 成本估算

一份 2-3 年群聊（约 500 对话块）：**$3-6 一次性**

- 阶段 3（Haiku Batches API）：约 $0.5-1
- 阶段 4（Opus 综合）：约 $2-5

## 支持格式

| 格式 | 来源 |
|------|------|
| 微信 WeFlow JSON | WeFlow 工具 → 选群聊 → 导出 JSON |
| 标准 CSV | 需含 sender / timestamp / content 列 |

## 方法论

基于**数字民族志**（Digital Ethnography）：

- 阶段 1-2：田野记录整理（结构化原始数据）
- 阶段 3：系统观察（Haiku 提取五维度行为模式）
- 阶段 4：民族志分析（Opus 综合「厚描」）

> Clifford Geertz：「浅描记录行为，厚描解释意义。」

soul.md 不是行为清单，而是理解这个家庭需要什么样的解释框架。

---

作者：[@zengury](https://github.com/zengury)
License: MIT
