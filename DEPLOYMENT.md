# 部署指南

## 第一步：复制到你的 openclaw-backup 库

```bash
# 1. 克隆你的仓库
git clone https://github.com/WangLaoer02/openclaw-backup.git
cd openclaw-backup

# 2. 复制新的 Skill 版本
cp -r /tmp/backstage-video-download-v2 skills/backstage-video-download-v2

# 3. 或者：删除旧版本，替换为新版本
rm -rf skills/backstage-video-download
mv /tmp/backstage-video-download-v2 skills/backstage-video-download
```

## 第二步：安装依赖

```bash
cd skills/backstage-video-download
pip install -r requirements.txt

# 验证 ffmpeg 安装
ffmpeg -version
ffprobe -version
```

## 第三步：配置环境

```bash
# 在 ~/.bash_profile 或 ~/.zshrc 中添加：
export FEISHU_ACCESS_TOKEN="your-feishu-token"
export VISION_API_KEY="your-vision-api-key"
export VISION_API_URL="https://api.jiekou.ai/openai/v1/chat/completions"
export BACKSTAGE_SAVE_DIR="/Volumes/美术AI龙虾/D/backstage_downloads"
```

## 第四步：测试

```bash
# 搜索视频
python3 scripts/download.py --search "20250419"

# 运行单元测试
cd ../../
pytest skills/backstage-video-download/tests/ -v
```

## 第五步：提交到 Git

```bash
git add skills/backstage-video-download/
git commit -m "feat: upgrade backstage-video-download to v2.0.0

- Fix _call_vision duplicate definition bug
- Fix parameter passing error on line 715
- Move API keys to environment variables
- Implement complete handler.py
- Add comprehensive documentation
- Add unit tests and examples"

git push origin main
```

## 文件对应关系

| 原文件 | 新位置 | 说明 |
|--------|--------|------|
| SKILL.md | skills/backstage-video-download/SKILL.md | 技术文档 |
| download.py v3 | scripts/download.py（修复版） | 核心脚本 |
| handler.py（缺失） | scripts/handler.py（新增）| FFmpeg 改竖处理器 |
| _meta.json（无） | _meta.json | Skill 元数据 |
| 无 | requirements.txt | 依赖管理 |
| 无 | FIXES.md | 修复清单 |
| 无 | tests/ | 单元测试 |

## 验证清单

- [ ] 所有文件已复制到 `skills/backstage-video-download/`
- [ ] 依赖已安装：`pip install -r requirements.txt`
- [ ] 环境变量已设置
- [ ] 搜索功能正常：`python3 scripts/download.py --search "test"`
- [ ] 单元测试通过：`pytest tests/ -v`
- [ ] 已提交到 Git 并推送

## 常见问题

**Q: 为什么要创建 v2.0.0？**
A: v1 有多个严重 bug（函数重复、硬编码 key、handler.py 缺失），v2 完全修复并规范化。

**Q: 能同时运行 v1 和 v2 吗？**
A: 可以，但要确保使用不同的 BITABLE_APP_TOKEN 或添加前缀区分记录。

**Q: 如何回滚到 v1？**
A: `git revert` 相关提交即可恢复。

