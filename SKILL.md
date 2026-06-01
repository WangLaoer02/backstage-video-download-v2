---
name: backstage-video-download-v2
description: 从广告平台 API 批量下载视频，支持前缀搜索、断点续传，每日定时任务。下载后自动进行改竖处理（AI 角色识别 + 贴图匹配 + handler.py 执行 + 按原视频日期归档到 /Volumes/美术AI龙虾/{用户代码}/后台下载/{YYYY-MM-DD}/ 目录）。
metadata:
  short-description: 后台视频下载与稳定改竖
  version: v2.4.0
  date: 2026-06-01
  trigger-keywords:
    - 下载视频
    - 后台下载
    - 广告平台视频
---

# backstage-video-download v2.4.0 Skill

## 功能概述

1. **下载阶段**：从广告平台 API 批量下载横版视频（跳过名称含"改竖"的），内置 moov 完整性检测 + 自动修复
2. **改竖阶段**：提取关键帧 → AI 识别 IP → 匹配贴图 → handler.py 执行 → 输出到日期目录

3. **自我审查阶段**：每步自动审查，命名/成品全链路可追溯

## ⚠️ 脚本路径说明

> 实际生效路径：**`~/.agents/skills/backstage-video-download-v2/scripts/`**
> v2.4.0 已加入：720x1280 强校验、贴图全片循环铺满、本地幂等状态、防重复改竖、批次缺号报告。

## 环境配置

```bash
export VISION_API_URL="http://localhost:11434/api/generate"   # Ollama qwen2.5vl:7b（本地 Vision，不耗钱）
export VISION_API_KEY=""                                          # Ollama 不需要 key
export BACKSTAGE_SAVE_DIR="/Volumes/美术AI龙虾"
export BACKSTAGE_ASSETS_DIR="/Volumes/美术AI龙虾/assets"
export IPv6_ROOT="http://[2408:8256:4c87:f19c::c42]:9092"
```

## 标准批处理流程（推荐）

> 小龙虾自动任务优先用一键批次入口。它会搜索、去重、逐条改竖、复用已有成品，并输出缺号和失败列表。

```bash
python3 download.py --batch-pipeline "260601"
```

### 人工检查流程

```
① python3 download.py --search "260601"
   → 确认 API 返回数量

② python3 download.py --batch-pipeline "260601" --dry-run
   → 预览 eligible、skipped、missing_sequences

③ python3 download.py --batch-pipeline "260601"
   → 完整执行，返回 processed_list / failed_list / missing_sequences
```

### 批次执行检查清单（必做）

- [ ] 下载数量与搜索数量一致（除去含"改竖"的跳过项）
- [ ] 每条横版视频（1280×720）都必须执行改竖，**不得跳过**
- [ ] 每条 --pipeline 返回 success=True
- [ ] 输出成品必须为 720×1280（脚本会自动 ffprobe 校验）
- [ ] 同一原视频重复跑时必须返回 reused_existing=True，不再新生成成品
- [ ] 异常条目记入 memory/errors.md
- [ ] **遍历所有用户代码确认没有漏掉某用户的某批次**

## 脚本速查

| 脚本 | 路径 |
|------|------|
| 下载/改竖 | `~/.agents/skills/backstage-video-download-v2/scripts/download.py` |
| 改竖执行器 | `~/.agents/skills/backstage-video-download-v2/scripts/handler.py` |
| 配置 | `~/.agents/skills/backstage-video-download-v2/scripts/config.py` |

### download.py 参数
```bash
# 搜索（先用这个确认数量）
python3 download.py --search "260529"

# 下载当天（跳过含"改竖"的视频）
python3 download.py --download-prefix "260529"

# 单条完整流水线（下载→改竖，写表已禁用）
python3 download.py --pipeline "260529D1-原生开局一辆车-原创"

# 批次完整流水线（推荐给自动任务）
python3 download.py --batch-pipeline "260529"

# 预览批次，不下载不改竖
python3 download.py --batch-pipeline "260529" --dry-run
```

## 竖版原视频判断标准

> 以下情况不需要改竖，直接记录（状态=竖版原视频）

| 判断依据 | 说明 |
|----------|------|
| 已是竖屏尺寸 | 视频宽高为 720×1280 |
| 文件名含"龙虾改竖" | 已处理过的本流水线成品，跳过下载和改竖 |

> ⚠️ **横版视频（1280×720）必须改竖，不得以任何理由跳过。**
> ⚠️ 原始素材标题里可能包含"改竖"两个字（如 `AI小樱擦边改竖...`），不能因此跳过。

## 贴图随机化规则

> v2.3.0 新增：同一 IP 匹配到多张贴图时随机选取，不再固定选第一张。

- 命中关键词或 AI 识别后，匹配到多张贴图时 → `random.choice()` 随机选取
- fallback 目录有多张图时 → `random.choice()` 随机选取
- fallback 目录只有1张图时 → 全落到同一张（需补充多张才能随机化）

**当前 fallback 贴图数：1张（通用贴图.jpg），需补充才能解决随机性问题。**

## 成品序号生成规则

> 成品序号 = 扫描日期目录下所有文件的序号最大值 + 1
> 扫描范围：原始文件 + 龙虾改竖成品，合并计算 max

| 场景 | 原始文件 | 目录成品文件 | max扫描结果 | 下一个成品序号 |
|------|----------|-------------|-------------|---------------|
| 新批次首批 | 1条 | 0条 | 1 | 2 |
| 同批次第N条 | N条 | M条 | max(N,M) | max+1 |
| 跨批次追加 | 1条 | 已有前批成品 | 前批成品号 | 前批成品号+1 |

**代码：** `get_next_seq(date, user_code)` 扫描 `{用户代码}/后台下载/{YYYY-MM-DD}/` 目录下所有 `.mp4` 文件，按 `{26MMDD}{USER_CODE}{seq}` 模式提取序号，取最大值 + 1

## 幂等与防重复规则

> v2.4.0 新增：同一个原视频名只允许生成一个有效改竖成品。

- 每个 `{用户代码}/后台下载/{YYYY-MM-DD}/` 目录会写入 `.backstage_pipeline_state.json`
- 每次 `--pipeline` 会先查状态文件，再扫描已有 `*-龙虾改竖{原内容}-{后缀}.mp4`
- 已存在且通过 720×1280 + 时长校验时，直接返回 `reused_existing=True`
- 序号分配在 `.backstage_pipeline.lock` 文件锁内执行，避免并发跑任务时撞号

## 改竖输出强约束

- `handler.py` 使用 `-loop 1` 让贴图覆盖完整视频时长
- 上下贴图均按 720×437 缩放裁切铺满
- 中间视频固定 720×406，不足区域自动黑边 pad
- 输出后强制 ffprobe 校验为 720×1280，否则本条失败

## 用户代码 → IP 映射

> 用于记录时自动填充 IP名字 字段

| 用户代码 | 常见 IP | 说明 |
|----------|---------|------|
| D | 火影忍者 / 咒术回战 / 其他 | 独立 IP |
| JR | 火影忍者 / 咒术回战 / 鬼灭之刃 | 混搭 |
| LJJ | 咒术回战 / 鬼灭之刃 / 火影忍者 | 混搭 |
| TM | 鬼灭之刃 / 火影忍者 / 咒术回战 | 混搭 |
| WY | 咒术回战 | 独立 |
| ZL | 咒术回战（竖版原视频居多） | RF来源 |
| HR | 鬼灭之刃 / 咒术回战 | 混搭 |
| M | 咒术回战 | 竖版原视频居多 |
| ZX | 火影忍者 | 独立 |
| RY | 火影忍者 | 独立 |
| YB | 火影忍者 | 独立 |
| DXX | 咒术回战 / 火影忍者 / 其他 | 新增素材来源 |

> 实际 IP 以贴图路径和 AI 识别为准，上表用于辅助判断和无匹配时兜底。

## 文件名兼容

- 支持 `{YYMMDD}{USER}{seq}-{内容}-{后缀}`，如 `260601DXX1-五条悟面试简历-KY-37`
- 支持 `{YYMMDD}{USER}{seq}-{内容}`，如 `260601LJJ2-AI小樱擦边改竖佐助洗髓`
- 只有明确包含 `龙虾改竖` 的文件名才视为本流水线成品并跳过

## 贴图匹配规则

### IP 识别优先级
1. **文件名关键词判断**（最优先，无网络开销）
2. **关键帧 AI 识别**（文件名无关键词时触发）—— 从视频 30% 处提取帧，调 Vision API 识别 IP

### 文件名 → 贴图匹配规则

#### 火影角色（assets/naruto/）
| 关键词 | 贴图 |
|--------|------|
| 鼬 | `naruto/火影-宇智波鼬_*`, `naruto/鼬_*` |
| 斑 | `naruto/火影-宇智波斑_*` |
| 佐助 | `naruto/火影-宇智波佐助_*` |
| 鸣人 | `naruto/火影-漩涡鸣人_*`, `naruto/鸣人_*` |
| 水门 | `naruto/火影-波风水门_*` |
| 纲手 | `naruto/火影-纲手_*` |
| 柱间 | `naruto/火影-千手柱间_*`, `初代火影` |
| 自来也 | `naruto/火影-自来也_*` |
| 佩恩 | `naruto/火影-佩恩_*` |
| 夜凯, 死门凯 | `naruto/火影-夜凯_*` |
| 小樱 | `naruto/火影-春野樱_*` |
| 玖辛奈 | `naruto/玖辛奈_*` |
| 雏田 | `naruto/雏田_*` |
| 天天 | `naruto/天天_*` |
| 香燐 | `naruto/香燐_*` |
| 卡卡西 | `naruto/旗木卡卡西_*` |
| 凯 | `naruto/迈特凯_*` |
| 金鸣 | `naruto/金鸣_*`, `naruto/漩涡鸣人_*` |
| 擦边（通用） | `naruto/火影-擦边_*`, `naruto/火影通用.jpg` |

#### 咒术角色（assets/jujutsu/）
| 关键词 | 贴图 |
|--------|------|
| 甚尔, 伏黑甚尔 | `jujutsu/咒术-伏黑甚尔*`, `jujutsu/咒术-甚尔*` |
| 乙骨, 乙骨忧太 | `jujutsu/咒术-乙骨*`, `jujutsu/咒术-乙骨忧太*` |
| 宿傩 | `jujutsu/宿傩*` |
| 五条悟 | `jujutsu/五条悟*` |
| 虎杖, 虎杖悠仁 | `jujutsu/虎杖悠仁*`, `jujutsu/虎杖*` |
| 七海 | `jujutsu/七海*` |
| 东堂, 东堂葵 | `jujutsu/东堂*` |
| 秤, 秤金次 | `jujutsu/咒术-秤金次*` |
| 禅院 | `jujutsu/禅院*` |
| 伏黑惠, 惠 | `jujutsu/伏黑惠*` |
| 冥冥 | `jujutsu/冥冥*` |
| 夏油杰 | `jujutsu/夏油杰*` |
| 真人 | `jujutsu/真人*` |

#### 鬼灭角色（assets/kimetsu/）
| 关键词 | 贴图 |
|--------|------|
| 义勇, 富冈义勇 | `kimetsu/富冈义勇*`, `kimetsu/鬼灭-富冈义勇*` |
| 岩柱, 悲鸣屿行冥 | `kimetsu/岩柱*` |
| 甘露寺, 甘露寺蜜璃 | `kimetsu/甘露寺蜜璃*`, `kimetsu/甘露寺*` |
| 蝴蝶忍, 忍 | `kimetsu/蝴蝶忍*`, `kimetsu/鬼灭-擦边-蝴蝶忍*` |
| 我妻善逸, 善逸 | `kimetsu/我妻善逸*` |
| 猗窝座 | `kimetsu/猗窝座*` |
| 杏寿郎 | `kimetsu/杏寿郎*` |
| 炭治郎 | `kimetsu/炭治郎*` |
| 继国缘一, 缘一 | `kimetsu/继国缘一*` |
| 黑死牟 | `kimetsu/黑死牟*` |
| 祢豆子 | `kimetsu/祢豆子*`, `kimetsu/鬼灭-擦边-祢豆子*` |
| 堕姬 | `kimetsu/堕姬*` |
| 香奈乎 | `kimetsu/香奈乎*`, `kimetsu/鬼灭-擦边-香奈乎*` |
| 无惨 | `kimetsu/无惨*` |
| 无一郎 | `kimetsu/无一郎*` |
| 擦边（通用） | `kimetsu/鬼灭-擦边-*` |

**兜底：** 无匹配 → `fallback/` 目录随机选一张（标记待确认）

### 贴图素材库路径
- **搜索范围**：`/Volumes/美术AI龙虾/assets/`
- **火影**：`assets/naruto/` 子目录
- **咒术**：`assets/` 根目录

## 飞书表格写入规范

> ⚠️ Ipv6视频链接字段为 URL 类型，写入格式：
> `{"link": "http://[...]/{用户}/后台下载/{YYYY-MM-DD}/{文件名}.mp4", "text": "文件名.mp4"}`
> 纯字符串会返回 `URLFieldConvFail` 错误。

| 字段名 | 值 | 说明 |
|--------|-----|------|
| `原命名` | 原视频命名 | 主键 |
| `Ipv6视频链接` | JSON对象，含 link + text | URL 字段 |
| `状态` | `改竖` / `竖版原视频` | 单选 |
| `IP名字` | 鬼灭之刃/火影忍者/咒术回战/其他 | 单选 |
| `用户` | D/JR/LJJ/ZX/WY/HR/TM/ZL/M/RY/YB | 单选 |
| `是否异常` | 正常/异常 | 单选 |

## 目标表

- App Token：`SYP1b0qvOaY60xszqLycOK9PnNg`
- Table ID：`tblewZ4BB4tHPnFC`
- 链接：`https://fc4dpykqzg.feishu.cn/base/SYP1b0qvOaY60xszqLycOK9PnNg?table=tblewZ4BB4tHPnFC&view=vew9Tu0iOX`

## API 约束
- 搜索只支持**前缀匹配**，描述文字搜不了
- 日期格式：`YYMMDD`（260420 = 2026年4月20日）

## 版本记录

### v2.4.0（2026-06-01）
- 修正：`handler.py` 增加强制 720×1280 输出校验，尺寸异常直接失败
- 修正：贴图输入改为 `-loop 1`，上下贴图全程铺满，不再因单帧/时长问题丢贴图
- 新增：本地 `.backstage_pipeline_state.json` 状态账本，同一原视频重复跑会复用成品
- 新增：`.backstage_pipeline.lock` 文件锁，避免并发跑批导致序号重复
- 新增：`--batch-pipeline` 一键跑批，自动输出 `missing_sequences` 和失败列表
- 修正：原始素材标题包含"改竖"时不再误判为成品跳过，只跳过 `龙虾改竖`
- 修正：支持无后缀文件名，避免 `260601LJJ2-AI小樱擦边改竖佐助洗髓` 这类素材被丢弃
- 修正：`cron_incremental.py` 不再使用旧 `~/.openclaw/skills` 路径，不再依赖已禁用的飞书写表状态

### v2.3.0（2026-05-29）
- 新增：贴图随机化（`random.choice()` 取代 `sorted()[0]`），同一 IP 不再每次固定选同一张
- 新增：用户代码补充 RY、YB
- 新增：金鸣→naruto鸣人的映射
- 新增：卡卡西、凯的 naruto 关键词
- 修正：竖版原视频判断标准明确横版（1280×720）必须改竖不得跳过
- 修正：批次执行检查清单新增"遍历所有用户确认无遗漏"
- 修正：飞书表格 URL 字段写入格式（含 JSON 对象格式说明）
- 修正：SKILL.md 路径改为 `~/.agents/skills/`（实际生效路径）

### v2.2.0（2026-04-28）
- 新增：标准批处理流程章节
- 新增：竖版原视频判断标准（含像素类视频）
- 新增：用户代码 → IP 映射表
- 修正：脚本路径说明

### v2.1.0（2026-04-27）
- 完整重写 download.py，移除多用户复杂规则
- AI 角色识别（Vision API）集成
- 自我审查机制（下载/改竖/成品三段校验）

## 相关技能

| Skill | 职责 |
|-------|------|
| `video-reinspect` | 异常视频返工：扫描表格异常记录 → 重新改竖 → 覆盖成品 → 更新表格 |

## 待解决事项

| 事项 | 说明 |
|------|------|
| fallback 贴图补充 | 当前只有1张通用贴图，AI识别失败时全落到同一张，需补充多张不同角色贴图 |
| AI识别质量 | AI有时返回"鼫"/"鹤人"等无法匹配的词，建议优化 prompt 或更换模型 |
