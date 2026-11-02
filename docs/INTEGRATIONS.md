# 接进你的群

这个仓库只产出一样东西：**一段自包含的 system prompt**。剩下的事平台自己解决。

`python3 tools/build.py` 之后，`dist/prompts/<id>.md` 就是成品，直接塞给任意 OpenAI 兼容接口的 `system` 字段。

---

## 通用姿势（任何平台都适用）

```python
import openai, pathlib

system = pathlib.Path("dist/prompts/xiao-geng.md").read_text()
client = openai.OpenAI(api_key=..., base_url=...)

# 群聊里每来一条消息，带上最近 N 条上下文
messages = [{"role": "system", "content": system}, *recent_history]
resp = client.chat.completions.create(
    model="deepseek-chat",
    messages=messages,
    temperature=0.75,          # 用人格卡里的 temperature
    max_tokens=200,            # 群聊别给太长，200 够
)
```

三个必须做的细节：

1. **`max_tokens` 卡死。** 人格卡里写了「一两句」，但模型不一定听话，硬限制比 prompt 可靠。
2. **带上下文，但别带太多。** 群里最近 10-20 条足够。带太多它会把别人的口癖学过去，人设会糊。
3. **不要每条都回。** 按概率回（比如 30%），或者只在被 @ / 被叫名字时回。有性格的鱼不会刷屏。

---

## QQ 群

主流两条路，取舍很明确：

### 路线一：NapCat（OneBot v11）

社区最成熟的方案，基于 NTQQ 客户端，能进任意群、能主动说话、自由度最高。

```
QQ 客户端 → NapCat（OneBot v11）→ 你的程序（HTTP / WebSocket）
```

- 项目：[NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ)
- 优点：不审核、能进老群、能主动发言，养成玩法必需
- 代价：非官方途径，有风控和掉线风险，腾讯政策变化会影响；别人掉线你遭殃
- 常见搭配：NapCat + NoneBot2 / Koishi / AstrBot

接进来之后你只需要处理两件事：收到消息 → 调模型 → 发回去。

### 路线二：QQ 官方机器人平台

在 [q.qq.com](https://q.qq.com/) 申请，个人认证开发者能建 5 个（[官方文档](https://bot.q.qq.com/wiki)）。

- 优点：合规、稳定、不担心封号
- 代价：要审核；不能主动进群；主动消息有频率限制；支持的消息类型受限

**结论**：想玩「饿了主动喊人」这种养成互动，基本只能走 NapCat。走了就得接受掉线是常态，把重连和掉线通知做扎实。

### 已接入的方案

- [AstrBot](https://github.com/Soulter/AstrBot)：多平台 LLM 机器人框架，自带 QQ 适配，配置化程度高
- [Koishi](https://koishi.chat/) + Chatluna：插件生态最丰富
- NoneBot2：适合自己写业务逻辑

以上都能把 `dist/prompts/*.md` 当成 system prompt 直接喂。

---

## 先选场合：群聊还是私聊

每张卡的 `channel` 决定它被拼进哪套规矩，选错了会明显别扭：

| channel | 拼进去的内核 | 适合接哪 | 典型卡 |
| --- | --- | --- | --- |
| `group` | voice + group | QQ 群、TG 群、Discord 服务器 | 老肥、阿街、缸长 |
| `private` | voice + private | 只有你跟它的一个聊天框 | 半页、小鲠、温水 |
| `both` | voice + group + private | 两边都要用 | 阿懵、老周、老井 |

导出后的 prompt 里能直接看到判据：`channel: group` 的卡开头是「你是一条养在**群聊**里的」，`both` 的会同时带上【场合规则 · 群聊里】和【场合规则 · 私聊里】两段。

**一对一私养其实比接群更省事**，也更容易出效果：不用装 NapCat、不用管掉线、不用怕刷屏。一个聊天框，接个 OpenAI 兼容接口就行。`examples/simple_bot.py` 里的冷却、回复概率这些群聊参数，私聊场景全部关掉，改成每条都回。

区别在于三件事：

- **群聊怕吵，私聊怕冷。** 群里少说话是礼貌，私聊里半天不回一个「嗯」就是敷衍。
- **群聊不能追问私事，私聊可以记得住。** 私聊的核心价值是「它记得你上次说的那件事」。
- **群聊人设要浅一点，私聊可以深一点。** 群里一句话就是全部信息量，私聊可以两三句。

---

## 微信

**没有官方个人号接口。** 能用的都是 hook 客户端（如基于 PC 端的注入方案），封号风险高，不建议用在主号上。

企业微信 / 公众号 / 客服消息是合规路径，但都是「用户主动来找」，不是群聊氛围，养成的感觉会弱很多。

如果只是要群聊养成，QQ 比微信合适得多。

---

## Telegram / Discord

最省事的两个平台，官方 Bot API 完整，几分钟能跑通。

- Telegram：`@BotFather` 建 bot → `python-telegram-bot` 或 `aiogram` → 群聊里加 bot 需要关掉 privacy mode 才能读全部消息
- Discord：Developer Portal 建 application → `discord.py` → 记得开 `message_content` intent

这两个适合先验证人格卡好不好玩，再接 QQ。

---

## 养成系统怎么接

人格卡的 `moments` 字段是留给养成系统的接口：

| 字段 | 什么时候触发 | 你该做什么 |
| --- | --- | --- |
| `greeting` | 有人在群里说话，它被叫醒 | 直接发 |
| `fed` | 记录到一次投喂（聊天算、@ 算、发图算，你定） | 直接发 |
| `hungry` | 距上次互动超过 N 小时 | 主动发，别太频繁，一天最多一次 |
| `poke` | 被 @ 或戳一戳 | 直接发 |
| `levelup` | 体重跨过阈值 | 直接发，配一张战报图效果最好 |
| `leave` | 长时间没人理 / 有人退群 | 别真走，发一句就够 |

`fish` 字段给的是养成曲线：`weight_start` → `weight_grown`，`color_start` → `color_grown`。按喂食次数线性插值，或者自己设计曲线，都行。

**别做的**：别让「不喂就死」变成打卡负债。让「回来」比「别断」重要——饿了说话，但不会真的死。

---

## 常见坑

- **人设糊掉**：上下文塞太多别人的话，它会学舌。控制在最近 20 条内，且只放该群的消息。
- **变成客服**：模型默认就是助手腔。`kernel/voice.md` 里的禁令必须完整带上，别只发人格卡部分。用 `build.py` 生成的完整 prompt 就不会漏。
- **刷屏**：一定要限制频率，同一个话题不重复回。
- **复读**：模型对同一个 prompt 会稳定输出同一句口头禅。在 `catchphrases` 里多备几句，随机取用。
- **掉线无感知**：NapCat 掉线不会告诉你。写个心跳检测，掉线发通知，不然群里会安静好几天没人发现。
