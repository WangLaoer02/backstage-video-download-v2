# Backstage Video Download V2 - Guide

## Build & Test Commands
- Install: `pip install -r requirements.txt`
- Run: `python scripts/download.py`
- Test: `pytest tests/`

## Code Style & Rules
- **Error Handling**: 必须捕获网络异常并重试，参考 download.py 的重试逻辑。
- **Video Processing**: 处理竖屏转换时，必须保留原始元数据。
- **Logging**: 统一使用 config.py 中定义的日志格式。
- **Context**: 之前修复过多线程下载时的文件锁定问题，修改 download.py 时务必保留 Lock 机制。
