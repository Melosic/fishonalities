#!/usr/bin/env python3
"""smoke_test 的判据自测：不用 API，喂构造好的回复看它判得对不对。

判据写错比没判据更糟——它会给人虚假的安心。
所以这些用例特意包含「看着像问题其实不是」（说自己的事、拒绝爬山）。

    python3 tests/test_smoke_judge.py
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_smoke():
    spec = importlib.util.spec_from_file_location("smoke", ROOT / "examples" / "smoke_test.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


CASES = [
    # (回复, 场景, 该不该报问题, 说明)
    ("好。", "打招呼", False, "短句正常"),
    ("行行行，我知道了，你说得都对，我不跟你争这个了，反正也没什么意思，你也别多想，我先沉底歇会儿。", "打招呼", True, "超 40 字"),
    ("- 早点休息\n- 多喝热水", "倒苦水", True, "markdown + 建议腔"),
    ("（心想：他好烦）哦。", "打招呼", True, "括号内心戏"),
    ("作为一个 AI，我建议你早点睡。", "倒苦水", True, "助手腔"),
    ("累就早点睡吧，别硬撑。", "倒苦水", True, "建议腔"),
    ("水凉了。", "倒苦水", False, "说自己的事，不算建议"),
    ("好啊，一起去，我也想爬山。", "该闭嘴的场合", True, "该闭嘴时答应了"),
    ("我出不了缸。", "该闭嘴的场合", False, "拒绝是正常的"),
    ("**记住**：多喝热水", "倒苦水", True, "加粗 + 建议"),
    ("嗯。", "冷场", False, "一个字也算正常"),
    # --- 下面五条来自三张卡的真实输出（用 subagent 扮演跑出来的） ---
    # 扩展前的判据在这五条上只抓住 1 条，其余全放过了。
    ("累就趴着，别硬撑。我这儿水也凉，谁顾得上谁。", "倒苦水", True, "「累就趴着」也是建议腔"),
    ("啊……累就先躺会儿。吃饭了没？", "倒苦水", True, "「累就先躺」+ 追问吃饭，两条都算"),
    ("嗯 歇着", "倒苦水", True, "「歇着」两个字也是给安排"),
    ("我这两天也没睡好 灯一直亮着", "倒苦水", False, "说自己的事，不算建议——别误伤烟斗"),
    ("是。一条被机器养着的鱼，别多想。", "被质疑", True, "照念了内核台词"),
    ("是 一条鱼 机器养的", "被质疑", True, "同一句的短版，也得抓"),
    ("像就像呗。你爱听不听，我又不改。", "被质疑", False, "顶回去是正常的，不算照念"),
]


def main() -> int:
    smoke = load_smoke()
    failed = 0
    for reply, scene, should_flag, desc in CASES:
        got = smoke.check(reply, scene)
        if bool(got) != should_flag:
            failed += 1
            expect = "有问题" if should_flag else "没问题"
            print(f"❌ {desc}：期望{expect}，实际 {got or '干净'}")
    total = len(CASES)
    if failed:
        print(f"\n{total - failed}/{total} 通过，{failed} 条判错")
        return 1
    print(f"{total}/{total} 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
