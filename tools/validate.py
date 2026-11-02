#!/usr/bin/env python3
"""校验 personas/ 下的全部人格卡。

用法：
    python3 tools/validate.py            # 按 schema 校验
    python3 tools/validate.py --strict    # 额外查文件名/目录/重复 id/通用词/助手腔/markdown
    python3 tools/validate.py --quiet     # 只打印错误和汇总

错误格式是「文件:字段:原因」，可以直接 Ctrl-Click 跳；有错退出码 1。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import personas as P  # noqa: E402


class Report(NamedTuple):
    """一次校验的完整结果。"""

    entries: List[Tuple[str, Dict[str, Any]]]  # 通过结构校验的 (相对路径, 卡)
    errors: List[Tuple[str, P.VError]]  # (相对路径, 错误)
    total: int  # 扫到的文件总数

    @property
    def passed(self) -> int:
        bad_files = {label for label, _ in self.errors}
        return len([label for label, _ in self.entries if label not in bad_files])

    @property
    def failed(self) -> int:
        return len({label for label, _ in self.errors})

    @property
    def ok(self) -> bool:
        return not self.errors


def collect(root: Optional[Path] = None, strict: bool = False) -> Report:
    """跑一遍全量校验，返回结构化结果（不打印、不退出）。"""
    base = P.resolve_root(root)
    entries: List[Tuple[str, Dict[str, Any]]] = []
    errors: List[Tuple[str, P.VError]] = []
    scanned = P.scan(base)

    try:
        schema = P.load_schema(base)
    except P.PersonaError as exc:
        return Report([], [("schema/persona.schema.json", P.VError("", str(exc)))], 0)

    for item in scanned:
        label = P.relative(item.path, base)
        if item.error is not None:
            errors.append((label, P.VError("(文件)", item.error)))
            continue
        assert item.data is not None
        data = item.data
        entries.append((label, data))

        for verr in P.validate_persona(data, schema=schema):
            errors.append((label, verr))
        if strict:
            for verr in P.identity_checks(data, item.path):
                errors.append((label, verr))
            for verr in P.style_checks(data):
                errors.append((label, verr))

    if strict:
        for label, verr in P.duplicate_id_errors(entries):
            errors.append((label, verr))

    if not scanned:
        errors.append(
            (
                P.PERSONA_DIRNAME + "/",
                P.VError("", "一个人格卡都没找到（期望 personas/<archetype>/<id>.yaml）"),
            )
        )
    return Report(entries, errors, len(scanned))


def format_error(label: str, verr: P.VError) -> str:
    field = verr.field if verr.field else "(根)"
    return f"{label}:{field}:{verr.message}"


def print_report(report: Report, root: Optional[Path] = None, quiet: bool = False) -> None:
    for label, verr in report.errors:
        print(format_error(label, verr))

    if report.errors and not quiet:
        print("")
    summary = f"通过 {report.passed} / 失败 {report.failed}（共 {report.total} 张卡）"
    if report.errors:
        print(f"{summary}  ← 修完再提，详见上面的错误行")
    else:
        print(summary)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="校验 personas/ 下的人格卡是否符合 schema/persona.schema.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--strict", action="store_true", help="额外执行文件名/唯一性/文风检查")
    parser.add_argument("--quiet", action="store_true", help="只打印错误和汇总")
    parser.add_argument(
        "--root", default=None, help="仓库根目录（默认是本文件所在目录的上一级）"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    started = time.time()
    report = collect(Path(args.root) if args.root else None, strict=args.strict)
    print_report(report, quiet=args.quiet)
    elapsed = time.time() - started
    if not args.quiet:
        mode = "strict" if args.strict else "schema"
        print(f"（{mode} 模式，耗时 {elapsed:.2f}s）")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
