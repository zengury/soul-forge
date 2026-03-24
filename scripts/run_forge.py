#!/usr/bin/env python3
"""
soul-forge agent-loop runner

Agent 通过这个脚本做所有文件 I/O，自己用配置好的模型做 LLM 工作。
不需要额外配置 API key——所有 LLM 调用由 OpenClaw agent 自己完成。
"""

import argparse
import json
import sys
import time
from pathlib import Path
from collections import defaultdict

SKILL_DIR = Path(__file__).parent.parent
PIPELINE_DIR = SKILL_DIR / "pipeline"
PROMPTS_DIR = SKILL_DIR / "prompts"
sys.path.insert(0, str(PIPELINE_DIR))

BATCH_SIZE = 20
DEFAULT_BATCH_DELAY = 3   # 每批之间默认等待秒数
DEFAULT_MAX_BATCHES = 3   # 默认每次运行处理批数（限速模式）


def load_config(config_path: str) -> dict:
    p = Path(config_path).expanduser()
    if not p.exists():
        print(f"[ERROR:配置文件不存在：{config_path}]")
        sys.exit(1)
    return json.loads(p.read_text())


def get_output_dir(config: dict) -> Path:
    return Path(config["output_dir"]).expanduser()


def get_data_dir(config: dict) -> Path:
    return get_output_dir(config) / "data"


def load_state(config: dict) -> dict:
    state_file = get_output_dir(config) / ".forge_state.json"
    if state_file.exists():
        return json.loads(state_file.read_text())
    return {"stage": 0, "chunks_total": 0, "chunks_done": 0}


def save_state(config: dict, state: dict):
    state_file = get_output_dir(config) / ".forge_state.json"
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))


# ── 阶段 1 ────────────────────────────────────────────────────────────────────

def run_stage1(config: dict):
    import subprocess
    data_dir = get_data_dir(config)
    data_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [sys.executable, str(PIPELINE_DIR / "01_parse.py"),
         "--input", config["input_file"],
         "--output", str(data_dir / "messages.jsonl"),
         "--format", config.get("format", "weflow"),
         "--members", json.dumps(config.get("members", {}))],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[ERROR:{result.stderr.strip()}]")
        sys.exit(1)
    count = sum(1 for _ in (data_dir / "messages.jsonl").open())
    print(f"[STAGE:1:DONE] 解析完成，共 {count} 条消息")


# ── 阶段 2 ────────────────────────────────────────────────────────────────────

def run_stage2(config: dict):
    import subprocess
    data_dir = get_data_dir(config)

    result = subprocess.run(
        [sys.executable, str(PIPELINE_DIR / "02_denoise.py"),
         "--input", str(data_dir / "messages.jsonl"),
         "--output", str(data_dir / "chunks.jsonl")],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[ERROR:{result.stderr.strip()}]")
        sys.exit(1)

    chunks = [json.loads(l) for l in (data_dir / "chunks.jsonl").open()]
    state = load_state(config)
    state["stage"] = 2
    state["chunks_total"] = len(chunks)
    save_state(config, state)
    print(f"[STAGE:2:DONE] 分块完成，共 {len(chunks)} 个对话块")


# ── 阶段 3：获取下一批 ────────────────────────────────────────────────────────

def get_next_batch(config: dict, max_batches: int = 0, delay_seconds: int = 0):
    """
    max_batches: 本次最多处理几批（0=不限制，由 agent 自行决定何时停止）
    delay_seconds: 批次之间等待秒数（用于限速）
    """
    data_dir = get_data_dir(config)
    obs_file = data_dir / "observations.jsonl"

    done_ids = set()
    if obs_file.exists():
        for line in obs_file.open():
            try:
                done_ids.add(json.loads(line)["chunk_id"])
            except Exception:
                pass

    all_chunks = []
    for line in (data_dir / "chunks.jsonl").open():
        try:
            all_chunks.append(json.loads(line))
        except Exception:
            pass

    pending = [c for c in all_chunks if c["chunk_id"] not in done_ids]

    if not pending:
        print("[BATCH:DONE]")
        return

    total = len(all_chunks)
    done = len(done_ids)
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    batch_num = done // BATCH_SIZE + 1

    # 限速模式：只输出 max_batches 批
    if max_batches > 0:
        remaining_tonight = total_batches - (done // BATCH_SIZE)
        will_do = min(max_batches, remaining_tonight)
        eta_hours = (total_batches - done // BATCH_SIZE) // max_batches + 1 if max_batches else 0
        print(f"[RATE_LIMIT_MODE] 本次处理 {will_do} 批，预计需要约 {eta_hours} 小时全部完成")
        print(f"[SCHEDULE_HINT] 建议在午夜后每小时自动运行一次，每次处理 {max_batches} 批")
        print()

    batch = pending[:BATCH_SIZE]
    print(f"[BATCH:{batch_num}/{total_batches}]")
    print(f"[PROGRESS:{done}/{total}]")

    if delay_seconds > 0:
        print(f"[DELAY:{delay_seconds}s] 批次间将等待 {delay_seconds} 秒以避免触发 rate limit")
    print()

    for chunk in batch:
        print(f"--- chunk-{chunk['chunk_id']} ({chunk.get('time_range', '')}) ---")
        for msg in chunk.get("messages", []):
            role = msg.get("display", msg.get("sender", "?"))
            print(f"{role}: {msg.get('content', '')}")
        print()

    prompt_text = (PROMPTS_DIR / "extract_patterns.md").read_text()
    print("=== 提取 Prompt ===")
    print(prompt_text)
    print()

    # 构建下一步调用命令（含限速参数）
    rate_flags = ""
    if max_batches > 0:
        rate_flags += f" --max-batches {max_batches}"
    if delay_seconds > 0:
        rate_flags += f" --delay {delay_seconds}"

    print("请按照上面的 prompt 分析这批对话块，输出 JSON 数组，每个元素对应一个 chunk_id。")
    print(f"完成后调用：python3 {__file__} --stage 3 --save-batch --config {config.get('_path','')} --result '<JSON>'")
    if max_batches > 0:
        print()
        print(f"[NEXT_BATCH_CMD] 保存完成后继续下一批（还剩 {len(pending) - BATCH_SIZE} 个块）：")
        print(f"  python3 {__file__} --stage 3 --next-batch --config {config.get('_path','')}{rate_flags}")


# ── 阶段 3：保存批次结果 ──────────────────────────────────────────────────────

def save_batch(config: dict, result_json: str):
    data_dir = get_data_dir(config)
    obs_file = data_dir / "observations.jsonl"

    try:
        observations = json.loads(result_json)
        if isinstance(observations, dict):
            observations = [observations]
    except json.JSONDecodeError as e:
        print(f"[ERROR:JSON解析失败：{e}]")
        sys.exit(1)

    saved = 0
    with obs_file.open("a", encoding="utf-8") as f:
        for obs in observations:
            if obs.get("has_signal", True):
                f.write(json.dumps(obs, ensure_ascii=False) + "\n")
                saved += 1

    done_ids = set()
    for line in obs_file.open():
        try:
            done_ids.add(json.loads(line)["chunk_id"])
        except Exception:
            pass
    total = sum(1 for _ in (data_dir / "chunks.jsonl").open())

    print(f"[BATCH:SAVED] 保存 {saved} 条有信号观察")
    print(f"[PROGRESS:{len(done_ids)}/{total}]")


# ── 阶段 4：加载观察记录 ──────────────────────────────────────────────────────

def load_observations(config: dict):
    data_dir = get_data_dir(config)
    obs_file = data_dir / "observations.jsonl"

    if not obs_file.exists():
        print("[ERROR:observations.jsonl 不存在，请先完成阶段3]")
        sys.exit(1)

    observations = []
    for line in obs_file.open():
        try:
            observations.append(json.loads(line))
        except Exception:
            pass

    print(f"[OBSERVATIONS:共 {len(observations)} 条观察记录]")
    print()

    by_member = defaultdict(list)
    collective = []

    for obs in observations:
        o = obs.get("observations", {})
        if not o:
            continue
        lang = o.get("language", {})
        for role in ["dad", "mom", "child"]:
            if lang.get(role):
                by_member[role].append({
                    "time": obs.get("time_range", ""),
                    "language": lang[role],
                    "emotional": o.get("emotional_patterns", ""),
                    "values": o.get("values", ""),
                })
        collective.append({
            "time": obs.get("time_range", ""),
            "relational": o.get("relational_dynamics", ""),
            "collective": o.get("collective_identity", ""),
        })
        for q in obs.get("notable_quotes", []) or []:
            if q:
                by_member[q.get("role", "?")].append({"quote": q})

    print("=== 集体观察（用于生成 soul.md）===")
    for item in collective[:80]:
        print(f"[{item['time']}] 关系：{item['relational'][:120]}")
        print(f"  集体：{item['collective'][:120]}")
    print()

    for role, items in by_member.items():
        print(f"=== {role} 观察（用于生成 persona_{role}.md）===")
        for item in items[:40]:
            if "quote" in item:
                print(f"  名言：{item['quote']}")
            else:
                print(f"  [{item['time']}] {item.get('language','')[:120]}")
        print()

    soul_prompt = (PROMPTS_DIR / "synthesize_soul.md").read_text()
    print("=== soul.md 综合 Prompt ===")
    print(soul_prompt)
    print()
    print(f"完成后调用：python3 {__file__} --stage 4 --save --file soul.md --config ... --content '<内容>'")
    print(f"然后依次为每个成员生成 persona，使用：{PROMPTS_DIR / 'synthesize_persona.md'}")


# ── 阶段 4：保存输出文件 ──────────────────────────────────────────────────────

def save_output_file(config: dict, filename: str, content: str):
    output_dir = get_output_dir(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename
    out_path.write_text(content, encoding="utf-8")
    print(f"[OUTPUT:{out_path}] 已保存 {len(content)} 字符")


# ── 状态查询 ──────────────────────────────────────────────────────────────────

def show_status(config: dict):
    data_dir = get_data_dir(config)
    output_dir = get_output_dir(config)

    print("=== soul-forge 状态 ===")
    print(f"输入：{config.get('input_file','未设置')}")
    print(f"输出：{output_dir}")
    print()

    chunks_file = data_dir / "chunks.jsonl"
    if not chunks_file.exists():
        print("阶段1-2：未完成")
        return

    total = sum(1 for _ in chunks_file.open())
    print(f"对话块：{total} 个")

    obs_file = data_dir / "observations.jsonl"
    if obs_file.exists():
        done = sum(1 for _ in obs_file.open())
        pct = done * 100 // total if total else 0
        print(f"已提取：{done}/{total} 块（{pct}%）")
    else:
        print("阶段3：未开始")

    for fname in ["soul.md", "persona_dad.md", "persona_mom.md", "persona_child.md"]:
        f = output_dir / fname
        status = f"✓ ({f.stat().st_size} 字节)" if f.exists() else "✗ 未生成"
        print(f"  {fname}: {status}")


# ── 调度建议 ──────────────────────────────────────────────────────────────────

def print_schedule_guide(config_path: str, max_batches: int):
    """
    输出分时运行建议，帮助用户避免触发 rate limit。
    不依赖 config 文件是否存在。
    """
    script = Path(__file__).resolve()
    print("""
=== soul-forge 分时运行方案（避免 Rate Limit）===

原理：每次只处理少量批次，然后停止。
      下次运行时自动从断点继续，不重复处理。

推荐设置：
  每批 20 个对话块，每次运行 {max_batches} 批（{chunk_num} 个块）
  批次间等待 10 秒，降低单位时间 token 消耗

─────────────────────────────────────────────────────

【方案 A：手动分次运行（最简单）】

每次在 OpenClaw 里说："soul-forge 处理下一批"
Agent 会自动处理 {max_batches} 批后停止，进度自动保存。

─────────────────────────────────────────────────────

【方案 B：Mac 定时任务（推荐，全自动）】

在终端执行以下命令，设置每小时运行一次（凌晨1点-7点）：

  crontab -e

添加以下行：

  0 1-7 * * * openclaw run "{script}" --stage 3 --next-batch --config {config_path} --max-batches {max_batches} --delay 10

或者直接调用脚本（如果 OpenClaw 在终端可用）：

  0 1-7 * * * /usr/bin/python3 "{script}" --stage 3 --next-batch --config {config_path} --max-batches {max_batches} --delay 10

─────────────────────────────────────────────────────

【方案 C：告诉 agent 用定时模式】

在 OpenClaw 中说：
  "soul-forge 每小时处理 {max_batches} 批，今晚午夜开始"

Agent 会自动设置 OpenClaw 的定时任务。

─────────────────────────────────────────────────────

当前建议参数（基于 20块/批）：
  --max-batches {max_batches}   每次处理约 {chunk_num} 个对话块
  --delay 10                    批次间等 10 秒

完成进度查看：
  python3 "{script}" --status --config {config_path}
""".format(
        max_batches=max_batches,
        chunk_num=max_batches * BATCH_SIZE,
        script=script,
        config_path=config_path,
    ))


# ── 主入口 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=int, choices=[1, 2, 3, 4])
    parser.add_argument("--config", required=False)
    parser.add_argument("--next-batch", action="store_true")
    parser.add_argument("--save-batch", action="store_true")
    parser.add_argument("--load-observations", action="store_true")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--file", type=str)
    parser.add_argument("--result", type=str)
    parser.add_argument("--content", type=str)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--schedule", action="store_true",
                        help="输出 cron 配置，用于午夜自动分时运行")
    parser.add_argument("--max-batches", type=int, default=0,
                        help="每次运行最多处理几批（0=不限制，建议限速时设为3-5）")
    parser.add_argument("--delay", type=int, default=0,
                        help="批次之间等待秒数（建议限速时设为 10-30）")
    args = parser.parse_args()

    if args.schedule:
        # 不需要 config，直接输出调度建议
        print_schedule_guide(args.config or "~/.forge_config.json",
                             args.max_batches or DEFAULT_MAX_BATCHES)
        return

    if not args.config:
        print("[ERROR:请提供 --config 参数]")
        sys.exit(1)

    config = load_config(args.config)
    config["_path"] = args.config

    if args.status:
        show_status(config)
    elif args.stage == 1:
        run_stage1(config)
    elif args.stage == 2:
        run_stage2(config)
    elif args.stage == 3:
        if args.next_batch:
            get_next_batch(config,
                           max_batches=args.max_batches,
                           delay_seconds=args.delay)
        elif args.save_batch:
            if not args.result:
                print("[ERROR:--save-batch 需要 --result 参数]")
                sys.exit(1)
            save_batch(config, args.result)
    elif args.stage == 4:
        if args.load_observations:
            load_observations(config)
        elif args.save:
            if not args.file or not args.content:
                print("[ERROR:--save 需要 --file 和 --content]")
                sys.exit(1)
            save_output_file(config, args.file, args.content)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
