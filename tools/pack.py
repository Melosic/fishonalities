#!/usr/bin/env python3
"""把生成好的 prompt 打包成一个开箱即用的文件夹。

dist/prompts/ 里是 a-meng.md 这种英文 id，分不清谁是谁。这个工具把它们
按场合分好、改成认得出来的中文名，再配一份说明，拷到手机里就能直接用。

    python3 tools/pack.py                    # 输出到 out/鱼格/
    python3 tools/pack.py --out ~/下载/鱼格
    python3 tools/pack.py --channel private  # 只要私聊的
"""

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import personas as P


# 场合 -> 文件夹名。用户看得懂的说法，不是 group/private/both。
CHANNEL_FOLDERS = {
    "group": "群聊用",
    "private": "私聊用",
    "both": "都行",
}

# 场合 -> 一句话解释，写进 README
CHANNEL_HINTS = {
    "group": "丢进群里。它会判断这句是不是冲它说的，不该接的时候不接。",
    "private": "只跟你一个人聊。它记得住事，会主动开口，话可以多说两句。",
    "both": "群里私聊都能用。场合规矩会两套都给。",
}

# 原型 -> 中文。文件名里已经有 tagline 了，表格里再放一遍是废话，
# 换成「这条鱼是哪种类型」，才是文件名之外的增量信息。
ARCHETYPE_LABELS = {
    "veteran": "老资历",
    "streetwise": "市井",
    "literary": "文艺",
    "chuuni": "中二",
    "naive": "憨",
    "tsundere": "傲娇",
    "sarcastic": "阴阳怪气",
    "healer": "治愈",
    "cyber": "赛博",
    "hermit": "闷葫芦",
    "leader": "带队",
    "salaryman": "打工人",
    "koi": "锦鲤",
    "nerd": "技术宅",
    "gamer": "游戏搭子",
    "mother": "妈味",
    "sister": "妹妹",
    "freeloader": "吃白饭",
    "lurker": "潜水",
    "foulmouth": "嘴臭",
    "peer": "同龄人",
}

PACK_DIRNAME = "鱼格"
README_NAME = "先看这个.md"


def safe_filename(text: str) -> str:
    """文件名里不能有 / \\ : * ? " < > |，换成下划线。"""
    bad = '<>:"/\\|?*'
    for ch in bad:
        text = text.replace(ch, "_")
    return text.strip().rstrip(".")


def prompt_filename(persona: Dict[str, Any]) -> str:
    """小鲠·嘴上让你走，尾巴还留在原地.md —— 光看文件名就知道是谁。

    tagline 不截断：截到一半（「只管你吃没吃穿」丢掉末字）比长一点更难看。
    schema 限死 tagline 6-30 字，加上名字最多 40 字上下，文件名扛得住。
    """
    name = safe_filename(str(persona.get("name", persona["id"])))
    tag = safe_filename(str(persona.get("tagline", ""))).rstrip("。，、！？")
    if tag:
        return f"{name}·{tag}.md"
    return f"{name}.md"


def _bullet(lines: Sequence[str], limit: int = 0) -> List[str]:
    items = list(lines)
    if limit:
        items = items[:limit]
    return [f"- {item}" for item in items]


def render_readme(packed: Dict[str, List[Dict[str, Any]]], root: Path) -> str:
    """这个文件夹怎么用，一页说清。"""
    total = sum(len(v) for v in packed.values())
    lines: List[str] = []
    lines.append("# 鱼格 · 开箱包")
    lines.append("")
    lines.append(f"共 **{total}** 条鱼，按场合分好了文件夹。每条鱼一个 `.md` 文件。")
    lines.append("")
    lines.append("## 怎么用")
    lines.append("")
    lines.append("1. 打开你要用的那个 `.md` 文件，**全选、复制**。")
    lines.append("2. 粘到模型的 **system prompt / 系统提示词 / 人设** 那一栏。")
    lines.append("3. 正常聊天就行。不要再说「请你扮演一条鱼」，它会自己入戏。")
    lines.append("")
    lines.append("> 文件是自包含的：安全底线 + 场合规矩 + 共用内核 + 这条鱼自己，")
    lines.append("> 全拼好了。不用再额外加任何东西。")
    lines.append("")
    lines.append("## 选哪条")
    lines.append("")

    for channel, personas in packed.items():
        if not personas:
            continue
        folder = CHANNEL_FOLDERS.get(channel, channel)
        lines.append(f"### {folder}（{len(personas)} 条）")
        lines.append("")
        lines.append(CHANNEL_HINTS.get(channel, ""))
        lines.append("")
        lines.append("| 文件 | 类型 |")
        lines.append("| --- | --- |")
        for persona in personas:
            fname = prompt_filename(persona)
            arch = str(persona.get("archetype", ""))
            label = ARCHETYPE_LABELS.get(arch, arch)
            lines.append(f"| `{fname}` | {label} |")
        lines.append("")

    lines.append("## 几个提醒")
    lines.append("")
    lines.append("- **温度调到 0.8 以上。** 太低会变得一本正经。")
    lines.append("- **回复长度限制在 200 token 左右。** 给太多它会开始写小作文。")
    lines.append("- **别秒回。** 这个 prompt 管不到，得你在接入层加延迟。")
    lines.append("- 想改某条鱼的说话方式，去改仓库里 `personas/` 下的 YAML，别改这里。")
    lines.append("")
    lines.append(f"（由 `tools/pack.py` 生成，源仓库 `{root.name}`）")
    return "\n".join(lines) + "\n"


def pack(
    out_dir: Path,
    root: Optional[Path] = None,
    channel: Optional[str] = None,
    quiet: bool = False,
) -> Dict[str, Any]:
    """生成开箱包。返回统计。"""
    base = P.resolve_root(root)
    personas = P.load_all(base)

    if channel:
        personas = [p for p in personas if p.get("channel") == channel]
        if not personas:
            raise P.PersonaError(f"没有 channel={channel} 的卡")

    packed: Dict[str, List[Dict[str, Any]]] = {"group": [], "private": [], "both": []}
    for persona in personas:
        ch = str(persona.get("channel", "both"))
        packed.setdefault(ch, []).append(persona)

    for group in packed.values():
        group.sort(key=lambda p: str(p.get("name", "")))

    # 先清空上次的产物，避免留幽灵文件
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for ch, group in packed.items():
        if not group:
            continue
        folder = out_dir / CHANNEL_FOLDERS.get(ch, ch)
        folder.mkdir(parents=True, exist_ok=True)
        for persona in group:
            text = P.compose_prompt(persona, base)
            target = folder / prompt_filename(persona)
            target.write_text(text, encoding="utf-8", newline="\n")
            written += 1

    (out_dir / README_NAME).write_text(render_readme(packed, base), encoding="utf-8", newline="\n")

    if not quiet:
        print(f"  {out_dir}/")
        for ch, group in packed.items():
            if group:
                print(f"    {CHANNEL_FOLDERS[ch]}/{'':<6} {len(group):>2} 条")
        print(f"    {README_NAME}")
    return {"total": written, "out_dir": str(out_dir), "by_channel": {k: len(v) for k, v in packed.items()}}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="把编译好的 prompt 打成一个开箱即用的文件夹",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--root", default=None, help="仓库根目录（默认本文件上一级）")
    parser.add_argument("--out", default=None, help=f"输出到哪（默认 <仓库>/out/{PACK_DIRNAME}）")
    parser.add_argument(
        "--channel",
        default=None,
        choices=["group", "private", "both"],
        help="只要某个场合的卡",
    )
    parser.add_argument("--quiet", action="store_true", help="只输出错误")
    args = parser.parse_args(list(argv) if argv is not None else None)

    base = P.resolve_root(Path(args.root) if args.root else None)
    out_dir = Path(args.out) if args.out else base / "out" / PACK_DIRNAME

    started = time.time()
    try:
        result = pack(out_dir, base, channel=args.channel, quiet=args.quiet)
    except P.PersonaError as exc:
        print(f"打包失败：{exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"\n{result['total']} 条鱼打包好了。整份文件夹拷到手机就能用。")
        print(f"（耗时 {time.time() - started:.2f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
