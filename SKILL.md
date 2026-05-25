---
name: backstage-video-download-v2
description: 从广告平台 API 批量下载视频，支持前缀搜索、断点续传，每日定时任务。下载后自动进行改竖处理（AI 角色识别 + 贴图匹配 + handler.py 执行 + 按原视频日期归档到 /Volumes/美术AI龙虾/{用户代码}/后台下载/{YYYY-MM-DD}/ 目录）。
trigger_keywords:
  - 下载视频
  - 后台下载
  - 广告平台视频
version: v2.2.0
date: 2026-04-28
---

# backstage-video-download v2.2.0 Skill

## 功能概述

1. **下载阶段**：从广告平台 API 批量下载横版视频（跳过名称含"改竖"的），内置 moov 完整性检测 + 自动修复
2. **改竖阶段**：提取关键帧 → AI 识别 IP → 匹配贴图 → handler.py 执行 → 输出到日期目录

3. **自我审查阶段**：每步自动审查，命名/成品全链路可追溯

## ⚠️ 脚本路径说明

> 实际生效路径：**`~/.openclaw/skills/backstage-video-download-v2/scripts/`**
> `~/.agents/skills/backstage-video-download-v2/scripts/` 为同步备份，内容可能落后。

## 环境配置

```bash
export VISION_API_URL="http://localhost:11434/api/generate"   # Ollama qwen2.5vl:7b（本地 Vision，不耗钱）
export VISION_API_KEY=""                                          # Ollama 不需要 key
export BACKSTAGE_SAVE_DIR="/Volumes/美术AI龙虾"
export BACKSTAGE_ASSETS_DIR="/Volumes/美术AI龙虾/assets"
export IPv6_ROOT="http://[2408:8256:4c87:f19c::c42]:9092"
```

## 标准批处理流程

> 每次任务按此顺序执行，不跳步。

```
① python3 download.py --search "260420"
   → 确认视频数量，核查是否有遗漏

② python3 download.py --download-prefix "260420"
   → 批量下载，自动跳过文件名含"改竖"的视频
   → 记录下载数量和跳过数量

③ 逐条执行 --pipeline
   → 改竖完成，一体化闭环（写表已禁用）
   → 竖版原视频直接记录（状态=竖版原视频）
```

### 批次执行检查清单

- [ ] 下载数量与搜索数量一致（除去含"改竖"的跳过项）
- [ ] 每条 --pipeline 返回 success=True
- [ ] 全部写入飞书表格（打开表格核查）
- [ ] 异常条目记入 memory/errors.md

## 脚本速查

| 脚本 | 路径 |
|------|------|
| 下载/改竖 | `~/.openclaw/skills/backstage-video-download-v2/scripts/download.py` |
| 改竖执行器 | `~/.openclaw/skills/backstage-video-download-v2/scripts/handler.py` |
| 配置 | `~/.openclaw/skills/backstage-video-download-v2/scripts/config.py` |

### download.py 参数
```bash
# 搜索（先用这个确认数量）
python3 download.py --search "260420"

# 下载当天（跳过含"改竖"的视频）
python3 download.py --download-prefix "260420"

# 单条完整流水线（下载→改竖，写表已禁用）
python3 download.py --pipeline "260420D1-700级卡卡西洛克王国面板Q版-D-ZZH"

# 预览不下载
python3 download.py --download-prefix "260420" --dry-run
```

## 竖版原视频判断标准

> 以下情况不需要改竖，直接记录（状态=竖版原视频）

| 判断依据 | 说明 |
|----------|------|
| 已是竖屏尺寸 | 视频宽高为 720×1280（竖版像素类） |
| 文件名含"改竖" | 已处理过的成品，跳过下载和改竖 |
| 像素技能类视频 | 内容为竖版角色（如"像素技能"、"像素火影"），宽高 1280×720 但内容竖版 |

**典型像素类关键词：** 像素、Q版、像素技能、像素火影

## 成品序号生成规则

> 成品序号 = 扫描日期目录下所有文件的序号最大值 + 1
> 扫描范围：原始文件 + 龙虾改竖成品，合并计算 max

| 场景 | 原始文件 | 目录成品文件 | max扫描结果 | 下一个成品序号 |
|------|----------|-------------|-------------|---------------|
| 新批次首批 | 1条 | 0条 | 1 | 2 |
| 同批次第N条 | N条 | M条 | max(N,M) | max+1 |
| 跨批次追加 | 1条 | 已有前批成品 | 前批成品号 | 前批成品号+1 |

**示例：** WY1/WY2原始文件存在 + WY2成品存在 → max=2 → 下一成品=WY3

**代码：** `get_next_seq(date, user_code)` 扫描 `{用户代码}/后台下载/{YYYY-MM-DD}/` 目录下所有 `.mp4` 文件，按 `{26MMDD}{USER_CODE}{seq}` 模式提取序号，取最大值 + 1

## 用户代码 → IP 映射

> 用于记录时自动填充 IP名字 字段

| 用户代码 | 常见 IP | 说明 |
|----------|---------|------|
| D | 火影忍者 | 独立 IP |
| JR | 火影忍者 / 咒术回战 / 鬼灭之刃 | 混搭 |
| LJJ | 咒术回战 / 鬼灭之刃 / 火影忍者 | 混搭 |
| TM | 鬼灭之刃 / 火影忍者 / 咒术回战 | 混搭 |
| WY | 咒术回战 | 独立 |
| ZL | 咒术回战（竖版原视频居多） | RF来源 |
| HR | 鬼灭之刃 / 咒术回战 | 混搭 |
| M | 咒术回战 | 竖版原视频居多 |
| ZX | 火影忍者 | 独立 |

> 实际 IP 以贴图路径和 AI 识别为准，上表用于辅助判断和无匹配时兜底。

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
| 柱间 | `naruto/火影-千手柱间_*` |
| 自来也 | `naruto/火影-自来也_*` |
| 佩恩 | `naruto/火影-佩恩_*` |
| 夜凯, 死门凯 | `naruto/火影-夜凯_*` |
| 小樱 | `naruto/火影-春野樱_*` |
| 玖辛奈 | `naruto/玖辛奈_*` |
| 雏田 | `naruto/雏田_*` |
| 天天 | `naruto/天天_*` |
| 香燐 | `naruto/香燐_*` |
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

**兜底：** 无匹配 → `fallback/通用贴图.*`（标记待确认）

### 贴图素材库路径
- **搜索范围**：`/Volumes/美术AI龙虾/assets/`
- **火影**：`assets/naruto/` 子目录
- **咒术**：`assets/` 根目录

## 目标表（已禁用写表，2026-05-08）

### D 用户热点收集表
- App Token：`SYP1b0qvOaY60xszqLycOK9PnNg`
- Table ID：`tblewZ4BB4tHPnFC`
- 链接：`https://fc4dpykqzg.feishu.cn/base/SYP1b0qvOaY60xszqLycOK9PnNg?table=tblewZ4BB4tHPnFC&view=vew9Tu0iOX`

### 字段映射

| 字段名 | 值 | 说明 |
|--------|-----|------|
| `原命名` | 原视频命名 | 主键 |
| `Ipv6视频链接` | `http://[IPv6]:9092/{用户}/{后台下载}/{YYYY-MM-DD}/{文件名}` | URL 字段 |
| `状态` | `改竖` / `竖版原视频` | 单选（竖版原视频也要写表） |
| `IP名字` | 鬼灭之刃/火影忍者/咒术回战/其他 | 单选 |
| `用户` | D/JR/LJJ/ZX/WY/HR/TM/ZL/M | 单选 |
| `是否异常` | 正常/异常 | 单选 |

## API 约束
- 搜索只支持**前缀匹配**，描述文字搜不了
- 日期格式：`YYMMDD`（260420 = 2026年4月20日）

## 版本记录

### v2.2.0（2026-04-28）
- 新增：标准批处理流程章节
- 新增：竖版原视频判断标准（含像素类视频）
- 新增：用户代码 → IP 映射表

- 修正：脚本路径说明（实际生效路径为 ~/.openclaw/skills/）
- 移除：v2.0.0 旧修复日志（已过时）

### v2.1.0（2026-04-27）
- 完整重写 download.py，移除多用户复杂规则
- AI 角色识别（Vision API）集成
- 自我审查机制（下载/改竖/成品三段校验）

## 相关技能

| Skill | 职责 |
|-------|------|
| `video-reinspect` | 异常视频返工：扫描表格异常记录 → 重新改竖 → 覆盖成品 → 更新表格 |
