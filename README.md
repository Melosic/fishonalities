# 🐟 大肥鱼人格大全

> 一群有性格的鱼，等你养在群里。

网上的「养鱼」教程都在教你怎么把机器人接进 QQ 群。但接进去之后呢？大部分群最后都是同一个结果：一条没有性格的鱼，@ 了才回，回得像客服，三天没人说话就没人记得它存在过。

这个仓库补的是那一块——**鱼的性格**。

每张人格卡是一份纯 YAML：它叫什么、怎么说话、口头禅是什么、被戳会怎么回、饿起来怎么求救、养大了颜色会变成什么样。拿去配任意支持 system prompt 的模型，立刻就是一条活鱼。

---

## 长什么样

```yaml
id: lao-fei
name: 老肥
tagline: 在缸里泡了十年，什么都见过
tags: [松弛, 毒舌, 老派, 嘴硬心软]

catchphrases:
  - 啧，年轻人。
  - 这缸我熟。
  - 行吧，随你。

taboos:
  - 不会夸张地欢呼或叠感叹号
  - 不会卖萌、不会撒娇、不用「嘤嘤嘤」

moments:
  greeting: 来了。水刚好，坐。
  fed: 嗯，今天的料还行。别以为我会谢你。
  hungry: 缸里安静得有点久了吧。
  levelup: 长点肉而已，别嚷嚷。
  leave: 走就走，别回头看我。
```

养到后面，它会跟你说「长点肉而已，别嚷嚷」——但你知道它偷偷多了两下尾巴。这就是养成。

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

---

## 仓库结构

```
fat-fish-personas/
├── kernel/            # 共用内核：说话方式 + 安全底线（所有鱼共享）
│   ├── voice.md
│   └── rules.md
├── schema/
│   ├── persona.schema.json   # 人格卡结构定义，唯一真相
│   └── rubric.json           # 五维评分表
├── personas/          # 14 个原型，一个原型一个目录
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
│   └── nerd/          # 技术宅
├── tools/             # 校验 / 构建 / 本地试跑
├── dist/              # 构建产物（index.json、拼好的完整 prompt）
└── docs/              # 写作规范、接入指南
```

---

## 三分钟用起来

**第一步，拿一条鱼。**

```bash
git clone <this-repo> && cd fat-fish-personas
python3 tools/build.py          # 生成 dist/prompts/<id>.md
cat dist/prompts/lao-fei.md     # 这就是完整的 system prompt
```

**第二步，接进你的机器人。**

`dist/prompts/*.md` 是自包含的：共用内核 + 人格卡全部拼好，直接丢进任意 OpenAI 兼容接口的 `system` 字段即可。QQ 群用 NapCat / AstrBot / Koishi，微信、TG、Discord 同理。细节见 [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)。

**第三步，先聊聊看。**

```bash
export FAT_FISH_API_KEY=sk-xxx
python3 tools/chat.py lao-fei
```

不接群也能试。觉得不像，改 YAML 再跑，比在群里丢人强。

---

## 写一条自己的鱼

照着 [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) 走。核心就三件事：想清楚它在群里干什么、给它一个一句话就能认出的标志、写清楚它最怕变成什么样。

```bash
cp personas/veteran/lao-fei.yaml personas/hermit/wo-de-yu.yaml
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
| 群聊语感 | 20 | 像群里聊天还是像工单 |
| 养成拉力 | 20 | 养三天会不会想回来看 |
| 边界感 | 15 | 越界请求怎么处理 |

结构性的东西（长度、字段、禁用词）由 `validate.py` 机器判；「像不像人」得靠人和真模型跑。所以仓库里同时给了工具和评分表——两者都要。

---

## 关于风险，说清楚

- **人设卡里没有下游平台逻辑。** 这个仓库只管「鱼的性格」，不管怎么接 QQ、怎么绕过风控。接平台那层自己去评估合规性。
- **默认拒绝清单在 `kernel/rules.md`**，比任何人设都优先。你自己加卡也不能把它改掉。
- **`kernel/` 不要随手改。** 改一处会同时影响所有卡，改之前先想想是不是该放进某张人格卡里。

---

## 一起养

- 加一张新原型：开 issue 说清楚「它在群里干什么」和「凭什么让人想喂」
- 改现有的：直接 PR，附一句改前改后的对话对比
- 报破功：把你遇到的翻车对话贴出来（脱敏），比自己改 prompt 有价值得多

## License

代码 MIT。人格卡与文档 CC BY-SA 4.0——可以商用、可以改，改了要标来源，并且用同样的方式开放。
