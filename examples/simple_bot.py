#!/usr/bin/env python3
"""最小可跑的群聊机器人，演示怎么把人格卡接进去。

这不是一个完整的产品，是一个「该怎么用」的样板：
- 从 dist/prompts/ 读自包含的 system prompt
- 按概率决定要不要接话（有性格的鱼不会句句都回）
- 硬卡 max_tokens 和频率，防止刷屏
- 上下文只保留最近若干条，防止人设被别人的口癖带跑

用法：
    export FAT_FISH_API_KEY=sk-xxx
    python3 examples/simple_bot.py gou-dan

生产环境请换成真正的平台适配（NapCat / AstrBot / telegram-bot 等），
这个脚本只负责演示「接法和参数怎么定」。
"""

import json
import os
import random
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = ROOT / "dist" / "prompts"

API_KEY = os.environ.get("FAT_FISH_API_KEY", "")
BASE_URL = os.environ.get("FAT_FISH_BASE_URL", "https://api.deepseek.com").rstrip("/")
MODEL = os.environ.get("FAT_FISH_MODEL", "deepseek-chat")

MAX_TOKENS = 200          # 群聊别给太长
HISTORY_LIMIT = 20        # 只带最近 20 条，多了人设会糊
REPLY_PROBABILITY = 0.35  # 没被叫名字时的接话概率
COOLDOWN_SECONDS = 8      # 两条回复之间至少隔多久


def load_prompt(persona_id: str) -> str:
    path = PROMPT_DIR / f"{persona_id}.md"
    if not path.exists():
        raise SystemExit(
            f"找不到 {path}\n先跑：python3 tools/build.py"
        )
    return path.read_text(encoding="utf-8")


def chat(system: str, history: list) -> str:
    """走 OpenAI 兼容的 /chat/completions。"""
    if not API_KEY:
        raise SystemExit("先 export FAT_FISH_API_KEY=...")

    payload = json.dumps(
        {
            "model": MODEL,
            "messages": [{"role": "system", "content": system}, *history],
            "temperature": 0.8,
            "max_tokens": MAX_TOKENS,
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


def should_reply(text: str, name: str) -> bool:
    """被叫名字必回，否则按概率接话。"""
    if name in text:
        return True
    return random.random() < REPLY_PROBABILITY


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("用法：python3 examples/simple_bot.py <persona-id>")

    persona_id = sys.argv[1]
    system = load_prompt(persona_id)

    # 从 system prompt 里捞名字，用来判断「有没有人叫我」
    name = persona_id
    for line in system.splitlines():
        if line.startswith("# 你现在是"):
            name = line.split("是", 1)[1].strip("。 \n")
            break

    history: list = []
    last_reply = 0.0

    print(f"[{persona_id}] 已加载，Ctrl-C 退出。群里说话试试。\n")

    while True:
        try:
            text = input("群友 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n鱼沉底了。")
            break

        if not text:
            continue

        # 先记账，再决定回不回
        history.append({"role": "user", "content": text})
        history[:] = history[-HISTORY_LIMIT:]

        if not should_reply(text, name):
            continue
        if time.time() - last_reply < COOLDOWN_SECONDS:
            continue

        try:
            reply = chat(system, history)
        except Exception as exc:  # 网络/额度问题别让整个进程挂掉
            print(f"[错误] {redact(exc)}")
            continue

        last_reply = time.time()
        history.append({"role": "assistant", "content": reply})
        history[:] = history[-HISTORY_LIMIT:]
        print(f"{name} > {reply}")


if __name__ == "__main__":
    main()
