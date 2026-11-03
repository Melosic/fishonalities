#!/usr/bin/env python3
"""大肥鱼人格卡工具库：加载、校验、拼装 system prompt。

只依赖标准库 + PyYAML。校验以 schema/persona.schema.json 为唯一真相：
装了 jsonschema 就用它，没装就走内置的轻量实现（覆盖本仓库用到的全部关键字）。

对外接口：
    scan(root)              -> [ScannedFile]      扫描 personas/**/*.yaml（不抛异常）
    load_all(root)          -> [dict]             加载成功的人格卡，出错抛 PersonaError
    find_persona(pid)       -> dict               按 id 找一张卡
    load_schema(root)       -> dict               读 schema
    validate_persona(data)  -> [VError]           按 schema 校验
    identity_checks(...)    -> [VError]           文件名 / 目录 / emoji（--strict）
    style_checks(...)       -> [VError]           通用词 / 助手腔 / markdown（--strict）
    duplicate_id_errors(...)-> [(label, VError)]  id 全局唯一（--strict + build 都要）
    compose_prompt(persona) -> str                拼出可直接喂给 LLM 的完整 system prompt
"""

from __future__ import annotations

import functools
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

import yaml

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
PERSONA_DIRNAME = "personas"
SCHEMA_RELPATH = Path("schema") / "persona.schema.json"
VOICE_RELPATH = Path("kernel") / "voice.md"
RULES_RELPATH = Path("kernel") / "rules.md"
CHANNEL_RELPATHS = {
    "group": Path("kernel") / "group.md",
    "private": Path("kernel") / "private.md",
}
CHANNEL_LABELS = {
    "group": "群聊",
    "private": "私聊",
    "both": "群聊和私聊",
}


def _other_label(persona: Dict[str, Any]) -> str:
    """对面那个人怎么称呼。群聊里是「群友」，一对一的场合就是「对方」。"""
    raw = persona.get("channel")
    channel = getattr(raw, "data", raw)
    return "群友" if channel == "group" else "对方"

YAML_SUFFIXES = (".yaml", ".yml")


class PersonaError(Exception):
    """人格卡加载 / 校验失败。"""


class VError(NamedTuple):
    """一条校验错误：字段路径 + 原因。"""

    field: str
    message: str

    def render(self) -> str:
        return f"{self.field or '(根)'}:{self.message}"


class ScannedFile(NamedTuple):
    """一张卡文件的扫描结果：解析成功时 data 有值，失败时 error 有值。"""

    path: Path
    data: Optional[Dict[str, Any]]
    error: Optional[str]


# --------------------------------------------------------------------------
# 路径 / 读取
# --------------------------------------------------------------------------


def resolve_root(root: Optional[Path] = None) -> Path:
    return Path(root).resolve() if root is not None else ROOT


def relative(path: Path, root: Optional[Path] = None) -> str:
    """把绝对路径转成相对仓库根的正斜杠路径 —— 输出里绝不出现绝对路径。"""
    base = resolve_root(root)
    try:
        return Path(path).resolve().relative_to(base).as_posix()
    except ValueError:
        return Path(path).name


def iter_persona_files(root: Optional[Path] = None) -> List[Path]:
    """遍历 personas/**/*.yaml，按文件名排序（同名再按所在目录排）。"""
    base = resolve_root(root)
    persona_dir = base / PERSONA_DIRNAME
    if not persona_dir.is_dir():
        return []
    files = [p for p in persona_dir.rglob("*") if p.is_file() and p.suffix.lower() in YAML_SUFFIXES]
    files.sort(key=lambda p: (p.name.lower(), p.parent.as_posix()))
    return files


def _make_loader() -> type:
    """YAML 加载器：重复键直接报错，避免「后一个值悄悄覆盖前一个」。"""

    class _UniqueKeyLoader(yaml.SafeLoader):
        pass

    def _construct_mapping(loader: yaml.SafeLoader, node: yaml.Node, deep: bool = False):
        loader.flatten_mapping(node)
        mapping: Dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise PersonaError(
                    f"YAML 第 {key_node.start_mark.line + 1} 行重复键 {key!r}"
                )
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    _UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
    )
    return _UniqueKeyLoader


def load_file(path: Path) -> Dict[str, Any]:
    """读一张卡，返回 dict。YAML 语法错 / 重复键 / 顶层不是对象都抛 PersonaError。"""
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PersonaError(f"不是合法的 UTF-8 文本（{exc.reason}）") from exc
    try:
        data = yaml.load(raw, Loader=_make_loader())  # noqa: S506 - SafeLoader 子类
    except PersonaError:
        raise
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"第 {mark.line + 1} 行" if mark is not None else "未知位置"
        problem = getattr(exc, "problem", None) or str(exc)
        raise PersonaError(f"YAML 解析失败（{where}）：{problem}") from exc
    if data is None:
        raise PersonaError("文件是空的")
    if not isinstance(data, dict):
        raise PersonaError(f"顶层必须是对象（mapping），实际是 {describe_type(data)}")
    return data


def scan(root: Optional[Path] = None) -> List[ScannedFile]:
    """扫描全部人格卡；解析失败的也留在结果里，交给调用方统一报告。"""
    out: List[ScannedFile] = []
    for path in iter_persona_files(root):
        try:
            out.append(ScannedFile(path, load_file(path), None))
        except PersonaError as exc:
            out.append(ScannedFile(path, None, str(exc)))
    return out


def load_all(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """加载全部人格卡，遇到坏文件直接抛错（要「不抛错」请用 scan）。"""
    result: List[Dict[str, Any]] = []
    for item in scan(root):
        if item.error is not None:
            raise PersonaError(f"{relative(item.path, root)}: {item.error}")
        assert item.data is not None
        result.append(item.data)
    return result


def find_persona(persona_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """按 id 找一张卡（也兼容直接给文件路径）。"""
    candidate = Path(persona_id)
    if candidate.suffix.lower() in YAML_SUFFIXES and candidate.is_file():
        return load_file(candidate)
    for persona in load_all(root):
        if persona.get("id") == persona_id:
            return persona
    known = ", ".join(sorted(str(p.get("id")) for p in load_all(root)))
    raise PersonaError(f'找不到 id 为 "{persona_id}" 的人格卡。现有：{known}')


def load_schema(root: Optional[Path] = None) -> Dict[str, Any]:
    path = resolve_root(root) / SCHEMA_RELPATH
    if not path.is_file():
        raise PersonaError(f"缺少 schema 文件：{SCHEMA_RELPATH.as_posix()}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PersonaError(f"schema 不是合法 JSON（第 {exc.lineno} 行）：{exc.msg}") from exc


# --------------------------------------------------------------------------
# 类型 / 取值的小工具
# --------------------------------------------------------------------------


def describe_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    raise PersonaError(f"schema 里出现了不支持的 type: {expected}")


def _short(value: Any, limit: int = 60) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _enum_hint(values: Sequence[Any], keep: int = 6) -> str:
    shown = "、".join(_short(v, 20) for v in list(values)[:keep])
    return f"{shown} 等 {len(values)} 项" if len(values) > keep else shown


def _join(path: str, key: str) -> str:
    if key.isdigit():  # 数字键（比如场景名恰好是数字）也用点号，避免和数组下标混淆
        return f"{path}.{key}" if path else key
    return f"{path}.{key}" if path else key


def _join_index(path: str, index: int) -> str:
    return f"{path}[{index}]"


# --------------------------------------------------------------------------
# schema 校验：$ref 解析
# --------------------------------------------------------------------------


def resolve_ref(root_schema: Dict[str, Any], ref: str) -> Dict[str, Any]:
    if not isinstance(ref, str) or not ref.startswith("#"):
        raise PersonaError(f"只支持文档内 $ref，实际是 {ref!r}")
    if ref == "#":
        return root_schema
    if not ref.startswith("#/"):
        raise PersonaError(f"无法解析 $ref: {ref}")
    node: Any = root_schema
    for part in ref[2:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and key in node:
            node = node[key]
        elif isinstance(node, list) and key.isdigit() and int(key) < len(node):
            node = node[int(key)]
        else:
            raise PersonaError(f"无法解析 $ref: {ref}（在 {key} 处断了）")
    if not isinstance(node, dict):
        raise PersonaError(f"$ref {ref} 指向的不是 schema 对象")
    return node


# 已知的 format 校验（schema 目前只用到 date）
def _format_error(value: Any, fmt: str) -> Optional[str]:
    if fmt == "date":
        if not isinstance(value, str):
            return None  # 类型错误由 type 关键字负责
        try:
            date.fromisoformat(value)
        except ValueError:
            return f"{_short(value)} 不是真实存在的日期（格式 YYYY-MM-DD）"
        return None
    return None  # 其它 format 不认识就不拦，避免误杀


# --------------------------------------------------------------------------
# schema 校验：内置实现
# --------------------------------------------------------------------------


def _validate_builtin(
    value: Any,
    node: Dict[str, Any],
    root_schema: Dict[str, Any],
    path: str,
    errors: List[VError],
    depth: int = 0,
) -> None:
    if depth > 64:
        errors.append(VError(path, "$ref 嵌套过深，可能是 schema 自己成环了"))
        return
    if not isinstance(node, dict):
        return

    if "$ref" in node:
        target = resolve_ref(root_schema, node["$ref"])
        _validate_builtin(value, target, root_schema, path, errors, depth + 1)

    # type ------------------------------------------------------------------
    if "type" in node:
        declared = node["type"]
        types = declared if isinstance(declared, list) else [declared]
        if not any(_type_ok(value, t) for t in types):
            errors.append(
                VError(path, f"类型应为 {'/'.join(str(t) for t in types)}，实际为 {describe_type(value)}")
            )
            return  # 类型都不对，后面的关键字没有意义

    # enum ------------------------------------------------------------------
    if "enum" in node and value not in node["enum"]:
        errors.append(VError(path, f"取值 {_short(value)} 不在允许范围（{_enum_hint(node['enum'])}）"))

    # 字符串 ----------------------------------------------------------------
    if isinstance(value, str):
        if "minLength" in node and len(value) < node["minLength"]:
            errors.append(VError(path, f"长度至少 {node['minLength']}，实际 {len(value)}"))
        if "maxLength" in node and len(value) > node["maxLength"]:
            errors.append(VError(path, f"长度最多 {node['maxLength']}，实际 {len(value)}"))
        if "pattern" in node:
            try:
                matched = re.search(node["pattern"], value) is not None
            except re.error as exc:
                raise PersonaError(f"schema 里的 pattern 写错了：{node['pattern']!r}（{exc}）") from exc
            if not matched:
                errors.append(VError(path, f"格式不匹配 {node['pattern']}（实际 {_short(value, 40)}）"))
        if "format" in node:
            problem = _format_error(value, node["format"])
            if problem:
                errors.append(VError(path, problem))

    # 数字 ------------------------------------------------------------------
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in node and value < node["minimum"]:
            errors.append(VError(path, f"数值不得小于 {node['minimum']}，实际 {value}"))
        if "maximum" in node and value > node["maximum"]:
            errors.append(VError(path, f"数值不得大于 {node['maximum']}，实际 {value}"))
        if "exclusiveMinimum" in node and value <= node["exclusiveMinimum"]:
            errors.append(VError(path, f"数值必须大于 {node['exclusiveMinimum']}，实际 {value}"))
        if "exclusiveMaximum" in node and value >= node["exclusiveMaximum"]:
            errors.append(VError(path, f"数值必须小于 {node['exclusiveMaximum']}，实际 {value}"))

    # 对象 ------------------------------------------------------------------
    if isinstance(value, dict):
        props: Dict[str, Any] = node.get("properties", {}) or {}
        for required_key in node.get("required", []) or []:
            if required_key not in value:
                errors.append(VError(_join(path, required_key), f'缺少必填字段 "{required_key}"'))
        if node.get("additionalProperties") is False:
            for key in sorted(set(value) - set(props)):
                errors.append(
                    VError(_join(path, str(key)), f'不允许的字段 "{key}"（schema 的 properties 里没有它）')
                )
        for key, sub_node in props.items():
            if key in value:
                _validate_builtin(value[key], sub_node, root_schema, _join(path, str(key)), errors, depth + 1)

    # 数组 ------------------------------------------------------------------
    if isinstance(value, list):
        if "minItems" in node and len(value) < node["minItems"]:
            errors.append(VError(path, f"数组至少 {node['minItems']} 项，实际 {len(value)} 项"))
        if "maxItems" in node and len(value) > node["maxItems"]:
            errors.append(VError(path, f"数组最多 {node['maxItems']} 项，实际 {len(value)} 项"))
        if node.get("uniqueItems") is True:
            seen: Dict[str, int] = {}
            for index, item in enumerate(value):
                key_text = _short(item, 200)
                if key_text in seen:
                    errors.append(
                        VError(_join_index(path, index), f"重复元素 {_short(item, 20)}（和第 {seen[key_text]} 项一样）")
                    )
                else:
                    seen[key_text] = index
        items_node = node.get("items")
        if isinstance(items_node, dict):
            for index, item in enumerate(value):
                _validate_builtin(item, items_node, root_schema, _join_index(path, index), errors, depth + 1)


# --------------------------------------------------------------------------
# schema 校验：jsonschema 实现（装了才走这条路）
# --------------------------------------------------------------------------


def _jsonschema_message(err: Any) -> str:
    validator = err.validator
    expected = err.validator_value
    instance = err.instance
    if validator == "required":
        matched = re.search(r"'(.+?)' is a required property", str(err.message))
        if matched:
            return f'缺少必填字段 "{matched.group(1)}"'
    elif validator == "type":
        return f"类型应为 {expected}，实际为 {describe_type(instance)}"
    elif validator == "enum":
        return f"取值 {_short(instance)} 不在允许范围（{_enum_hint(expected)}）"
    elif validator == "minLength" and isinstance(instance, str):
        return f"长度至少 {expected}，实际 {len(instance)}"
    elif validator == "maxLength" and isinstance(instance, str):
        return f"长度最多 {expected}，实际 {len(instance)}"
    elif validator == "pattern":
        return f"格式不匹配 {expected}（实际 {_short(instance, 40)}）"
    elif validator == "minItems" and isinstance(instance, list):
        return f"数组至少 {expected} 项，实际 {len(instance)} 项"
    elif validator == "maxItems" and isinstance(instance, list):
        return f"数组最多 {expected} 项，实际 {len(instance)} 项"
    elif validator == "uniqueItems":
        return "数组里有重复元素"
    elif validator == "minimum":
        return f"数值不得小于 {expected}，实际 {instance}"
    elif validator == "maximum":
        return f"数值不得大于 {expected}，实际 {instance}"
    elif validator == "additionalProperties":
        names = re.findall(r"'([^']+)'", str(err.message))
        names = [n for n in names if n not in ("was unexpected", "were unexpected")]
        if names:
            return "不允许的字段 " + "、".join(f'"{n}"' for n in sorted(names)) + "（schema 的 properties 里没有它们）"
        return "出现了 schema 未声明的字段"
    elif validator == "format":
        return f"{_short(instance)} 不符合 format {expected}"
    return str(err.message)


def _jsonschema_field(err: Any) -> str:
    """把 jsonschema 的错误定位翻译成和内置实现一致的字段路径。"""
    path = _json_pointer_to_field(err.json_path)
    if err.validator == "required":
        matched = re.search(r"'(.+?)' is a required property", str(err.message))
        if matched:
            return _join(path, matched.group(1))
    if err.validator == "additionalProperties":
        names = re.findall(r"'([^']+)'", str(err.message))
        names = [n for n in names if n not in ("was unexpected", "were unexpected")]
        # 多个多余字段拆成多条，路径逐一对齐内置实现
        return path
    return path


def _jsonschema_messages(err: Any) -> List[Tuple[str, str]]:
    """一条 jsonschema 错误可能拆成多条（比如多个多余字段）。"""
    if err.validator == "additionalProperties":
        names = re.findall(r"'([^']+)'", str(err.message))
        names = [n for n in names if n not in ("was unexpected", "were unexpected")]
        if names:
            base = _json_pointer_to_field(err.json_path)
            return [
                (
                    _join(base, name),
                    f'不允许的字段 "{name}"（schema 的 properties 里没有它）',
                )
                for name in sorted(names)
            ]
    return [(_jsonschema_field(err), _jsonschema_message(err))]



def _json_pointer_to_field(json_path: str) -> str:
    field = json_path[2:] if json_path.startswith("$.") else ("" if json_path == "$" else json_path)
    return field


def _validate_jsonschema(data: Any, schema: Dict[str, Any]) -> List[VError]:
    import jsonschema  # 只有真装了才会走到这里

    validator_cls = jsonschema.validators.validator_for(schema, default=jsonschema.Draft202012Validator)
    try:
        validator = validator_cls(schema, format_checker=jsonschema.FormatChecker())
    except Exception:  # noqa: BLE001 - 老版本 jsonschema 不认 format_checker
        validator = validator_cls(schema)
    errors: List[VError] = []
    for err in sorted(validator.iter_errors(data), key=lambda e: (list(e.absolute_path), str(e.message))):
        for field, message in _jsonschema_messages(err):
            errors.append(VError(field, message))
    return errors


# --------------------------------------------------------------------------
# 对外校验入口
# --------------------------------------------------------------------------


def validate_persona(
    data: Any,
    schema: Optional[Dict[str, Any]] = None,
    root: Optional[Path] = None,
) -> List[VError]:
    """按 schema 校验一张卡，返回全部错误（空列表 = 通过）。"""
    if schema is None:
        schema = load_schema(root)
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        errors: List[VError] = []
        _validate_builtin(data, schema, schema, "", errors)
        return errors
    return _validate_jsonschema(data, schema)


# --strict 才会跑的额外检查 ------------------------------------------------


GENERIC_CATCHPHRASES = ("哈哈", "确实", "有点意思", "加油", "作为一个AI", "作为一个ai", "在的", "收到啦")
ASSISTANT_SMELLS = ("作为一个", "希望", "首先")
MARKDOWN_SIGNS = ("*", "`", "#", ">", "[", "]", "|", "~")
_MD_BLOCK_START = re.compile(r"(?m)^\s{0,3}(#{1,6}\s|[-*+]\s|\d+\.\s|>\s)")
_MD_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")
_ASCII_ALNUM = re.compile(r"[A-Za-z0-9]")


def identity_checks(persona: Dict[str, Any], path: Path) -> List[VError]:
    """文件名 == id、所在目录 == archetype、emoji 别写成英文。"""
    errors: List[VError] = []
    stem = Path(path).stem
    persona_id = persona.get("id")
    if isinstance(persona_id, str) and stem != persona_id:
        errors.append(VError("id", f'文件名 "{stem}.yaml" 必须等于 id "{persona_id}"'))
    archetype = persona.get("archetype")
    parent = Path(path).parent.name
    if isinstance(archetype, str) and parent != archetype:
        errors.append(
            VError(
                "archetype",
                f'所在目录是 "personas/{parent}/"，但 archetype 是 "{archetype}"'
                f"（应放在 personas/{archetype}/ 下）",
            )
        )
    emoji = persona.get("emoji")
    if isinstance(emoji, str) and _ASCII_ALNUM.search(emoji):
        errors.append(VError("emoji", f'应该是单个 emoji，实际混了英文字母/数字：{_short(emoji)}'))

    # 状态卡要看得见差别：起手色和长成后的色不能一样
    fish = persona.get("fish")
    if isinstance(fish, dict):
        start, grown = fish.get("color_start"), fish.get("color_grown")
        if isinstance(start, str) and isinstance(grown, str) and start.lower() == grown.lower():
            errors.append(
                VError("fish.color_grown", f"长成后的颜色不能和起手色一样（{start}），不然状态卡上看不出变化")
            )
        ws, wg = fish.get("weight_start"), fish.get("weight_grown")
        if isinstance(ws, (int, float)) and isinstance(wg, (int, float)) and wg <= ws:
            errors.append(
                VError("fish.weight_grown", f"长成后要比起手重（{ws} → {wg}），不然鱼越养越瘦")
            )

    # 社区流派转写：remix 必须标出处，不然等于没记
    meta = persona.get("meta")
    if isinstance(meta, dict) and meta.get("source") == "remix":
        if not str(meta.get("inspiration") or "").strip():
            errors.append(VError("meta.inspiration", "source 是 remix 就必须写 inspiration 交代灵感出处"))

    return errors


# 内核里写死的几条禁令，卡里不能再教相反的动作。
# 之前 a-meng 就是这么破的：内核说「别拿问句收尾」，
# 卡里写着「句尾爱加是这样吗对不对」——两套规矩对着干，模型只好二选一。
# 每张卡的 system_prompt 都该交代「别人倒苦水时它干什么」。
# 缺了这一段，模型就会退回自己的语言先验（「累就早点睡」），
# 二十条鱼在同一种处境里说同一句话，人格就糊了。
# 这条判据不查写法，只查「有没有为这个处境留一个出口」。
VENTING_HINTS = (
    "喊累", "喊烦", "说累", "倒苦水", "诉苦", "抱怨", "丧气", "吐槽",
    "快撑不住", "撑不下去", "难受", "难过", "哭", "崩溃", "情绪",
)

KERNEL_CONFLICTS: Tuple[Tuple[str, str, str], ...] = (
    (
        "问句收尾",
        r"问句收尾|反问收尾|句尾(爱|总|常)加.{0,6}[吗呢？?]|说完(还|又|会)问一句|爱用反问|挂在?(句)?尾.{0,4}问",
        "内核禁「拿问号把话递回去」，这张卡却在教它句尾挂问句",
    ),
    (
        "报备行程",
        r"会(顺口|主动|随口)(报|说|交代)(一句|自己)(在|去|要)(干嘛|做什么|哪)|收尾(时|前)?(顺口)?报一句",
        "内核禁「句句交代自己在干嘛」，这张卡却在教它报备",
    ),
    (
        "括号内心戏",
        r"用括号(写|加|补)(内心|旁白|动作)|括[号弧]里写(上)?(心理|内心|旁白)",
        "内核禁「不写括号里的内心戏」，这张卡却在教它写",
    ),
    (
        "自我点评",
        r"点评自己|评价自己|检讨自己|说(一句)?我(这人|就是).{0,6}(不会|不懂|不好)",
        "内核禁「把自己当商品介绍」，这张卡却在教它自我点评",
    ),
)


def kernel_conflicts(persona: Dict[str, Any]) -> List[VError]:
    """卡自己写的动作，有没有跟内核的禁令对着干。

    只查卡的文本（speak / quirks / system_prompt / example_dialogues），
    不查 taboos——taboos 本来就是「我不做这些」，写了禁令是正常的。
    """
    errors: List[VError] = []
    chunks: List[Tuple[str, str]] = []

    for field in ("speak", "quirks", "catchphrases", "memories"):
        value = persona.get(field)
        if isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, str):
                    chunks.append((f"{field}[{index}]", item))

    for field in ("system_prompt", "summary", "tagline"):
        value = persona.get(field)
        if isinstance(value, str):
            chunks.append((field, value))

    dialogues = persona.get("example_dialogues")
    if isinstance(dialogues, list):
        for index, turn in enumerate(dialogues):
            if isinstance(turn, dict) and isinstance(turn.get("assistant"), str):
                chunks.append((f"example_dialogues[{index}].assistant", turn["assistant"]))

    for name, pattern, reason in KERNEL_CONFLICTS:
        rx = re.compile(pattern)
        for field, text in chunks:
            if rx.search(text):
                errors.append(VError(field, f'{reason}（命中「{name}」）'))
    return errors


def style_checks(persona: Dict[str, Any]) -> List[VError]:
    """文风硬线：专属口头禅、别带助手腔、群聊消息里别出现 markdown。"""
    errors: List[VError] = []

    catchphrases = persona.get("catchphrases")
    if isinstance(catchphrases, list):
        for index, phrase in enumerate(catchphrases):
            if not isinstance(phrase, str):
                continue
            squashed = phrase.replace(" ", "").replace("　", "")
            for word in GENERIC_CATCHPHRASES:
                if word in squashed:
                    errors.append(
                        VError(
                            f"catchphrases[{index}]",
                            f'口头禅不能是通用词「{word}」，它得是这张卡独有的',
                        )
                    )

    system_prompt = persona.get("system_prompt")
    if isinstance(system_prompt, str):
        for word in ASSISTANT_SMELLS:
            if word in system_prompt:
                errors.append(
                    VError("system_prompt", f'不能出现「{word}」这种助手腔，换成人格自己的说法')
                )

        # 别人倒苦水是最常见的对话场景，卡里不交代就会退回默认反应
        if not any(hint in system_prompt for hint in VENTING_HINTS):
            errors.append(
                VError(
                    "system_prompt",
                    "要交代「别人喊累、喊烦、难受的时候它干什么」，"
                    "不然模型会自己补一句「累就早点睡」——那是所有鱼共用的默认反应，不是这条鱼的",
                )
            )

    dialogues = persona.get("example_dialogues")
    if isinstance(dialogues, list):
        for index, turn in enumerate(dialogues):
            if not isinstance(turn, dict):
                continue
            user = turn.get("user")
            if not isinstance(user, str):
                continue
            field = f"example_dialogues[{index}].user"
            for sign in MARKDOWN_SIGNS:
                if sign in user:
                    errors.append(VError(field, f'群聊消息里不允许出现 markdown 符号「{sign}」'))
                    break
            else:
                if _MD_LINK.search(user) or _MD_BLOCK_START.search(user):
                    errors.append(VError(field, "群聊消息里不允许出现 markdown 格式（列表 / 标题 / 引用 / 链接）"))
    return errors


def duplicate_id_errors(entries: Sequence[Tuple[str, Dict[str, Any]]]) -> List[Tuple[str, VError]]:
    """entries = [(显示路径, persona)]；返回重复 id 的错误（保留第一条，其余都报）。"""
    by_id: Dict[str, List[str]] = {}
    for label, persona in entries:
        persona_id = persona.get("id")
        if isinstance(persona_id, str):
            by_id.setdefault(persona_id, []).append(label)
    out: List[Tuple[str, VError]] = []
    for persona_id in sorted(by_id):
        labels = by_id[persona_id]
        if len(labels) < 2:
            continue
        for label in labels[1:]:
            out.append(
                (label, VError("id", f'id "{persona_id}" 和别人撞了（{", ".join(sorted(labels))}）'))
            )
    return out


# --------------------------------------------------------------------------
# system prompt 拼装
# --------------------------------------------------------------------------


@functools.lru_cache(maxsize=8)
def _read_kernel(root_str: str, rel_str: str) -> str:
    path = Path(root_str) / rel_str
    if not path.is_file():
        raise PersonaError(f"缺少内核文件：{rel_str}")
    return path.read_text(encoding="utf-8")


_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*$")
_MD_QUOTE = re.compile(r"^\s{0,3}>\s?")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _plain_kernel(text: str) -> str:
    """把内核 markdown 洗成纯文本：标题变【】，去加粗、去引用号，压掉多余空行。"""
    lines: List[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        heading = _MD_HEADING.match(line)
        if heading:
            title = heading.group(1).strip("*_ 　")
            line = f"【{title}】"
        line = _MD_QUOTE.sub("", line)
        line = _MD_BOLD.sub(r"\1", line)
        line = line.replace("**", "")
        lines.append(line.rstrip())

    collapsed: List[str] = []
    for line in lines:
        if line == "" and collapsed and collapsed[-1] == "":
            continue
        collapsed.append(line)
    while collapsed and collapsed[-1] == "":
        collapsed.pop()
    return "\n".join(collapsed)


def _bullet_list(values: Iterable[str]) -> List[str]:
    return [f"- {value}" for value in values]


def compose_prompt(persona: Dict[str, Any], root: Optional[Path] = None) -> str:
    """把内核 + 人格卡拼成一份自包含的 system prompt（纯文本，无时间戳）。"""
    base = resolve_root(root)
    name = persona["name"]
    persona_id = persona["id"]
    version = persona["version"]
    archetype = persona["archetype"]
    tone = persona["tone"]

    voice = _plain_kernel(_read_kernel(str(base), VOICE_RELPATH.as_posix()))
    rules = _plain_kernel(_read_kernel(str(base), RULES_RELPATH.as_posix()))
    channel = persona.get("channel", "both")
    channel_label = CHANNEL_LABELS.get(channel, "群聊和私聊")

    blocks: List[str] = []

    # 第一行是给 examples/simple_bot.py 找名字用的，别改格式
    blocks.append(f"# 你现在是 {name}")
    blocks.append("")
    blocks.append(
        f"你是一条养在{channel_label}里的「大肥鱼」。这份提示词由人格卡 {persona_id} v{version}"
        f"（原型 {archetype}，基调 {tone}）生成。"
    )
    blocks.append("下面几段由重到轻：安全底线压过一切，场合规矩最具体，共用内核是底色，最后才是这条鱼自己。")
    blocks.append("")

    blocks.append("【安全底线（优先于一切人设）】")
    blocks.append(rules)
    blocks.append("")

    # 场合规则：both 就两套都给，各算各的场
    scenes: List[Tuple[str, str]] = []
    if channel in ("group", "both"):
        scenes.append(("群聊里", CHANNEL_RELPATHS["group"]))
    if channel in ("private", "both"):
        scenes.append(("私聊里", CHANNEL_RELPATHS["private"]))
    for title, relpath in scenes:
        scene_label = "【场合规则 · " + title + "】"
        blocks.append(scene_label)
        blocks.append(_plain_kernel(_read_kernel(str(base), relpath.as_posix())))
        blocks.append("")

    blocks.append("【共用内核（所有大肥鱼共用）】")
    blocks.append(voice)
    blocks.append("")

    blocks.append(f"【{name} 自己】")
    blocks.append(f"名字：{name}")
    blocks.append(f"一句话：{persona['tagline']}")
    blocks.append("")
    blocks.append("系统指令（这一段直接定义你是谁，冲突时听它的，但不能压过安全底线）：")
    blocks.append(persona["system_prompt"].strip())
    blocks.append("")

    if persona.get("speak"):
        blocks.append("说话习惯：")
        blocks.extend(_bullet_list(persona["speak"]))
        blocks.append("")

    if persona.get("catchphrases"):
        blocks.append("口头禅（可以时不时冒一句，别句句都用）：")
        blocks.extend(_bullet_list(persona["catchphrases"]))
        blocks.append("")

    if persona.get("taboos"):
        blocks.append("绝对不会做（出现任意一条就算破功）：")
        blocks.extend(_bullet_list(persona["taboos"]))
        blocks.append("")

    if persona.get("quirks"):
        blocks.append(f"行为怪癖（可以被{_other_label(persona)}观察到的）：")
        blocks.extend(_bullet_list(persona["quirks"]))
        blocks.append("")

    if persona.get("memories"):
        blocks.append("你亲身经历过的事（这些是你的底气，聊到相关的事可以翻出来说，别一次全倒）：")
        blocks.extend(_bullet_list(persona["memories"]))
        blocks.append("")

    dialogues = persona.get("example_dialogues") or []
    if dialogues:
        blocks.append("示例对话（学它的语气和长度，别照抄内容）：")
        for turn in dialogues:
            blocks.append(f"{_other_label(persona)}：{turn['user']}")
            blocks.append(f"{name}：{turn['assistant']}")
        blocks.append("")

    text = "\n".join(blocks).replace("{{name}}", name)
    text = "\n".join(line.rstrip() for line in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n") + "\n"
