#!/usr/bin/env python3
"""
soul-forge agent-loop runner

Agent 通过这个脚本做所有文件 I/O，自己用配置好的模型做 LLM 工作。
不需要额外配置 API key——所有 LLM 调用由 OpenClaw agent 自己完成。
"""

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict

SKILL_DIR = Path(__file__).parent.parent
PIPELINE_DIR = SKILL_DIR / "pipeline"
PROMPTS_DIR = SKILL_DIR / "prompts"
sys.path.insert(0, str(PIPELINE_DIR))

BATCH_SIZE = 20


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

def get_next_batch(config: dict):
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

    batch = pending[:BATCH_SIZE]
    total = len(all_chunks)
    done = len(done_ids)
    batch_num = done // BATCH_SIZE + 1
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    print(f"[BATCH:{batch_num}/{total_batches}]")
    print(f"[PROGRESS:{done}/{total}]")
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
    print("请按照上面的 prompt 分析这批对话块，输出 JSON 数组，每个元素对应一个 chunk_id。")
    print(f"完成后调用：python3 {__file__} --stage 3 --save-batch --config {config.get('_path','')} --result '<JSON>'")


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
    args = parser.parse_args()

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
            get_next_batch(config)
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
