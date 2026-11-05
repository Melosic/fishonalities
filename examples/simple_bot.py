#!/usr/bin/env python3
"""最小可跑的机器人样板：把人格卡接进对话，按场合决定怎么说话。

这不是一个完整的产品，是一个「该怎么用」的样板。它演示的不是「怎么调 API」——
那个谁都会——而是**接了之后怎么才不像个客服**：

- 群聊和私聊用两套规矩（人格卡的 `channel` 字段说了算）
- 回复前先等一会儿，等多久看场合和字数（群里有上限，超了这轮就别接）
- 私聊记得住对方说过的事
- 对话上下文只留最近若干条，多了人设会被别人的口癖带跑
- temperature 用人格卡里写的那个

用法：
    export FAT_FISH_API_KEY=sk-xxx
    python3 examples/simple_bot.py gou-dan            # 场合跟着卡的 channel 走
    python3 examples/simple_bot.py xiao-geng          # 私聊卡 → 私聊模式
    python3 examples/simple_bot.py gou-dan --group    # 强制模拟群聊
    python3 examples/simple_bot.py xiao-geng --no-delay --no-memory   # 快速试跑

生产环境请换成真正的平台适配（NapCat / AstrBot / telegram-bot 等），
这个脚本负责演示「接法和参数怎么定」。
"""

import json
import os
import random
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROMPT_DIR = ROOT / "dist" / "prompts"
INDEX_JSON = ROOT / "dist" / "index.json"

# 让脚本能找到同目录的 memory.py
sys.path.insert(0, str(HERE))
try:
    from memory import Memory, append_to_prompt  # noqa: E402
except ImportError:  # 单独拷走这个文件也能跑
    Memory = None  # type: ignore[assignment]
    append_to_prompt = None  # type: ignore[assignment]

API_KEY = os.environ.get("FAT_FISH_API_KEY", "")
BASE_URL = os.environ.get("FAT_FISH_BASE_URL", "https://api.deepseek.com").rstrip("/")
MODEL = os.environ.get("FAT_FISH_MODEL", "deepseek-chat")

# 群聊：话短、别碎嘴、被叫到才必回
GROUP_MAX_TOKENS = 200
GROUP_REPLY_PROBABILITY = 0.35
GROUP_COOLDOWN = 8.0

# 私聊：可以多说一句，但也不是每条都得应
PRIVATE_MAX_TOKENS = 320

HISTORY_LIMIT = 20  # 带太多它会把别人的口癖学过去，人设会糊


# ---- 读人格卡 -------------------------------------------------------------

def load_persona(persona_id: str) -> Dict:
    """从构建产物里读这张卡的 channel / temperature / name。"""
    if not INDEX_JSON.is_file():
        raise SystemExit(f"找不到 {INDEX_JSON}\n先跑：python3 tools/build.py")
    index = json.loads(INDEX_JSON.read_text(encoding="utf-8"))
    for item in index.get("personas", []):
        if item.get("id") == persona_id:
            return item
    raise SystemExit(f"没有这张卡：{persona_id}\n看看 dist/INDEX.md 里都有谁")


def load_prompt(persona_id: str) -> str:
    path = PROMPT_DIR / f"{persona_id}.md"
    if not path.exists():
        raise SystemExit(f"找不到 {path}\n先跑：python3 tools/build.py")
    return path.read_text(encoding="utf-8")


def name_from_prompt(system: str, fallback: str) -> str:
    """prompt 首行固定是「# 你现在是 <名字>」，从那儿捞名字，用来判断有没有人叫它。"""
    for line in system.splitlines():
        if line.startswith("# 你现在是"):
            return line.split("是", 1)[1].strip("。 \n") or fallback
    return fallback


# ---- 该不该说话、什么时候说 ----------------------------------------------

def think_then_reply(text: str, *, group: bool, hot: bool = False) -> Optional[float]:
    """返回该等几秒；返回 None 表示这一轮干脆别接。

    群聊和私聊不是一个算法：群里有人在等接话，超过几秒就不自然了；
    私聊里隔半小时回一条才是常态。
    """
    if group:
        # 群里超过 6 秒就别回了——晚到的回复比不回更怪
        base = min(1.5 + len(text) * 0.06, 4.0)
        ceiling = 6.0
    else:
        base = min(2.5 + len(text) * 0.12, 9.0)
        ceiling = 25.0

    delay = min(base * random.uniform(0.7, 1.6), ceiling)

    if group and hot:
        delay *= 0.6

    # 私聊偶尔慢得离谱：真人在忙、在上厕所、在洗澡
    if not group and random.random() < 0.05:
        delay = random.uniform(20.0, 60.0)

    if group and delay >= ceiling:
        return None  # 群里等太久，这轮别接了
    return delay


def should_reply(text: str, name: str, group: bool) -> bool:
    """被叫名字必回；群里没被叫时按概率接话，私聊基本都接。"""
    if name and name in text:
        return True
    if group:
        return random.random() < GROUP_REPLY_PROBABILITY
    return True


# ---- 调模型 ---------------------------------------------------------------

def chat(system: str, history: List[Dict], *, temperature: float, max_tokens: int) -> str:
    """走 OpenAI 兼容的 /chat/completions。"""
    if not API_KEY:
        raise SystemExit("先 export FAT_FISH_API_KEY=...")

    payload = json.dumps(
        {
            "model": MODEL,
            "messages": [{"role": "system", "content": system}, *history],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def redact(message: object) -> str:
    """报错信息先擦一遍，别把 key 打到终端或日志里。"""
    text = str(message)
    if API_KEY and API_KEY in text:
        text = text.replace(API_KEY, "sk-***")
    return text


# ---- 主循环 ---------------------------------------------------------------

USAGE = """用法：python3 examples/simple_bot.py <persona-id> [选项]

选项：
  --group       强制模拟群聊（默认跟着人格卡的 channel 走）
  --private     强制模拟私聊
  --no-delay    不等待，回复立刻出来（调试用，正式用别开）
  --no-memory   不记对方说过的事（私聊默认会记）
"""


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}

    if not args or flags & {"--help", "-h"}:
        print(USAGE)
        return

    persona_id = args[0]
    persona = load_persona(persona_id)
    system = load_prompt(persona_id)
    name = name_from_prompt(system, persona.get("name", persona_id))
    temperature = float(persona.get("temperature", 0.8))

    # 场合：命令行优先，其次看卡
    channel = persona.get("channel", "both")
    if "--group" in flags:
        group = True
    elif "--private" in flags:
        group = False
    else:
        group = channel == "group"  # both 默认按私聊——终端里本来就只有你俩

    use_memory = (not group) and ("--no-memory" not in flags) and Memory is not None
    no_delay = "--no-delay" in flags

    memory = Memory(persona_id, "me") if use_memory else None

    max_tokens = GROUP_MAX_TOKENS if group else PRIVATE_MAX_TOKENS
    scene = "群聊" if group else "私聊"
    print(f"[{persona_id}] 已加载（{scene}模式，temperature {temperature}）")
    if use_memory:
        print("  会记着你的事，存 local/state/ 下。")
    cmds = "/reset 清对话" + (" /facts 看记了什么" if use_memory else "") + " /prompt 看完整人格 /quit 退出"
    print(f"  命令：{cmds}\n")

    history: List[Dict] = []
    last_reply = 0.0

    while True:
        try:
            text = input("你 > " if not group else "群友 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n鱼沉底了。")
            break

        if not text:
            continue

        if text in ("/quit", "/exit"):
            break
        if text == "/reset":
            history.clear()
            print("[对话已清空]\n")
            continue
        if text == "/prompt":
            print(system)
            print()
            continue
        if text == "/facts":
            if memory is None:
                why = "群聊模式不记事" if group else "加 --no-memory 了，这次不记事"
                print(f"[{why}]\n")
            elif not memory.facts:
                print("[还没记下什么]\n")
            else:
                for f in memory.facts:
                    print(f"  - {f['text']}（{f['heard']}）")
                print()
            continue

        # 先记账（记的是对方说的话，跟回不回没关系）
        if memory:
            got = memory.observe(text)
            if got:
                memory.save()

        history.append({"role": "user", "content": text})
        history[:] = history[-HISTORY_LIMIT:]

        if not should_reply(text, name, group):
            continue
        if group and time.time() - last_reply < GROUP_COOLDOWN:
            continue

        wait = None if no_delay else think_then_reply(text, group=group, hot=len(history) > 6)
        if wait is None and not no_delay:
            continue  # 群里太迟了，这轮不接
        if wait:
            time.sleep(wait)

        # 私聊把记事本接在 system prompt 后面（接前面会被后面的人设压过去）
        effective_system = append_to_prompt(system, memory) if memory else system

        try:
            reply = chat(effective_system, history, temperature=temperature, max_tokens=max_tokens)
        except Exception as exc:  # 网络/额度问题别让整个进程挂掉
            print(f"[错误] {redact(exc)}\n")
            continue

        last_reply = time.time()
        history.append({"role": "assistant", "content": reply})
        history[:] = history[-HISTORY_LIMIT:]
        print(f"{name} > {reply}\n")


if __name__ == "__main__":
    main()
