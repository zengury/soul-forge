# soul-forge

> 从群聊记录提炼数字人格。一份聊天导出 → soul.md + 每位成员的 persona 文件。

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
```

无需额外安装依赖，仅需 Python 3.9+（系统自带）。

## 使用

在 OpenClaw 对话中说：

```
帮我分析这份聊天记录：/path/to/chat_export.json
```

或：

```
soul-forge 运行 ~/Downloads/wechat_export.json
```

Agent 会自动处理四个阶段，完成后输出：

```
soul-forge-output/
├── soul.md            ← 集体人格，可直接作为 AI agent 的 SOUL.md 使用
├── persona_A.md       ← 成员 A 的个人人格
├── persona_B.md       ← 成员 B 的个人人格
└── persona_C.md       ← 成员 C 的个人人格
```

## 进阶用法

```
soul-forge 只更新 soul          # 跳过提取，直接重新综合 soul.md
soul-forge 只刷新 persona       # 跳过提取，重新生成各成员 persona
soul-forge 继续上次的任务        # 断点续跑，不重复处理已完成的部分
soul-forge 状态                 # 查看当前进度
soul-forge 分时运行             # 获取避免 rate limit 的调度方案
```

## 需要什么

- Python 3.9+（通常已安装）
- OpenClaw（使用你已经配置好的模型，无需额外 API key）
- 群聊 JSON 或 CSV 导出文件

## 支持格式

| 格式 | 来源 |
|------|------|
| 微信 WeFlow JSON | WeFlow 工具 → 选群聊 → 导出 JSON |
| 标准 CSV | 需含 sender / timestamp / content 列 |

## 方法论

基于**数字民族志**（Digital Ethnography）：

- **阶段 1-2**：田野记录整理 — 解析原始聊天，去噪，按时间分段
- **阶段 3**：系统性观察 — OpenClaw 对每段对话提取五维度行为模式（语言风格、情感模式、价值观信号、关系动态、集体身份）
- **阶段 4**：民族志分析 — OpenClaw 综合所有观察，生成「厚描」式人格档案

> Clifford Geertz：「浅描记录行为，厚描解释意义。」

soul.md 不是行为清单，而是理解这个群体需要什么样的解释框架。

---

作者：[@zengury](https://github.com/zengury)
License: MIT
