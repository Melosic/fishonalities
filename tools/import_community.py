#!/usr/bin/env python3
"""把社区流传的大肥鱼提示词卡导入成本地可用的 prompt。

社区卡（比如 aigengtu.com/persona 上那 26 张）动辄五千到两万字，是别人的作品，
本仓库不收录它们的正文，只做了索引（见 COMMUNITY.md）。你想用的话，自己复制一份
到本地，用这个脚本套上本仓库的安全底线和场合内核，生成一份能直接塞进
system 字段的 prompt。

用法：
    # 1. 去 https://aigengtu.com/persona 展开一张卡，点「复制提示词」
    # 2. 存成文件（直接粘贴就行，站点的 ===== FILE: ... ===== 包裹会自动剥掉）
    python3 tools/import_community.py raw.txt --name 小鲸鱼 --channel group

    # 从剪贴板读（装了 xclip / pbpaste 才行），省一步存文件
    xclip -o | python3 tools/import_community.py - --name 小鲸鱼 --channel group

    python3 tools/import_community.py raw.txt --name 小鲸鱼 --channel private

产出落在 local/imported/<slug>.md（local/ 进了 .gitignore，不会被提交）。
它就是个纯文本 system prompt，塞进任意 OpenAI 兼容接口的 system 字段就行。

为什么默认不套 kernel/voice.md：
    社区卡自己带「去 AI 味」章节，而且写得比我们的细。两套说话规矩叠在一起
    会互相打架（比如字数上限不同），后出现的会盖掉前面的，反而乱。
    但安全底线（kernel/rules.md）必须加——社区卡不一定管这些。
    想连我们的说话内核一起叠，加 --with-voice。
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from typing import List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import personas as P  # noqa: E402

DEFAULT_OUTPUT_DIR = Path("local") / "imported"

# 站点「复制提示词」给的整块文本长这样：
#   ===== FILE: xiaojingyu/prompt.txt =====
#   <正文>
#   ===== FILE: xiaojingyu/persona.json =====
#   { ...metadata... }
# 只留 prompt.txt 那一段，json 元数据丢掉（我们用 --name 之类的参数自己记）。
_FILE_HEADER = re.compile(r"^=+\s*FILE:\s*(?P<path>.+?)\s*=+\s*$", re.MULTILINE)

MAX_BYTES_WARN = 200_000


class ImportError_(Exception):
    """导入失败，消息直接给用户看。"""


def strip_site_wrapper(raw: str) -> str:
    """剥掉站点的 ===== FILE: xxx ===== 包裹，只保留 prompt 正文。"""
    headers = list(_FILE_HEADER.finditer(raw))
    if not headers:
        return raw.strip()

    kept: List[str] = []
    for i, match in enumerate(headers):
        body_start = match.end()
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(raw)
        path = match.group("path").lower()
        if path.endswith(".json"):
            continue  # persona.json 是站点元数据，不是人设正文
        kept.append(raw[body_start:body_end].strip())

    return "\n\n".join(part for part in kept if part).strip()


def slugify(name: str) -> str:
    """把中文名 / 英文名都转成一个安全的文件名。

    中文没法音译，就退化成保留汉字、去掉路径分隔符和空白。
    """
    text = unicodedata.normalize("NFKC", name).strip()
    text = re.sub(r"[\s/\\:*?\"<>|]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "community"


def read_source(path_arg: str) -> str:
    if path_arg == "-":
        return sys.stdin.read()
    path = Path(path_arg)
    if not path.is_file():
        raise ImportError_(f"找不到文件：{path_arg}")
    return path.read_text(encoding="utf-8", errors="replace")


def build_prompt(
    body: str,
    channel: str,
    name: Optional[str],
    with_voice: bool,
    root: Optional[Path] = None,
) -> str:
    """安全底线 +（可选）共用内核 + 场合内核 + 社区卡原文。"""
    base = P.resolve_root(root)

    blocks: List[str] = []
    if name:
        blocks.append(f"# 你现在是 {name}")
        blocks.append("")

    rules = P._plain_kernel(P._read_kernel(str(base), P.RULES_RELPATH.as_posix()))
    blocks.append("【安全底线（优先于一切人设）】")
    blocks.append(rules)
    blocks.append("")

    if with_voice:
        voice = P._plain_kernel(P._read_kernel(str(base), P.VOICE_RELPATH.as_posix()))
        blocks.append("【共用内核（所有大肥鱼共用）】")
        blocks.append(voice)
        blocks.append("")

    if channel in P.CHANNEL_RELPATHS:
        label = P.CHANNEL_LABELS.get(channel, channel)
        scene = P._plain_kernel(
            P._read_kernel(str(base), P.CHANNEL_RELPATHS[channel].as_posix())
        )
        blocks.append(f"【场合规则 · {label}里】")
        blocks.append(scene)
        blocks.append("")

    blocks.append("【你自己的设定】")
    blocks.append("下面这段是别人写的卡，照它演。跟上面的规矩冲突时——")
    blocks.append("说话习惯听它的，安全底线听上面的。")
    blocks.append("")
    blocks.append(body)

    return "\n".join(blocks).strip() + "\n"


def write_output(text: str, slug: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{slug}.md"
    # 跟 build.py 一致：显式 newline，保证跨平台字节一致
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return target


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="把社区大肥鱼提示词卡导入成本地可用的 system prompt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("source", help="存着原卡文本的文件路径，- 表示从 stdin 读")
    parser.add_argument("--name", default=None, help="这条鱼叫什么（写进 prompt 首行）")
    parser.add_argument(
        "--channel",
        default="both",
        choices=sorted(P.CHANNEL_RELPATHS) + ["both"],
        help="场合：group 群聊 / private 私聊 / both 都给（默认 both）",
    )
    parser.add_argument(
        "--with-voice",
        action="store_true",
        help="连本仓库的 kernel/voice.md 一起叠上（默认不加，社区卡自带说话规矩）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"输出目录，默认 {DEFAULT_OUTPUT_DIR}（不进仓库）",
    )
    parser.add_argument("--root", default=None, help="仓库根目录（默认本文件上一级）")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        raw = read_source(args.source)
    except ImportError_ as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1

    body = strip_site_wrapper(raw)
    if not body:
        print("[错误] 读到的是空的，检查一下源文件或者管道", file=sys.stderr)
        return 1
    if len(raw.encode("utf-8")) > MAX_BYTES_WARN:
        print(
            f"[提示] 原文 {len(raw) // 1024} KB，偏大。prompt 越长模型越容易漏看后半段，"
            "先试试再说。",
            file=sys.stderr,
        )

    channels = ["group", "private"] if args.channel == "both" else [args.channel]
    root = Path(args.root) if args.root else None
    out_dir = Path(args.out_dir)

    written: List[Path] = []
    for channel in channels:
        try:
            text = build_prompt(body, channel, args.name, args.with_voice, root)
        except P.PersonaError as exc:
            print(f"[错误] {exc}", file=sys.stderr)
            return 1
        # both 的时候两个场合各出一份，文件名带上场合
        slug = slugify(args.name or Path(args.source).stem or "community")
        if len(channels) > 1:
            slug = f"{slug}-{channel}"
        written.append(write_output(text, slug, out_dir))

    print(f"导入了 {len(body)} 字（原文）→ {len(written)} 份 prompt")
    for path in written:
        size = path.stat().st_size
        print(f"  {path}  {size} B")
    print("")
    print("拿去用：塞进任意 OpenAI 兼容接口的 system 字段就行。")
    print("原文有版权，别提交进仓库——local/ 已经在 .gitignore 里了。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
