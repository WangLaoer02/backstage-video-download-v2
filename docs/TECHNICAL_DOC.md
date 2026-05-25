# backstage-video-download-v2 技术文档

> 适用版本：v2.2.0 | 更新日期：2026-05-11
> 本文档描述完整的改竖工作流，供其他实例参照执行

---

## 一、系统架构

```
广告平台 API
    ↓
download.py (下载 + 改竖 + 写表)
    ↓ (关键词 / AI识别)
贴图匹配 → handler.py (FFmpeg 合成)
    ↓
成品输出 → 飞书表格
```

**关键文件路径：**

| 文件 | 路径 | 说明 |
|------|------|------|
| download.py | `~/.agents/skills/backstage-video-download-v2/scripts/download.py` | 主程序 |
| handler.py | `~/.agents/skills/backstage-video-download-v2/scripts/handler.py` | 改竖执行器 |
| config.py | `~/.agents/skills/backstage-video-download-v2/scripts/config.py` | 配置 |
| batch_pipeline.py | `~/.agents/skills/backstage-video-download-v2/scripts/batch_pipeline.py` | 批处理模板 |

> ⚠️ 实际生效路径为 `~/.agents/skills/`（不是 `~/.openclaw/skills/`）

---

## 二、环境要求

### 2.1 依赖命令

| 命令 | 用途 | 说明 |
|------|------|------|
| `ffmpeg` | 视频处理 | 必须安装 |
| `ffprobe` | 视频信息读取 | ffmpeg 附赠 |
| `mmx` | AI 视觉识别 | MiniMax CLI，需配置 API Key |

### 2.2 环境变量

```bash
# 核心路径
export BACKSTAGE_SAVE_DIR="/Volumes/美术AI龙虾"
export BACKSTAGE_ASSETS_DIR="/Volumes/美术AI龙虾/assets"

# IPv6 视频服务地址（必须按实例更新）
export IPv6_ROOT="http://[2408:8256:4c87:f19c::c42]:9092"

# Vision API（AI 角色识别）
export VISION_API_URL="http://localhost:11434/api/generate"

# 飞书配置（写表用）
export BITABLE_APP_TOKEN="SYP1b0qvOaY60xszqqLycOK9PnNg"
export BITABLE_TABLE_ID="tblewZ4BB4tHPnFC"
```

### 2.3 NAS 目录结构

```
/Volumes/美术AI龙虾/
├── {用户代码}/              ← D / JR / LJJ / TM / WY / ZL / HR / M / ZX
│   └── 后台下载/
│       └── {YYYY-MM-DD}/   ← 按日期归档
├── assets/                 ← 贴图素材库
│   ├── naruto/             ← 火影角色贴图
│   ├── jujutsu/            ← 咒术角色贴图
│   ├── kimetsu/            ← 鬼灭角色贴图
│   └── fallback/           ← 兜底通用贴图
└── 公共资源/
    └── ...（字体/贴片等）
```

---

## 三、核心参数速查

### 3.1 命令行接口

```bash
# ① 搜索：确认当天有多少条视频
python3 download.py --search "260511"

# ② 下载：批量下载横版视频（自动跳过含"改竖"的文件）
python3 download.py --download-prefix "260511"

# ③ 改竖流水线：对单条视频执行下载→改竖一体化（写表已禁用）
python3 download.py --pipeline "260511JR1-挨打回血卡卡西-原创-BY"
```

### 3.2 日期格式

- API 前缀格式：`YYMMDD`（如 `260511`）
- 目录归档格式：`YYYY-MM-DD`（如 `2026-05-11`）

### 3.3 用户代码

| 代码 | 用户 |
|------|------|
| D | D |
| JR | JR |
| LJJ | LJJ |
| TM | TM |
| WY | WY |
| ZL | ZL |
| HR | HR |
| M | M |
| ZX | ZX |

---

## 四、完整执行流程（标准三步）

> 按此顺序执行，不跳步。

### Step 1：搜索确认数量

```bash
python3 download.py --search "260511"
```

返回示例：
```json
{"success": true, "count": 9, "results": [...]}
```

记录视频数量，核查是否有遗漏。

### Step 2：批量下载

```bash
python3 download.py --download-prefix "260511"
```

- 自动跳过文件名含"改竖"的视频
- 自动跳过已是竖版（720×1280）的视频
- 返回下载数量和路径列表

### Step 3：逐条执行改竖

对每条视频运行 `--pipeline`：

```bash
python3 download.py --pipeline "260511JR1-挨打回血卡卡西-原创-BY"
```

返回：
```json
{
  "success": true,
  "downloaded": "/Volumes/美术AI龙虾/JR/后台下载/2026-05-11/260511JR1-...mp4",
  "vertical": "/Volumes/美术AI龙虾/JR/后台下载/2026-05-11/260511JR2-龙虾改竖挨打回血卡卡西-原创-BY.mp4",
  "link": "http://[IPv6]:9092/JR/后台下载/2026-05-11/260511JR2-龙虾改竖挨打回血卡卡西-原创-BY.mp4"
}
```

**逐条执行好处：** 每条独立，可追踪、可定位异常。

---

## 五、改竖判断规则

### 5.1 跳过改竖（竖版原视频）

| 判断条件 | 说明 |
|----------|------|
| 视频尺寸 720×1280 | 已是竖版 |
| 文件名含"改竖" | 已处理过 |
| 尺寸 1920×3414 竖版 | 改竖处理 |

### 5.2 贴图匹配逻辑（优先级顺序）

```
① 文件名关键词匹配
   └─ 火/鬼/咒关键词 → assets/{subdir}/ 下找贴图
   └─ 精确匹配：鼬→火影-宇智波鼬_*.jpg
   └─ 模糊匹配：找到含该角色名的任意文件

② AI 角色识别（文件名无命中时触发）
   └─ 从视频 30% 处提取关键帧
   └─ 调用 mmx vision describe（MiniMax VLM）
   └─ 候选角色：火影/咒术/鬼灭主流角色
   └─ 识别结果再双向模糊匹配贴图

③ 兜底
   └─ assets/fallback/ 通用贴图
   └─ 标记 cover_uncertain=True（写表时"待确认"）
```

### 5.3 贴图目录结构

```
assets/
├── naruto/        ← 火影忍者角色贴图
├── jujutsu/        ← 咒术回战角色贴图
├── kimetsu/        ← 鬼灭之刃角色贴图
└── fallback/       ← 兜底通用贴图
```

贴图命名规范：`{IP}-{角色名}_{变体}.jpg/png`

---

## 六、成品命名规则

### 6.1 文件名格式

```
{26MMDD}{USER_CODE}{seq}-龙虾改竖{原始内容}-{原始后缀}.mp4
```

示例：
```
260511JR2-龙虾改竖挨打回血卡卡西-原创-BY.mp4
```

### 6.2 序号分配规则

> **成品序号 = 扫描该日期目录下所有 .mp4（原始+成品）的最大序号 + 1**

- 扫描范围：`{用户代码}/后台下载/{YYYY-MM-DD}/` 下所有 `.mp4`
- 跳过含 `vertical_` 的临时文件
- 同批次追加：前批成品号存在则从其继续编号

### 6.3 输出目录

```
/Volumes/美术AI龙虾/{用户代码}/后台下载/{YYYY-MM-DD}/
├── 260511JR1-挨打回血卡卡西-原创-BY.mp4    ← 原始横版
└── 260511JR2-龙虾改竖挨打回血卡卡西-原创-BY.mp4  ← 成品竖版
```

---

## 七、改竖技术规格（handler.py）

### 7.1 视频结构

```
┌────────────────────────┐
│ 上层贴图（cover_top）   │  437px
├────────────────────────┤
│ 中间视频（scale 720×406）│  406px
├────────────────────────┤
│ 下层贴图（cover_bottom） │  437px
└────────────────────────┘
总尺寸：720 × 1280 px
```

### 7.2 FFmpeg 参数

| 参数 | 值 |
|------|------|
| 输出分辨率 | 720×1280 |
| 视频区域 | 720×406（居中） |
| 贴图区域 | 720×437 × 2（上下） |
| 视频编码 | libx264 |
| 色彩空间 | yuv420p |
| 音频编码 | aac 128k |

### 7.3 FFmpeg 合成流程

```
1. 创建 720×1280 黑色背景（时长=原视频时长）
2. 贴图缩放到 720×437（上下各一张）
3. 视频缩放到 720×406（保持宽高比，不足部分留黑）
4. 按顺序叠加：背景 → 上贴图 → 视频 → 下贴图
5. 保留原音频轨道
```

### 7.4 预设速度

| preset | 速度 | 质量 | 适用场景 |
|--------|------|------|----------|
| fast | ultrafast | 低 | 快速预览 |
| medium | medium | 中 | 标准生产（默认）|
| slow | slow | 高 | 最终成品 |

---

## 八、飞书写表规范（已禁用，仅作记录参考）

> ⚠️ 写表功能已于 2026-05-08 禁用，需手动操作。

### 8.1 目标表格

- **App Token**：`SYP1b0qvOaY60xszqLycOK9PnNg`
- **Table ID**：`tblewZ4BB4tHPnFC`
- **链接**：`https://fc4dpykqzg.feishu.cn/base/SYP1b0qvOaY60xszqLycOK9PnNg?table=tblewZ4BB4tHPnFC&view=vew9Tu0iOX`

### 8.2 字段映射

| 字段名 | 值 | 说明 |
|--------|-----|------|
| 原命名 | 原始视频命名 | 主键 |
| Ipv6视频链接 | `http://[IPv6]:9092/{用户}/后台下载/{YYYY-MM-DD}/{成品名}.mp4` | URL |
| 状态 | `改竖` / `竖版原视频` | 单选 |
| IP名字 | `火影忍者` / `鬼灭之刃` / `咒术回战` / `其他` | 单选 |
| 用户 | D/JR/LJJ/TM/WY/ZL/HR/M/ZX | 单选 |
| 是否异常 | `正常` / `异常` | 单选 |

### 8.3 写表逻辑（download.py 内置）

```python
def _retry_write_to_bitable(
    video_name, ipv6_link, status,
    ip_name, user, final_name, cover_uncertain=False
):
    # 1. 获取 tenant_access_token（appId + appSecret）
    # 2. 构造 record 写入表格
    # 3. 超时重试 3 次
    # 4. 写表已禁用：输出 ⏭️ skip 提示，不实际调用 API
```

---

## 九、批次执行检查清单

执行完一批改竖任务后，逐一核查：

- [ ] `--search` 数量 = `--download-prefix` 下载数量（除去含"改竖"跳过项）
- [ ] 每条 `--pipeline` 返回 `success: true`
- [ ] 成品文件存在于目标目录（720×1280）
- [ ] 异常条目记录到 `memory/errors.md`
- [ ] 手动写入飞书表格（写表禁用期间）

---

## 十、常见问题

### Q1：AI 识别返回"未知"但文件名有角色名怎么办？
**A：** `find_cover_image()` 先做文件名关键词匹配，AI 识别是兜底。只有文件名完全没有关键词时才触发 AI。

### Q2：竖版原视频（720×1280）也要写表吗？
**A：** 是的，状态填 `竖版原视频`，IP 名字根据文件名判断。

### Q3：贴图找不到怎么办？
**A：** 走兜底 `assets/fallback/` → `cover_uncertain=True` → 标记待确认。手动补图后可在 `video-reinspect` Skill 中重新处理。

### Q4：视频下载后没有 moov 可以播放怎么办？
**A：** `download.py` 内置 moov 检测，损坏视频会自动触发 `--rebuild` 修复（重编码 + faststart）。

### Q5：成品序号跳号了怎么办？
**A：** `get_next_seq()` 每次全量扫描目录，取 max+1，不会跳号。检查是否有多实例同时写入。

---

## 十一、调用示例（直接复制使用）

### 标准单条执行
```bash
cd ~/.agents/skills/backstage-video-download-v2/scripts
python3 download.py --pipeline "260511JR1-挨打回血卡卡西-原创-BY"
```

### 标准批次执行（先搜索确认，再逐条改竖）
```bash
# Step 1：确认数量
python3 download.py --search "260511"

# Step 2：下载（可跳过，直接改竖即可，--pipeline 包含下载）
python3 download.py --download-prefix "260511"

# Step 3：逐条改竖
for name in "JR1" "TM1" "TM2" "TM6" "TM7" "TM8" "ZL1" "ZL2" "ZL3"; do
  python3 download.py --pipeline "$name的完整命名"
done
```

### 手动批量脚本（复制 batch_pipeline.py 改写）
```python
videos = [
    "260511JR1-挨打回血卡卡西-原创-BY",
    "260511TM1-DNF套黑死牟mod战斗展示-原创-ZZX",
    # ...更多视频名
]

for v in videos:
    r = subprocess.run(
        ["python3", "download.py", "--pipeline", v],
        capture_output=True, text=True
    )
    d = json.loads(r.stdout)
    if d.get("success"):
        print(f"✅ {v}")
    else:
        print(f"❌ {v}: {d.get('error')}")
```

---

## 十二、版本记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v2.2.0 | 2026-04-28 | 标准批处理流程 + 竖版原视频判断标准 + 用户代码→IP映射表 |
| v2.1.0 | 2026-04-27 | 重写 download.py，集成 AI 角色识别 |
| v1.0.0 | 早期 | 基础下载功能 |

---

*文档生成时间：2026-05-11 | 基于 Dw虾 实例执行经验整理*