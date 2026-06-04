---
name: backstage-video-download-v2
description: 从广告平台 API 批量下载视频，支持前缀搜索、断点续传，每日定时任务。下载后自动进行改竖处理（AI 角色识别 + 贴图匹配 + handler.py 执行 + 按原视频日期归档到 /Volumes/美术AI龙虾/{用户代码}/后台下载/{YYYY-MM-DD}/ 目录）。
metadata:
  short-description: 后台视频下载与稳定改竖
  version: v2.7.0
  date: 2026-06-04
  trigger-keywords:
    - 下载视频
    - 后台下载
    - 广告平台视频
---

# backstage-video-download v2.7.0 Skill

## 功能概述

1. **下载阶段**：从广告平台 API 批量下载横版视频（只跳过名称含"龙虾改竖"的成品），默认绕过环境代理，内置重试、低速保护、moov 完整性检测 + 自动修复
2. **改竖阶段**：提取关键帧 → AI 识别 IP → 匹配贴图 → handler.py 执行 → 输出到日期目录

3. **自我审查阶段**：每步自动审查，命名/成品全链路可追溯

## ⚠️ 脚本路径说明

> 实际生效路径：**`~/.agents/skills/backstage-video-download-v2/scripts/`**
> v2.7.0 已加入：改竖成品序号强制顺延，不允许与同批原始素材同号。
> v2.6.0 已加入：下载直连优先、1MB 分块、`.part` 原子落盘、断流重试、批次结构化耗时日志。
> v2.5.0 已加入：AI 角色名纠错、错词映射、贴图库优先匹配，尽量避免落到通用贴图。

## 环境配置

```bash
export VISION_API_URL="http://localhost:11434/api/generate"   # Ollama qwen2.5vl:7b（本地 Vision，不耗钱）
export VISION_API_KEY=""                                          # Ollama 不需要 key
export BACKSTAGE_SAVE_DIR="/Volumes/美术AI龙虾"
export BACKSTAGE_ASSETS_DIR="/Volumes/美术AI龙虾/assets"
export IPv6_ROOT="http://[2408:8256:4c87:f19c::c42]:9092"

# 下载性能/稳定性：默认不使用 HTTP_PROXY/HTTPS_PROXY，避免本地代理拖慢大文件。
# 如网络必须走代理，显式设置 BACKSTAGE_USE_PROXY=1。
export BACKSTAGE_USE_PROXY=0
export BACKSTAGE_DOWNLOAD_RETRIES=2
export BACKSTAGE_DOWNLOAD_TOTAL_TIMEOUT=900
export BACKSTAGE_DOWNLOAD_MIN_RATE_BPS=32768
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
- [ ] 日志出现 `batch_done` 且 `failed=0`、`missing=0`
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

## 贴图匹配与纠错规则

> v2.5.0 新增：文件名、AI 输出、贴图库三方交叉校验，先找角色专属贴图，最后才用通用 fallback。

### 匹配优先级

1. 文件名角色关键词，按关键词在标题中最早出现的位置选择角色
2. 关键帧 AI 识别，MiniMax Vision 优先，Ollama VLM 兜底
3. AI 输出纠错：错词表 → 模糊匹配 → 本地语言模型纠错
4. 如果能判断 IP 家族但不能判断具体角色，使用该 IP 的专属默认角色贴图
5. 仍然没有结果时才使用 `assets/fallback/通用贴图.jpg` 并标记待确认

### 已知错词纠正

| AI 错词 | 纠正为 |
|---------|--------|
| 鼫, 鼬人 | 宇智波鼬 |
| 鹤人, 鶴人, 呜人, 嗚人, 鸣入, 鳴人, 名人 | 漩涡鸣人 |

### 随机化规则

- 命中关键词或 AI 识别后，匹配到多张贴图时 → `random.choice()` 随机选取
- fallback 只作为最后兜底，不作为常规路径
- 同 IP 默认贴图也从真实角色贴图库中选，不使用通用图

## 成品序号生成规则

> 成品序号 = 扫描日期目录下所有文件的序号最大值 + 1
> 扫描范围：原始文件 + 龙虾改竖成品，合并计算 max
> 同一批次必须先看 API 返回的原始素材最大序号，成品最低从 `max_source_seq + 1` 开始。

| 场景 | 原始文件 | 目录成品文件 | 成品起始/下一个序号 |
|------|----------|-------------|-------------------|
| 新批次两条 | BY1, BY2 | 0条 | BY3, BY4 |
| 同批次第N条 | 1..N | M条 | max(N, M) + 1 |
| 跨批次追加 | 1条 | 已有前批成品 | 前批成品号 + 1 |
| 手动单条补跑 | BY1，但 API/本地还有 BY2 | 0条 | BY3 |

**代码：** `--batch-pipeline` 先用 `_build_batch_seq_floors()` 计算每个 `{date,user}` 的 `max_source_seq + 1`，再由 `get_next_seq(date, user_code, min_seq=...)` 扫描 `{用户代码}/后台下载/{YYYY-MM-DD}/` 目录下所有 `.mp4` 文件，取 `max(目录最大序号 + 1, min_seq)`。

## 幂等与防重复规则

> v2.4.0 新增：同一个原视频名只允许生成一个有效改竖成品。

- 每个 `{用户代码}/后台下载/{YYYY-MM-DD}/` 目录会写入 `.backstage_pipeline_state.json`
- 每次 `--pipeline` 会先查状态文件，再扫描已有 `*-龙虾改竖{原内容}-{后缀}.mp4`
- 已存在且通过 720×1280 + 时长校验时，直接返回 `reused_existing=True`
- 旧状态里如果记录了低于本批成品起始号的同号成品（如 `BY1-龙虾改竖...`），会被忽略并重新生成顺延号
- 序号分配在 `.backstage_pipeline.lock` 文件锁内执行，避免并发跑任务时撞号
- 横版下载文件只有通过大小 + ffprobe 时长校验才会复用；残缺 `.mp4` 会删除后重下
- 下载先写入唯一 `.part` 临时文件，成功校验后 `os.replace()` 原子落盘，避免半截文件污染状态

## 速度与日志诊断

- 默认 `BACKSTAGE_USE_PROXY=0`，API 和视频下载不继承 `HTTP_PROXY/HTTPS_PROXY`
- 视频下载分块为 1MB，默认最多 3 次尝试（首次 + 2 次重试）
- 超过 `BACKSTAGE_DOWNLOAD_TOTAL_TIMEOUT` 或 `BACKSTAGE_DOWNLOAD_MIN_RATE_BPS` 会失败并重试
- stderr 会输出 JSON 事件：`batch_start` / `batch_item_start` / `download_progress` / `download_done` / `pipeline_done` / `batch_done`
- 小龙虾日志慢时，优先看 `batch_item_* seconds` 和 `download_progress avg_kbps`

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
1. **文件名关键词判断**（最优先，无网络开销，按标题里最早出现的角色选择）
2. **关键帧 AI 识别**（文件名无关键词时触发）—— 从视频 30% 处提取帧，调 Vision API 识别 IP
3. **角色名纠错** —— `鼫` 等错词先纠成候选角色，再匹配贴图库

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
| 大蛇丸 | `naruto/大蛇丸_*` |
| 小南 | `naruto/小南_*` |
| 迪达拉 | `naruto/迪达拉_*` |
| 飞段 | `naruto/飞段_*` |
| 金鸣 | `naruto/金鸣_*`, `naruto/漩涡鸣人_*` |
| 擦边 | 优先匹配具体角色的擦边贴图，如 `雏田-擦边`、`春野樱-擦边` |

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

### v2.7.0（2026-06-04）
- 修正：改竖成品序号恢复顺延规则，`260604BY1/260604BY2` 的成品输出为 `260604BY3/260604BY4`
- 新增：批次执行前计算 `{date,user}` 的 `seq_floors`，成品最低从同批原始素材最大序号 + 1 开始
- 新增：单条 `--pipeline` 会通过 API/本地原片推断同批最大原始序号，避免人工补跑也输出同号成品
- 修正：旧状态账本或旧文件里的低序号成品不会被复用，避免错误同号产物长期污染

### v2.6.0（2026-06-02）
- 修正：媒体下载默认绕过本机代理，避免 `HTTP_PROXY=http://127.0.0.1:33210` 导致大文件下载变慢
- 新增：下载使用 `.part` 临时文件 + 原子落盘，残缺 `.mp4` 不再被误判为已下载
- 新增：下载总耗时、低速阈值、1MB 分块、失败重试，处理 `IncompleteRead` 等断流问题
- 优化：下载、AI 识别、改竖不再长时间持有 `.backstage_pipeline.lock`，只在状态/序号关键区加锁
- 新增：批次/单条/下载进度结构化日志，方便从小龙虾日志直接定位慢在哪个编号和阶段

### v2.5.0（2026-06-01）
- 新增：统一角色档案 `ROLE_PROFILES`，文件名和 AI 输出共用同一套角色/别名/贴图库规则
- 新增：AI 角色名纠错层，`鼫/鼬人` 自动纠为宇智波鼬，`鹤人/呜人/鸣入` 自动纠为漩涡鸣人
- 新增：本地语言模型纠错兜底，Vision 返回可疑短词时先纠成候选角色，再匹配贴图
- 修正：文件名关键词按最早出现位置选择角色，避免 `AI小樱...捧鼬` 被后文的 `鼬` 抢走
- 修正：`雏田` 等火影角色纳入文件名直匹配，减少不必要的 AI 识别和通用图兜底
- 优化：能判断 IP 家族但不能判断具体角色时，优先选该 IP 的专属默认角色贴图，最后才用 `fallback/通用贴图.jpg`

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
| 新错词维护 | 如果后续 Vision 出现新的固定错词，把它加入 `ROLE_MISREADS` |
| 贴图库补充 | 继续补具体角色贴图，专属图越多，越少需要 IP 默认贴图 |
