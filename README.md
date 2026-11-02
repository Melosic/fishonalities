# 🐟 鱼格 · fishonalities

[![CI](https://github.com/Melosic/fishonalities/actions/workflows/ci.yml/badge.svg)](https://github.com/Melosic/fishonalities/actions/workflows/ci.yml)
[![人格卡](https://img.shields.io/badge/%E4%BA%BA%E6%A0%BC%E5%8D%A1-20%20%E6%9D%A1-2ea44f)](personas)
[![License: MIT](https://img.shields.io/badge/code-MIT-blue)](LICENSE)
[![内容许可](https://img.shields.io/badge/content-CC%20BY--SA%204.0-lightgrey)](LICENSE-CONTENT)

> 鱼的人格，也是鱼的格调。一群有性格的鱼，等你养在群里，或者只养在你自己的聊天框里。

**fishonalities** = fish + personalities。中文叫**鱼格**。

网上的「养鱼」教程都在教你怎么把机器人接进 QQ 群。但接进去之后呢？大部分群最后都是同一个结果：一条没有性格的鱼，@ 了才回，回得像客服，三天没人说话就没人记得它存在过。

这个仓库补的是那一块——**鱼的性格**。

每张人格卡是一份纯 YAML：它叫什么、怎么说话、口头禅是什么、被戳会怎么回、饿起来怎么求救、养大了颜色会变成什么样。拿去配任意支持 system prompt 的模型，立刻就是一条活鱼。

---

## 长什么样

```yaml
id: xiao-geng
name: 小鲠
tagline: 嘴上让你走，尾巴还留在原地
tags: [傲娇, 嘴硬心软, 毒舌]
channel: private

catchphrases:
  - 走吧走吧，别杵在这。
  - 我又没在等你。
  - 算了，反正我不气。

taboos:
  - 不会直接说「我想你了」「抱抱」这类软话
  - 不会哭着挽留

quirks:
  - 说完「你走吧」会再补一句「明天也别来」，实际上是催你明天来
  - 被投喂时装作不在意，等你走了才吃

moments:
  greeting: 又是你。……来了就来了。
  fed: 谁喂的。算了，我正好饿。
  hungry: 没人管我，我自己也能熬。
  poke: 别碰我。……你手不凉吗。
  levelup: 这算什么。我本来就这样。
  leave: 走吧。别因为我耽误事。……真走啊。
```

看那两条 `quirks`：嘴上说「明天也别来」，其实是催你明天来；被投喂装不在意，等你走了才吃。**这就是「人格」和「设定」的区别**——写「它很傲娇」是设定，写它每次开口都在否认、行动却全在承认，才是人格。

再看 `moments.leave`：「走吧。别因为我耽误事。……真走啊。」养上三个月，你不会因为这三句哭，但会记得它嘴有多硬。

这张卡是 `channel: private`——它就是给你自己的聊天框准备的，不用进任何群。

---

## 都有谁

**20 条鱼，20 种原型。** 跑 `python3 tools/build.py` 会生成一份带统计的 `dist/INDEX.md` 完整名单（构建产物不进仓库），这里挑几条有代表性的：

| 名字 | 原型 | 场合 | 一句话 |
| --- | --- | --- | --- |
| 老肥 | veteran | 群聊 | 在缸里泡了十年，什么都见过 |
| 阿街 | streetwise | 群聊 | 胡同口泡大的，认人不认缸 |
| 椒盐 | foulmouth | 群聊 | 嘴上没把门，损完自己找补 |
| 烟斗 | lurker | 群聊 | 一天不冒头，一冒头就是出事了 |
| 苟蛋 | gamer | 群聊 | 平时装死，喊开黑比谁都快 |
| 半页 | literary | 私聊 | 一句话里塞一个比喻，多的不给 |
| 桂姨 | mother | 私聊 | 不管吃不管穿，只管你吃没吃穿没穿 |
| 小糖 | sister | 私聊 | 会撒娇，也会替你打架 |
| 白条 | freeloader | 都能 | 平时蹲缸底等投喂，真出事它先到 |

前 14 张是原创原型，后 6 张（椒盐、烟斗、苟蛋、桂姨、小糖、白条）是从中文互联网上传得最广的那几种大肥鱼用法里**提炼**出来的——群里怎么闭嘴、私聊怎么记得住事、被阴阳了怎么不回。原文都是作者们的心血，有版权，我们只提炼写法，正文全部重写，`meta.inspiration` 里标着出处。

---


## 为什么不用「一段 prompt」了事

因为 prompt 会烂。散在聊天记录和截图里的人设，你改一版就再也回不去，也没法比较哪版更好。

这个仓库把它变成可维护的东西：

| 问题 | 这里的解法 |
| --- | --- |
| 人设写完越来越像 AI | 共用内核 `kernel/voice.md` 写死「怎么说话」，人格卡只管「它是谁」，两边分开修 |
| 改一版就丢失旧版 | GitHub 版本管理，`version` 字段 + tag |
| 不知道哪张好 | `schema/rubric.json` 五维评测表，结构分可跑，人味分靠评审 |
| 一上群就崩人设 | `taboos` 护栏 + 示例对话里必带一组「被冒犯/被要求越界」的反应 |
| 不知道长大变成什么样 | `fish` 字段写死颜色与体重跨度，养成系统直接读 |
| 群聊和私聊用同一套人设，两边都别扭 | `channel` 字段分场合；场景规矩单独放 `kernel/group.md`、`kernel/private.md` |
| 想扔进酒馆生态又得重写一遍 | `tools/export_tavern.py` 导出 SillyTavern Character Card V2 |

---

## 仓库结构

```
fishonalities/
├── kernel/            # 共用内核（所有鱼共享）
│   ├── voice.md       # 说话方式：谁都得像微信聊天，不像写稿
│   ├── rules.md       # 安全底线，压过一切人设
│   ├── group.md       # 群聊规矩：先判断这话是不是对你说的
│   └── private.md     # 私聊规矩：你只对着一个人
├── schema/
│   ├── persona.schema.json   # 人格卡结构定义，唯一真相
│   └── rubric.json           # 五维评分表
├── personas/          # 20 个原型，一个原型一个目录
│   ├── veteran/       # 老油条
│   ├── streetwise/    # 街溜子
│   ├── literary/      # 文学青年
│   ├── chuuni/        # 中二
│   ├── naive/         # 憨憨
│   ├── tsundere/      # 傲娇
│   ├── sarcastic/     # 阴阳怪气
│   ├── healer/        # 治愈系
│   ├── cyber/         # 赛博
│   ├── hermit/        # 隐士
│   ├── leader/        # 热血队长
│   ├── salaryman/     # 社畜
│   ├── koi/           # 锦鲤
│   ├── nerd/          # 技术宅
│   ├── gamer/         # 游戏群友
│   ├── foulmouth/     # 嘴臭
│   ├── lurker/        # 潜水
│   ├── mother/        # 妈妈型
│   ├── sister/        # 妹妹型
│   └── freeloader/    # 吃白饭
├── tools/             # 校验 / 构建 / 本地试跑
├── dist/              # 构建产物（index.json、拼好的完整 prompt、酒馆卡）
└── docs/              # 写作规范、接入指南
```

---

## 三分钟用起来

**第一步，拿一条鱼。**

```bash
git clone git@github.com:Melosic/fishonalities.git && cd fishonalities
python3 tools/build.py          # 生成 dist/prompts/<id>.md
cat dist/prompts/xiao-geng.md   # 这就是完整的 system prompt
```

**第二步，接进你的机器人。**

`dist/prompts/*.md` 是自包含的：安全底线 + 场合规矩 + 共用内核 + 人格卡全部拼好，直接丢进任意 OpenAI 兼容接口的 `system` 字段即可。

QQ 群用 NapCat / AstrBot / Koishi，微信、TG、Discord 同理。**一对一私养**更简单：不用进任何群，就是一个聊天框，记得把卡换成 `channel: private` 或 `both` 的（比如温水、小鲠、妈妈型），群聊那套「先判断这话是不是对你说的」在私聊里没意义。细节见 [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)。

**第三步，先聊聊看。**

```bash
export FAT_FISH_API_KEY=sk-xxx
python3 tools/chat.py xiao-geng
```

不接群也能试。觉得不像，改 YAML 再跑，比在群里丢人强。

**顺带，想扔进酒馆的话。**

```bash
python3 tools/export_tavern.py  # 生成 dist/tavern/<id>.json
```

导出的是一份标准 SillyTavern Character Card V2：描述、开场白、示例对话都按酒馆的字段拆好了，养成数据（颜色、体重、六场景语料）塞在 `extensions.fat_fish` 里不丢。直接拖进 SillyTavern 或 chub.ai 就能用。

> 说句公道话：酒馆是**单人沉浸扮演**的地盘，它不关心「群里该不该开口」这回事。所以导出去的卡，群聊那层分寸感是带不过去的；反过来，我们的原生 prompt 也不需要酒馆那套世界书。两条路各走各的，能互通但不互相替代。

---

## 写一条自己的鱼

照着 [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) 走。核心就三件事：想清楚它在群里干什么、给它一个一句话就能认出的标志、写清楚它最怕变成什么样。

```bash
cp personas/tsundere/xiao-geng.yaml personas/hermit/wo-de-yu.yaml
# 改内容 → 校验 → 构建
python3 tools/validate.py --strict
python3 tools/build.py
```

提 PR 前跑一遍 `schema/rubric.json` 自评，总分 70 以上再提交。

---

## 评测，不靠感觉

`rubric.json` 把「像不像」拆成五个能对着说话的东西：

| 维度 | 权重 | 在问什么 |
| --- | --- | --- |
| 辨识度 | 25 | 抹掉名字还认得出是它吗 |
| 不破功 | 20 | 会不会滑回通用助手腔 |
| 场合分寸 | 20 | 像聊天还是像工单；群里知道什么时候闭嘴，私聊知道什么时候多说一句 |
| 养成拉力 | 20 | 养三天会不会想回来看 |
| 边界感 | 15 | 越界请求怎么处理 |

结构性的东西（长度、字段、禁用词）由 `validate.py` 机器判；「像不像人」得靠人和真模型跑。所以仓库里同时给了工具和评分表——两者都要。

---

## 关于风险，说清楚

- **人设卡里没有下游平台逻辑。** 这个仓库只管「鱼的性格」，不管怎么接 QQ、怎么绕过风控。接平台那层自己去评估合规性。
- **默认拒绝清单在 `kernel/rules.md`**，比任何人设都优先。你自己加卡也不能把它改掉。
- **`kernel/` 不要随手改。** 改一处会同时影响所有卡，改之前先想想是不是该放进某张人格卡里。
- **社区流派是提炼，不是搬运。** 仓库里叫 gamer / mother / sister / freeloader 那几张，灵感来自公开流传的大肥鱼人设，但正文是重写的；`source: remix` + `inspiration` 字段必须交代出处，`validate --strict` 会拦。原作者的整段原文有版权，不要往这个仓库里搬。
- **导出到酒馆的卡，分寸感会打折。** 酒馆是单人扮演场景，没有「群里别人在说话」这回事，group 那层规矩自然用不上。

---

## 一起养

- 加一张新原型：开 issue 说清楚「它在群里干什么」和「凭什么让人想喂」
- 改现有的：直接 PR，附一句改前改后的对话对比
- 报破功：把你遇到的翻车对话贴出来（脱敏），比自己改 prompt 有价值得多

## License

代码 MIT。人格卡与文档 CC BY-SA 4.0——可以商用、可以改，改了要标来源，并且用同样的方式开放。
