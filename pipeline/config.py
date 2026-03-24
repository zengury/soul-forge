"""
family-soul pipeline configuration
===================================
修改这里以匹配你的微信导出数据。
"""

import os
from pathlib import Path

# ── 项目根目录 ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
PROMPTS_DIR = ROOT / "prompts"
OUTPUTS_DIR = ROOT / "outputs"

# ── 说话人映射 ────────────────────────────────────────────────────────────────
# key = 微信导出中的显示名 / 备注名
# role = dad / mom / son (管线内部使用)
# display = 输出文档中的称呼
SPEAKERS = {
    "nickname_dad":   {"role": "dad", "display": "爸爸"},
    "nickname_mom":   {"role": "mom", "display": "妈妈"},
    "nickname_child": {"role": "son", "display": "孩子"},
}

# 家庭介绍（用于 synthesis prompt 的背景）
FAMILY_CONTEXT = """
（在此填写家庭背景，供 LLM 合成时参考）
"""

# 孩子背景（用于 persona prompt）
CHILD_CONTEXT = """
（在此填写孩子的背景信息，如年龄、求学情况等）
"""

# ── 微信导出格式 ──────────────────────────────────────────────────────────────
# 支持格式：
#   "wechatmsg_csv"  - WeChatMsg / wxdump 导出的 CSV
#                      列名：MsgSvrID, type_name, is_sender, talker, room_name, msg, CreateTime
#   "txt_standard"   - 微信官方/第三方 TXT 格式：
#                      每条消息以 "YYYY-MM-DD HH:MM:SS 发送者:" 开头
#   "json"           - 自定义 JSON 数组，每条消息含 timestamp/sender/content 字段
EXPORT_FORMAT = "weflow"

# CSV 导出时的列名映射（如和默认不同，在这里修改）
CSV_COLUMNS = {
    "timestamp": "CreateTime",   # 或 "CreateTime"（Unix timestamp）
    "sender":    "talker",       # 发送者
    "content":   "msg",          # 消息内容
    "type":      "type_name",    # 消息类型（Text / Image / ...）
}

# ── LLM 模型选择 ──────────────────────────────────────────────────────────────
# 阶段3（批量提取）：用 haiku 降低成本
EXTRACT_MODEL = "claude-haiku-4-5"
# 阶段4（合成）：用 opus 保证质量
SYNTHESIZE_MODEL = "claude-opus-4-5"

# ── 管线参数 ──────────────────────────────────────────────────────────────────
# 去噪：忽略少于这个字符数的消息
MIN_MSG_LENGTH = 4

# 去噪：对话分段时间窗口（分钟）
CONVERSATION_GAP_MINUTES = 30

# 去噪：过滤掉这些消息类型
SKIP_MSG_TYPES = {
    # WeFlow 格式类型名
    "图片消息", "语音消息", "视频消息", "动画表情", "系统消息", "位置消息", "名片消息",
    # 其他消息（转账/红包等系统事件，sender 是 chatroom 本身）
    "其他消息",
    # 兼容旧格式
    "Image", "Video", "Voice", "File", "Sticker", "Emoji",
    "图片", "视频", "语音", "文件", "表情", "小程序", "视频号",
}

# 提取：每个 LLM 请求处理的最大对话轮数
CHUNK_SIZE_TURNS = 40

# 提取：每次批量请求最多并发多少个（Batches API 限制 100k/批）
BATCH_SIZE = 200

# ── Anthropic API ─────────────────────────────────────────────────────────────
# Mac GUI 应用（如 OpenClaw）不继承 shell 环境变量，
# 因此依次从以下位置读取 API key：
#   1. 环境变量 ANTHROPIC_API_KEY（终端直接运行时有效）
#   2. ~/.openclaw/workspace/.env
#   3. ~/.env
def _load_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    for env_path in [
        Path.home() / ".openclaw" / "workspace" / ".env",
        Path.home() / ".env",
        Path(__file__).parent.parent / ".env",
    ]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    return ""

ANTHROPIC_API_KEY = _load_api_key()
