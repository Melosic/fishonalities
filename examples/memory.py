#!/usr/bin/env python3
"""记忆层参考实现：让它真的记得上个月那件事。

**先说清楚它做不到什么。**

模型本身没有记忆。每轮对话都是重开一次，`HISTORY_LIMIT` 之外的东西全部消失。
这个文件解决的是「上次那件事」——把说过的话里值得留的挑出来存盘，下次开场塞回
system prompt 里面。仅此而已。

它做不到：真懂你在说什么、自己决定什么时候该想起什么、把两件事联系起来。
那些都得靠模型能力，不是靠一个 JSON 文件。

所以这个文件的价值只有两个：

1. **给一条能跑的最小路径。** 否则 `docs/INTEGRATIONS.md` 里那句「私聊的核心价值
   是它记得你上次说的那件事」就是句空话。
2. **把「该记什么」这个决定权交出去。** 默认的抽取规则很笨（见 `extract`），
   你可以整套换掉，接口只有两个函数。

用法：

    from memory import Memory
    mem = Memory("xiao-geng", "user-42")
    mem.recall_block()          # 返回一段能直接拼到 system prompt 末尾的文本
    mem.observe("我下周三要去做个小手术", when=...)   # 挑值得记的存下
    mem.save()

零第三方依赖，就是一个 JSON 文件。
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# 存哪儿。放仓库外——`local/` 已经被 .gitignore 忽略，别把用户的私事提交上去。
DEFAULT_HOME = Path(os.environ.get("FAT_FISH_STATE") or "local/state")

# 一个用户最多留几条。留太多会把 system prompt 塞满，反而把人格挤掉。
MAX_FACTS = 12
# 塞回 prompt 时最多用几条，挑最近的。
MAX_RECALL = 5

# 值得记的信号。**这一块最该被替换**——默认规则只认「明确说出口的时间 / 事件」，
# 不懂反讽，不懂「我最近挺好的」其实是「别问了」。
_FACT_PATTERNS = (
    # 时间锚点 + 事件：「下周三要去做个小手术」
    re.compile(r"[^\n。！？]{0,30}(?:下|这|明|上)(?:周|个?月|天)[^\n。！？]{2,40}"),
    # 明确的个人状态：「我在准备考研」「我换了工作」
    re.compile(r"我(?:在|正在)?(?:准备|打算|想|刚|已经|最近)[^\n。！？]{4,40}"),
    # 生日、纪念日、约定
    re.compile(r"[^\n。！？]{0,20}(?:生日|纪念日|说好了|答应|约好)[^\n。！？]{0,40}"),
    # 身体 / 健康
    re.compile(r"[^\n。！？]{0,20}(?:手术|体检|看病|吃药|住院|复查)[^\n。！？]{0,30}"),
)

# 这些话不值得记——客套、情绪余温、以及模型自己说的话。
_NOT_WORTHY = re.compile(r"^(?:嗯+|哦+|好的?|哈哈+|在吗|吃了吗|晚安|早安|睡吧)[。！？…]*$")


def _now() -> float:
    return time.time()


def _fmt_day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def extract(text: str) -> Optional[str]:
    """从一句人话里挑出值得记的那一块。挑不出就返回 None。

    这是**故意做得笨**的：宁可漏记，也不要记一堆没用的把 prompt 塞满。
    """
    text = (text or "").strip()
    if len(text) < 6 or _NOT_WORTHY.match(text):
        return None
    for pattern in _FACT_PATTERNS:
        hit = pattern.search(text)
        if hit:
            snippet = hit.group(0).strip("，。！？、 \t")
            # 太短的是噪声，太长的不像是在说一件事
            if 4 <= len(snippet) <= 60:
                return snippet
    return None


class Memory:
    """一条鱼的记事本。一个（人格, 对方）一份，互不串味。"""

    def __init__(self, persona_id: str, user_id: str, home: Optional[Path] = None) -> None:
        self.persona_id = persona_id
        self.user_id = user_id
        base = Path(home) if home else DEFAULT_HOME
        self.path = base / f"{persona_id}__{user_id}.json"
        self.facts: List[Dict[str, Any]] = []
        self._load()

    # ---- 读写 --------------------------------------------------------
    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # 文件坏了就当没记过，别让人格卡因为一个 JSON 崩掉
            return
        facts = raw.get("facts")
        if isinstance(facts, list):
            self.facts = [f for f in facts if isinstance(f, dict) and f.get("text")]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "persona": self.persona_id,
            "user": self.user_id,
            "updated": _fmt_day(_now()),
            "facts": self.facts,
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    # ---- 记 ----------------------------------------------------------
    def observe(self, text: str, when: Optional[float] = None) -> Optional[str]:
        """看一眼对方说了什么，值得记就记下来，返回记下的那条（没记返回 None）。"""
        fact = extract(text)
        if not fact:
            return None

        # 同一件事说两遍不算两件
        for known in self.facts:
            if known["text"] == fact:
                known["heard"] = _fmt_day(when or _now())
                known["count"] = int(known.get("count", 1)) + 1
                return None

        self.facts.append(
            {"text": fact, "first": _fmt_day(when or _now()), "heard": _fmt_day(when or _now()),
             "count": 1}
        )
        # 超出上限就丢最早记的（不是最早听的——听了很多次的说明重要）
        if len(self.facts) > MAX_FACTS:
            self.facts.sort(key=lambda f: (int(f.get("count", 1)), f.get("first", "")))
            self.facts = self.facts[-MAX_FACTS:]
        return fact

    # ---- 用 ----------------------------------------------------------
    def recall_block(self, limit: int = MAX_RECALL) -> str:
        """拼一段能直接接在 system prompt 末尾的文本。没记忆就返回空串。"""
        if not self.facts:
            return ""

        picked = sorted(self.facts, key=lambda f: (int(f.get("count", 1)), f.get("heard", "")))
        picked = picked[-limit:]
        lines = [f"- {f['text']}（{f['heard']}）" for f in picked]
        return (
            "【你记着的事】\n"
            "这些是对方以前亲口说过的。聊到相关的事可以自然地提一句，"
            "但别一口气全倒出来，也别当成清单念——记错、记混反而更像人。\n"
            + "\n".join(lines)
        )

    def forget(self, fact_text: str) -> bool:
        """对方说「忘了这件事」的时候用。有人要删就得删得掉。"""
        before = len(self.facts)
        self.facts = [f for f in self.facts if f["text"] != fact_text]
        return len(self.facts) < before


def append_to_prompt(system_prompt: str, memory: Memory) -> str:
    """把记忆接在系统提示词后面。**接在后面不是前面**——
    接在前面会被后面的人设段压过去，模型就只当背景音了。
    """
    block = memory.recall_block()
    if not block:
        return system_prompt
    return system_prompt.rstrip() + "\n\n" + block + "\n"


if __name__ == "__main__":
    # 一个自我演示：不联网，不需要 key，纯本地。
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        mem = Memory("xiao-geng", "demo", home=Path(tmp))
        said = [
            "今天好累啊",
            "我下周三要去做个小手术",
            "我在准备考研，还有两个月",
            "哈哈",
            "我生日是十一月十七",
        ]
        for line in said:
            got = mem.observe(line)
            print(f"{'记  ' if got else '略过'}｜{line}")
        mem.save()

        print("\n--- 重新加载（模拟第二天新开一轮对话）---")
        again = Memory("xiao-geng", "demo", home=Path(tmp))
        print(again.recall_block() or "（什么都没记住）")
