#!/usr/bin/env python3
"""把 personas/ 下的人格卡编译成 dist/ 里的发布物。

产物（全部确定性：同样的输入跑两次，字节完全一样；不含时间戳、不含绝对路径）：
    dist/index.json       全部人格的结构化数据 + 统计（总数 / 各原型数量 / 标签词频）
    dist/prompts/<id>.md  每个 id 一份自包含 system prompt（compose_prompt 的结果）
    dist/INDEX.md         人类看的索引页，按原型分组

想让 prompt 变成「拷到手机就能用」的文件夹，跑 tools/pack.py。

有校验错误时拒绝构建，退出码 1。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import personas as P  # noqa: E402
import validate as V  # noqa: E402

INDEX_JSON = "index.json"
INDEX_MD = "INDEX.md"
PROMPTS_DIR = "prompts"
GENERATED_BY = "tools/build.py"


# --------------------------------------------------------------------------
# 收集 + 守住「有错不构建」
# --------------------------------------------------------------------------


class BuildError(Exception):
    pass


def collect_cards(root: Path) -> List[Tuple[str, Path, Dict[str, Any]]]:
    """用 validate 的非 strict 模式收卡；有错就抛 BuildError（附错误明细）。"""
    report = V.collect(root, strict=False)
    errors: List[str] = [V.format_error(label, verr) for label, verr in report.errors]
    # 文件名要按 id 落地，所以 id 撞了必须拦住（strict 之外单独兜一层）
    for label, verr in P.duplicate_id_errors(report.entries):
        errors.append(V.format_error(label, verr))
    if errors:
        head = "\n".join(errors[:20])
        more = f"\n… 还有 {len(errors) - 20} 条，跑 python3 tools/validate.py 看全" if len(errors) > 20 else ""
        raise BuildError(f"校验不通过，拒绝构建：\n{head}{more}")
    if not report.entries:
        raise BuildError("personas/ 下一张卡都没有，没什么可构建的")

    cards: List[Tuple[str, Path, Dict[str, Any]]] = []
    scanned = P.scan(root)
    for item in scanned:
        if item.data is None:
            continue
        cards.append((P.relative(item.path, root), item.path, item.data))
    cards.sort(key=lambda entry: entry[2]["id"])
    return cards


# --------------------------------------------------------------------------
# 产物渲染
# --------------------------------------------------------------------------


def build_stats(cards: Sequence[Tuple[str, Path, Dict[str, Any]]]) -> Dict[str, Any]:
    archetype_counter: Counter = Counter()
    tag_counter: Counter = Counter()
    for _, _, persona in cards:
        archetype_counter[persona["archetype"]] += 1
        for tag in persona["tags"]:
            tag_counter[tag] += 1
    return {
        "total": len(cards),
        "archetypes": {name: archetype_counter[name] for name in sorted(archetype_counter)},
        "tags": {name: tag_counter[name] for name in sorted(tag_counter)},
    }


def render_index_json(cards: Sequence[Tuple[str, Path, Dict[str, Any]]]) -> str:
    payload = {
        "generated_by": GENERATED_BY,
        "personas": [persona for _, _, persona in cards],
        "stats": build_stats(cards),
    }
    # sort_keys + 固定缩进 + 结尾换行 => 字节级确定性
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _md_cell(text: str) -> str:
    """表格单元格里不能有竖线和换行。"""
    return str(text).replace("|", "/").replace("\n", " ").strip()


def render_index_md(cards: Sequence[Tuple[str, Path, Dict[str, Any]]]) -> str:
    stats = build_stats(cards)
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for _, _, persona in cards:
        groups.setdefault(persona["archetype"], []).append(persona)

    lines: List[str] = []
    lines.append("# 鱼格 · 索引")
    lines.append("")
    lines.append(f"共 **{stats['total']}** 条鱼，分布在 {len(groups)} 个原型里。")
    lines.append("")
    lines.append("> 本文件由 `tools/build.py` 生成，请改 `personas/` 下的源文件，别手改这里。")
    lines.append("")

    for archetype in sorted(groups):
        members = groups[archetype]
        lines.append(f"## {archetype}（{len(members)}）")
        lines.append("")
        lines.append("| 名字 | 一句话 | 标签 | 场合 |")
        lines.append("| --- | --- | --- | --- |")
        for persona in members:
            tags = " · ".join(persona["tags"])
            channel = P.CHANNEL_LABELS.get(persona.get("channel", "both"), "群聊和私聊")
            lines.append(
                f"| {_md_cell(persona['name'])} "
                f"| {_md_cell(persona['tagline'])} "
                f"| {_md_cell(tags)} "
                f"| {_md_cell(channel)} |"
            )
        lines.append("")

    lines.append("## 统计")
    lines.append("")
    lines.append("| 原型 | 数量 |")
    lines.append("| --- | --- |")
    for archetype, count in stats["archetypes"].items():
        lines.append(f"| {_md_cell(archetype)} | {count} |")
    lines.append("")
    lines.append("标签词频：" + "、".join(f"{tag}×{count}" for tag, count in stats["tags"].items()))
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 落盘：先算完再写，写之前清掉过期产物
# --------------------------------------------------------------------------


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" 保证在 Windows 上也是同一串字节
    path.write_text(text, encoding="utf-8", newline="\n")


def build(root: Optional[Path] = None, quiet: bool = False) -> Dict[str, Any]:
    base = P.resolve_root(root)
    dist = base / "dist"
    cards = collect_cards(base)

    index_json = render_index_json(cards)
    index_md = render_index_md(cards)
    prompts: Dict[str, str] = {}
    for label, _path, persona in cards:
        prompts[persona["id"]] = P.compose_prompt(persona, base)

    dist.mkdir(parents=True, exist_ok=True)
    prompts_dir = dist / PROMPTS_DIR
    prompts_dir.mkdir(parents=True, exist_ok=True)

    _write_text(dist / INDEX_JSON, index_json)
    _write_text(dist / INDEX_MD, index_md)
    for persona_id in sorted(prompts):
        _write_text(prompts_dir / f"{persona_id}.md", prompts[persona_id])

    # 幂等：删掉这次没有产出的旧 prompt，避免 dist 里留幽灵文件
    removed: List[str] = []
    for stale in sorted(prompts_dir.glob("*.md")):
        if stale.stem not in prompts:
            stale.unlink()
            removed.append(P.relative(stale, base))

    result = {
        "cards": len(cards),
        "prompts": len(prompts),
        "index_bytes": len(index_json.encode("utf-8")),
        "removed": removed,
        "stats": build_stats(cards),
    }
    if not quiet:
        print(f"构建完成：{result['cards']} 张卡 → {result['prompts']} 份 prompt")
        for name in (INDEX_JSON, INDEX_MD):
            print(f"  dist/{name:<12} {len((dist / name).read_bytes()):>7} B")
        print(f"  dist/{PROMPTS_DIR}/<id>.md   {result['prompts']} 个文件")
        for stale in removed:
            print(f"  清理过期产物 {stale}")
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="把 personas/ 编译成 dist/（有校验错误时拒绝构建）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--root", default=None, help="仓库根目录（默认本文件上一级）")
    parser.add_argument("--quiet", action="store_true", help="只输出错误")
    args = parser.parse_args(list(argv) if argv is not None else None)

    started = time.time()
    try:
        build(Path(args.root) if args.root else None, quiet=args.quiet)
    except BuildError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except P.PersonaError as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"（耗时 {time.time() - started:.2f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
