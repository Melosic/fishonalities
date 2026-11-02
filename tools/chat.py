#!/usr/bin/env python3
"""在命令行里试跑某一张人格卡。

用法：
    export FAT_FISH_API_KEY=sk-xxx
    python3 tools/chat.py lao-fei          # 用 id 找卡
    python3 tools/chat.py personas/veteran/lao-fei.yaml   # 也可以直接给路径

环境变量：
    FAT_FISH_API_KEY   必填，请求头里的 Bearer token（不会打印到终端）
    FAT_FISH_BASE_URL  可选，默认 https://api.deepseek.com
    FAT_FISH_MODEL     可选，默认 deepseek-chat

交互命令（在提示符下输入）：
    /prompt   打印完整的 system prompt（调试用）
    /reset    清空对话历史，重新开始
    /quit     退出（也认 /exit、Ctrl-D）
空行直接跳过，不发请求。temperature 用人格卡里写的值。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import personas as P  # noqa: E402

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
MAX_TOKENS = 200
HISTORY_LIMIT = 20
TIMEOUT = 60

PROMPT_PREFIX = "群友 > "
COMMANDS = {
    "/quit": "退出",
    "/exit": "退出",
    "/reset": "清空对话历史",
    "/prompt": "打印完整 system prompt",
    "/help": "看命令列表",
}


class ApiError(Exception):
    """调用模型接口失败。message 里已经抹掉 key。"""


def redact(text: str, key: str) -> str:
    """任何要打印的字符串都先过一遍，确保 key 不会漏到终端 / 日志里。"""
    if key and key in text:
        text = text.replace(key, "***")
    return text


def chat_once(system: str, history: List[Dict[str, str]], temperature: float) -> str:
    """发一次 OpenAI 兼容的 /chat/completions，返回回复文本。"""
    api_key = os.environ.get("FAT_FISH_API_KEY", "").strip()
    if not api_key:
        raise ApiError("没有设置 FAT_FISH_API_KEY，先 export 一下再跑")
    base_url = os.environ.get("FAT_FISH_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    model = os.environ.get("FAT_FISH_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
    messages.extend(history[-HISTORY_LIMIT:])
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": MAX_TOKENS,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:  # noqa: BLE001 - 读不到 body 就算了，别挡住报错
            pass
        raise ApiError(redact(f"接口返回 HTTP {exc.code}：{body or exc.reason}", api_key)) from exc
    except urllib.error.URLError as exc:
        raise ApiError(redact(f"连不上 {base_url}：{exc.reason}", api_key)) from exc
    except TimeoutError as exc:
        raise ApiError(f"请求超时（{TIMEOUT}s），模型那边没回话") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(redact(f"返回的不是 JSON：{raw[:200]}", api_key)) from exc
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ApiError(redact(f"返回结构不对：{raw[:200]}", api_key)) from exc
    return str(content).strip()


def load_persona_for_chat(target: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """找到并校验这张卡；结构不合法就别硬跑。"""
    persona = P.find_persona(target, root)
    errors = P.validate_persona(persona, root=root)
    if errors:
        detail = "\n".join(f"  {e.render()}" for e in errors[:10])
        raise P.PersonaError(
            f'这张卡没通过校验（{"、".join(str(e.field) for e in errors[:5])} …），先修好再试跑：\n{detail}'
        )
    return persona


def print_banner(persona: Dict[str, Any], strict_ok: bool) -> None:
    base_url = os.environ.get("FAT_FISH_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    model = os.environ.get("FAT_FISH_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    print(f"[{persona['id']}] {persona['name']} · {persona['tagline']}")
    print(f"  模型 {model} @ {base_url}，temperature {persona['temperature']}")
    print("  /prompt 看完整 system prompt，/reset 重开，/quit 退出；空行直接跳过。")
    if not strict_ok:
        print("  提示：文风检查没过（跑 python3 tools/validate.py --strict 看原因），只影响试跑手感。")
    print("")


def repl(persona: Dict[str, Any], root: Optional[Path] = None) -> int:
    system = P.compose_prompt(persona, root)
    errors = P.style_checks(persona)
    name = persona["name"]
    temperature = float(persona["temperature"])

    history: List[Dict[str, str]] = []
    print_banner(persona, strict_ok=not errors)

    while True:
        try:
            text = input(PROMPT_PREFIX).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n鱼沉底了。")
            return 0

        if not text:
            continue

        command = text.lower()
        if command in ("/quit", "/exit"):
            print("鱼沉底了。")
            return 0
        if command == "/reset":
            history.clear()
            print("（历史清空）")
            continue
        if command == "/prompt":
            print("-" * 60)
            print(system)
            print("-" * 60)
            continue
        if command == "/help":
            print("  ".join(f"{cmd}={desc}" for cmd, desc in COMMANDS.items()))
            continue
        if text.startswith("/"):
            print(f"没这个命令：{text}（/help 看可用的）")
            continue

        candidate = history + [{"role": "user", "content": text}]
        try:
            reply = chat_once(system, candidate, temperature)
        except ApiError as exc:
            print(f"[错误] {exc}")
            continue
        if not reply:
            print(f"[{name}] （空回复，可能是 max_tokens 被吃完了）")
            continue

        history = (candidate + [{"role": "assistant", "content": reply}])[-HISTORY_LIMIT:]
        print(f"{name} > {reply}")
        print("")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="在命令行试跑一张人格卡（走 OpenAI 兼容的 /chat/completions）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("persona", help="人格卡 id（如 lao-fei）或 .yaml 路径")
    parser.add_argument("--root", default=None, help="仓库根目录（默认本文件上一级）")
    args = parser.parse_args(list(argv) if argv is not None else None)

    root = Path(args.root) if args.root else None
    try:
        persona = load_persona_for_chat(args.persona, root)
    except P.PersonaError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1

    try:
        return repl(persona, root)
    except P.PersonaError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
