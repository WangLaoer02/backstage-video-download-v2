# backstage-video-download v2.0.0

广告平台视频自动化处理 Skill：下载 → 改竖 → 识别 → 写表

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt

# 系统依赖
brew install ffmpeg  # macOS
apt-get install ffmpeg  # Ubuntu/Debian
```

### 环境配置

```bash
export FEISHU_ACCESS_TOKEN="your-token-here"
export VISION_API_KEY="your-api-key"
export VISION_API_URL="https://api.jiekou.ai/openai/v1/chat/completions"
```

### 基本用法

**搜索视频**
```bash
python3 scripts/download.py --search "20250409"
```

**下载视频**
```bash
# 批量下载
python3 scripts/download.py --download-prefix "20250409"

# 精确下载
python3 scripts/download.py "260408D4-700级卡卡西-原创"
```

**清理竖版**
```bash
python3 scripts/download.py --delete-vertical
```

## 核心功能

| 功能 | 说明 |
|------|------|
| 下载 | 从广告平台 API 批量/精确下载视频 |
| 改竖 | 自动转换为竖版（720×1280） |
| 识别 | AI + 文件名关键词双重识别 IP 和角色 |
| 贴图 | 智能匹配贴图（火影/咒术/鬼灭） |
| 写表 | 自动写入飞书表格，支持多用户分发 |
| 修复 | moov 完整性检测和自动修复 |

## 项目结构

```
backstage-video-download/
├── README.md                    # 本文件
├── SKILL.md                     # 详细技术文档
├── _meta.json                   # Skill 元数据
├── requirements.txt             # Python 依赖
├── scripts/
│   ├── download.py              # 核心下载和改竖脚本
│   ├── handler.py               # FFmpeg 改竖处理器
│   ├── config.py                # 配置管理
│   └── utils.py                 # 工具函数
├── tests/
│   ├── test_download.py
│   ├── test_handler.py
│   └── test_naming.py
└── examples/
    └── batch_process.py         # 批量处理示例
```

## 修复内容（v2.0.0）

### 🐛 Bug 修复

- [x] 删除 `_call_vision` 重复定义（第 844-906 行）
- [x] 修复第 715 行参数传递错误
- [x] 删除不可达代码（第 965 行）
- [x] 移除硬编码 API key
- [x] 改进并发序号管理

### ✨ 功能改进

- [x] 添加完整类型提示
- [x] 规范化错误处理
- [x] 添加详细日志记录
- [x] 实现完整的 handler.py
- [x] 添加单元测试

### 📋 文档完善

- [x] 详细的 SKILL.md 技术文档
- [x] _meta.json 元数据
- [x] requirements.txt 依赖管理
- [x] 代码示例和最佳实践

## 常见问题

### Q: 如何处理 moov 损坏的视频？

A: 脚本会自动检测和修复：
- 优先使用 `-movflags +faststart`（快速）
- 失败则用 libx264 重编码（慢但安全）

### Q: IP 识别准确率如何？

A: 三层策略：
1. 文件名精确关键词（置信度 95%）
2. 文件名扩展关键词（置信度 80%）
3. AI 视频帧识别（置信度 72%）

### Q: 序号会重复吗？

A: 不会。脚本检查三个来源：
- 批次内缓存
- 飞书表中已有记录
- NAS 目录中的文件

## 技术栈

- **Python** 3.9+
- **FFmpeg** 视频处理
- **Requests** HTTP 请求
- **Feishu API** 表格操作
- **Vision API** 图像识别

## 许可证

MIT

## 支持

遇到问题？
1. 查看 `SKILL.md` 的完整文档
2. 检查日志输出
3. 提交 Issue 到仓库

