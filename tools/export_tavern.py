#!/usr/bin/env python3
"""把人格卡导出成 SillyTavern Character Card V2（酒馆生态通用格式）。

产出一个 JSON：dist/tavern/<id>.json，可以直接拖进 SillyTavern / chub.ai 之类的客户端。
规范见 https://github.com/malfoyslastname/character-card-spec-v2

字段映射的思路：
    我们有的                 →  酒馆的
    tagline + summary        →  description 开头
    speak / catchphrases     →  description 正文（说话方式）
    memories                 →  description 正文（亲身经历过的事）
    quirks / taboos          →  description 正文（怪癖与禁区）
    moments.greeting         →  first_mes
    moments.fed / poke       →  alternate_greetings
    example_dialogues        →  mes_example
    拼好的完整 prompt         →  system_prompt
    fish / channel / moments →  extensions（酒馆不认，但不会丢）

扩展字段全放在 extensions 里并按 "fat_fish" 命名空间收拢，符合规范的
「不要销毁未知字段」要求。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import personas as P  # noqa: E402
import validate as V  # noqa: E402

TAVERN_DIR = "tavern"
SPEC = "chara_card_v2"
SPEC_VERSION = "2.0"
CREATOR_NOTES_HEAD = "由 鱼格 fishonalities 导出"


def _join_lines(lines: Sequence[str]) -> str:
    return "\n".join(str(line).strip() for line in lines if str(line).strip())


def _render_description(persona: Dict[str, Any]) -> str:
    """把 tagline/summary/speak/quirks/taboos 揉成一段酒馆能直接吃的描述。"""
    parts: List[str] = []
    parts.append(persona["tagline"])
    parts.append(persona["summary"])

    if persona.get("speak"):
        parts.append("")
        parts.append("【说话方式】")
        parts.extend(f"- {line}" for line in persona["speak"])

    if persona.get("catchphrases"):
        parts.append("")
        parts.append("【常挂嘴边的】")
        parts.extend(f"- {line}" for line in persona["catchphrases"])

    if persona.get("memories"):
        parts.append("")
        parts.append("【它亲身经历过的事】")
        parts.extend(f"- {line}" for line in persona["memories"])
    if persona.get("quirks"):
        parts.append("")
        parts.append("【小毛病】")
        parts.extend(f"- {line}" for line in persona["quirks"])

    if persona.get("taboos"):
        parts.append("")
        parts.append("【绝对不做的】")
        parts.extend(f"- {line}" for line in persona["taboos"])

    return _join_lines(parts)


def _render_personality(persona: Dict[str, Any]) -> str:
    bits = [persona["archetype"], persona["tone"]]
    bits.extend(persona["tags"])
    return "、".join(bits)


def _render_scenario(persona: Dict[str, Any]) -> str:
    label = P.CHANNEL_LABELS.get(persona.get("channel", "both"), "群聊和私聊")
    return (
        f"{label}里的一口缸。用户在养一条叫{persona['name']}的鱼，"
        f"喂它、逗它、看它从{persona['fish']['weight_start']}斤长到{persona['fish']['weight_grown']}斤。"
    )


def _render_mes_example(persona: Dict[str, Any]) -> str:
    name = persona["name"]
    blocks: List[str] = []
    for pair in persona.get("example_dialogues", []):
        user = str(pair.get("user", "")).strip()
        assistant = str(pair.get("assistant", "")).strip()
        if not user or not assistant:
            continue
        blocks.append(f"{{{{user}}}}: {user}")
        blocks.append(f"{name}: {assistant}")
    return _join_lines(blocks)


def _render_creator_notes(persona: Dict[str, Any]) -> str:
    meta = persona.get("meta", {})
    lines = [
        f"{CREATOR_NOTES_HEAD}（人格卡 {persona['id']} v{persona['version']}）。",
        f"原型：{persona['archetype']}　基调：{persona['tone']}　场合：{P.CHANNEL_LABELS.get(persona.get('channel', 'both'), '群聊和私聊')}",
        f"作者：{meta.get('author', '未署名')}　创建于：{meta.get('created', '未知')}",
    ]
    if meta.get("source") == "remix" and meta.get("inspiration"):
        lines.append(f"灵感出处：{meta['inspiration']}")
    lines.append("源仓库的 system_prompt 已经拼好安全底线与场合规矩，直接用即可。")
    return _join_lines(lines)


def _render_extensions(persona: Dict[str, Any]) -> Dict[str, Any]:
    fish = dict(persona["fish"])
    return {
        "fat_fish": {
            "id": persona["id"],
            "version": persona["version"],
            "archetype": persona["archetype"],
            "tone": persona["tone"],
            "channel": persona.get("channel", "both"),
            "temperature": persona["temperature"],
            "emoji": persona["emoji"],
            "fish": fish,
            "moments": dict(persona["moments"]),
            "meta": dict(persona.get("meta", {})),
        }
    }


def to_tavern_card(persona: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    """单张人格卡 → SillyTavern Character Card V2。"""
    moments = persona["moments"]
    data: Dict[str, Any] = {
        "name": persona["name"],
        "description": _render_description(persona),
        "personality": _render_personality(persona),
        "scenario": _render_scenario(persona),
        "first_mes": moments["greeting"],
        "mes_example": _render_mes_example(persona),
        "creator_notes": _render_creator_notes(persona),
        "system_prompt": P.compose_prompt(persona, root),
        "post_history_instructions": "",
        "alternate_greetings": [moments["fed"], moments["poke"]],
        "tags": list(persona["tags"]),
        "creator": persona.get("meta", {}).get("author", "fishonalities"),
        "character_version": persona["version"],
        "extensions": _render_extensions(persona),
    }
    return {"spec": SPEC, "spec_version": SPEC_VERSION, "data": data}


def render_tavern_json(persona: Dict[str, Any], root: Optional[Path] = None) -> str:
    # sort_keys + 固定缩进 => 字节级确定性，跟 build.py 的约定一致
    return json.dumps(to_tavern_card(persona, root), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _collect(root: Path) -> List[Dict[str, Any]]:
    """收卡并挡住校验错误：有错就不导出（跟 build.py 一个原则）。"""
    report = V.collect(root, strict=True)
    errors = [V.format_error(label, err) for label, err in report.errors]
    if errors:
        head = "\n".join(errors[:20])
        more = f"\n… 还有 {len(errors) - 20} 条，跑 python3 tools/validate.py --strict 看全" if len(errors) > 20 else ""
        raise P.PersonaError(f"校验不通过，拒绝导出：\n{head}{more}")
    # report.entries 是 (label, persona_dict) 的列表
    cards = [data for _label, data in report.entries]
    cards.sort(key=lambda persona: persona["id"])
    return cards


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" 保证跨平台字节一致
    path.write_text(text, encoding="utf-8", newline="\n")


def export_all(root: Optional[Path] = None, quiet: bool = False) -> Dict[str, Any]:
    base = P.resolve_root(root)
    cards = _collect(base)
    dist = base / "dist"
    tavern_dir = dist / TAVERN_DIR
    tavern_dir.mkdir(parents=True, exist_ok=True)

    written: List[str] = []
    for persona in cards:
        text = render_tavern_json(persona, base)
        _write_text(tavern_dir / f"{persona['id']}.json", text)
        written.append(persona["id"])

    removed: List[str] = []
    for stale in sorted(tavern_dir.glob("*.json")):
        if stale.stem not in written:
            stale.unlink()
            removed.append(P.relative(stale, base))

    if not quiet:
        print(f"酒馆卡导出：{len(written)} 张 → dist/{TAVERN_DIR}/<id>.json")
        for stale in removed:
            print(f"  清理过期产物 {stale}")
    return {"cards": len(written), "ids": written, "removed": removed}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="把 personas/ 导出成 SillyTavern Character Card V2 JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--root", default=None, help="仓库根目录（默认本文件上一级）")
    parser.add_argument("--quiet", action="store_true", help="只输出错误")
    args = parser.parse_args(list(argv) if argv is not None else None)

    started = time.time()
    try:
        export_all(Path(args.root) if args.root else None, quiet=args.quiet)
    except P.PersonaError as exc:
        print(f"导出失败：{exc}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"（耗时 {time.time() - started:.2f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
