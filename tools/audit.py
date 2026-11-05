#!/usr/bin/env python3
"""体检：把「二十条鱼像不像一条鱼」变成能拦的数字。

三条判据，全都不联网、不需要 API key：

1. 信号占比 —— 一份 prompt 里，有多少字是这条鱼自己的。内核是所有人的，
   占比太低就说明模型读到的绝大部分是模板。低于 MIN_SIGNAL 报警。
2. 卡间相似度 —— 只比各卡独有的那一段。拿全文比是没意义的：21 份 prompt
   共享同一段内核，任意两张永远有 70% 的字一样，那个数字只说明内核有多长。
3. 卡内自检 —— 卡里写的规矩和它自己的示例对话别打架。

用法：
    python3 tools/audit.py              # 全部检查，正常退出码 0
    python3 tools/audit.py --verbose    # 把每张卡的数字也打出来
"""

from __future__ import annotations

import argparse
import itertools
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import personas as P  # noqa: E402

# ---- 判据阈值 ----------------------------------------------------------
MIN_SIGNAL = 0.22          # 卡自有内容至少占 prompt 的 22%；这是回归闸门不是质量线
MAX_SIMILARITY = 0.55      # 任意两张卡的独有部分，2-gram Jaccard 不超过这个
MAX_EXAMPLES = 3           # 示例对话最多几组（更多是负收益，见 README）

# 卡独有部分的起点：compose_prompt 里最后一段是【<名字> 自己】
_OWN_MARKER = "】\n"


def _grams(text: str, n: int = 2) -> set:
    """去空白后取 n-gram 集合。中文不用分词，2-gram 足够稳。"""
    squashed = re.sub(r"\s+", "", text)
    return {squashed[i:i + n] for i in range(len(squashed) - n + 1)}


def _jaccard(a: str, b: str) -> float:
    ga, gb = _grams(a), _grams(b)
    if not (ga | gb):
        return 0.0
    return len(ga & gb) / len(ga | gb)


def _own_section(prompt: str) -> str:
    """切出【<名字> 自己】之后的部分——这条鱼独有的那一段。"""
    idx = prompt.rfind(_OWN_MARKER)
    return prompt[idx:] if idx > 0 else prompt


def load_prompts(root: Path) -> Dict[str, str]:
    """读 dist/prompts。不在就现场生成一份，不写盘。"""
    built = sorted((root / "dist" / "prompts").glob("*.md"))
    if built:
        return {p.stem: p.read_text(encoding="utf-8") for p in built}

    out: Dict[str, str] = {}
    for data in P.load_all(root):
        out[data["id"]] = P.compose_prompt(data, root)
    return out


# ---- 三条判据 ----------------------------------------------------------
def check_signal(prompts: Dict[str, str]) -> Tuple[List[str], List[Tuple[str, float]]]:
    problems: List[str] = []
    rows: List[Tuple[str, float]] = []
    for pid, text in sorted(prompts.items()):
        own = len(_own_section(text))
        total = len(text)
        ratio = own / total if total else 0.0
        rows.append((pid, ratio))
        if ratio < MIN_SIGNAL:
            problems.append(
                f"{pid}：卡自有内容只占 {ratio:.0%}（{own}/{total} 字），"
                f"低于 {MIN_SIGNAL:.0%}——内核又长回去了，或者这张卡太空"
            )
    return problems, rows


def check_similarity(prompts: Dict[str, str]) -> Tuple[List[str], float]:
    own = {pid: _own_section(text) for pid, text in prompts.items()}
    pairs = itertools.combinations(sorted(own), 2)
    worst = 0.0
    over: List[Tuple[float, str, str]] = []
    for a, b in pairs:
        sim = _jaccard(own[a], own[b])
        worst = max(worst, sim)
        if sim > MAX_SIMILARITY:
            over.append((sim, a, b))
    over.sort(reverse=True)
    problems = [
        f"{a} 和 {b} 的独有部分相似度 {sim:.2f}，超过 {MAX_SIMILARITY}——这两条鱼在说同一种话"
        for sim, a, b in over
    ]
    return problems, worst


def check_internal(root: Path) -> List[str]:
    """卡里写的规矩，别让它自己的示例对话先破掉。"""
    problems: List[str] = []
    for data in P.load_all(root):
        pid = data["id"]
        examples = data.get("example_dialogues") or []
        if len(examples) > MAX_EXAMPLES:
            problems.append(
                f"{pid}：示例对话 {len(examples)} 组，多于 {MAX_EXAMPLES} 组——"
                f"实测加例句是负收益，模型会照抄去"
            )
        for turn in examples:
            reply = str(turn.get("assistant", ""))
            if len(reply) > 40:
                problems.append(f"{pid}：示例回复 {len(reply)} 字，超过 40 字——它在教模型说长话")
            if re.search(r"\n\s*\n", reply):
                problems.append(f"{pid}：示例回复里分了段——它在教模型分段")
            if re.search(r"[（(](?:心想|暗想|内心|旁白|沉默|停顿)[^）)]*[）)]", reply):
                problems.append(f"{pid}：示例回复里有括号内心戏——正是内核明令禁止的")
    return problems


def main(argv: List[str] | None = None) -> int:
    global MIN_SIGNAL, MAX_SIMILARITY

    parser = argparse.ArgumentParser(description="人格卡体检：不联网、不需要 key")
    parser.add_argument("--root", default=None, help="仓库根目录，默认自动向上找")
    parser.add_argument("--verbose", action="store_true", help="打每张卡的数字")
    parser.add_argument("--min-signal", type=float, default=MIN_SIGNAL)
    parser.add_argument("--max-similarity", type=float, default=MAX_SIMILARITY)
    args = parser.parse_args(argv)

    MIN_SIGNAL = args.min_signal
    MAX_SIMILARITY = args.max_similarity

    root = P.resolve_root(args.root)
    prompts = load_prompts(root)
    if not prompts:
        print("一张卡都没找到，先跑 python3 tools/build.py", file=sys.stderr)
        return 2

    print(f"体检 {len(prompts)} 张卡（不联网，不花 key）\n")

    signal_problems, rows = check_signal(prompts)
    sim_problems, worst = check_similarity(prompts)
    internal_problems = check_internal(root)

    if args.verbose:
        print("每张卡的信号占比：")
        for pid, ratio in sorted(rows, key=lambda r: r[1]):
            print(f"  {pid:<14} {ratio:.0%}")
        print()

    avg_signal = sum(r for _, r in rows) / len(rows)
    total_length = sum(len(t) for t in prompts.values()) / len(prompts)
    print(f"1) 信号占比：平均 {avg_signal:.0%}（均长 {total_length:.0f} 字）")
    print(f"2) 卡间相似度：最高 {worst:.2f}")
    print(f"3) 卡内自检：检查了 {len(prompts)} 张卡的示例对话")

    problems = signal_problems + sim_problems + internal_problems
    if problems:
        print(f"\n发现 {len(problems)} 个问题：")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("\n全过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
