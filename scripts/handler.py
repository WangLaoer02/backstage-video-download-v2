#!/usr/bin/env python3
"""
改竖处理器 v2.0.0

将横版视频改为竖版（720×1280）
贴片模式：上下各 437px，中间 406px 用于视频

使用方式：
  python3 handler.py \\
    --input input.mp4 \\
    --image cover.png \\
    --output output.mp4 \\
    --preset medium
"""

import argparse
import sys
import os
import subprocess
import logging
from pathlib import Path
from typing import Tuple, Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# 竖版尺寸标准
VERTICAL_WIDTH = 720
VERTICAL_HEIGHT = 1280
VIDEO_HEIGHT = 406  # 中间视频区域
COVER_HEIGHT = (VERTICAL_HEIGHT - VIDEO_HEIGHT) // 2  # 上下各 437px

# FFmpeg 预设
PRESETS = {
    "fast": "-preset ultrafast -crf 28",
    "medium": "-preset medium -crf 23",
    "slow": "-preset slow -crf 18"
}

def validate_inputs(input_path: str, image_path: str, output_path: str) -> Tuple[bool, str]:
    """验证输入文件"""
    if not os.path.exists(input_path):
        return False, f"输入视频不存在: {input_path}"
    if not os.path.exists(image_path):
        return False, f"贴图不存在: {image_path}"

    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    return True, "验证成功"

def get_video_duration(video_path: str) -> Optional[float]:
    """获取视频时长"""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', video_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"获取视频时长失败: {e}")
    return None

def process_vertical(input_path: str, image_path: str, output_path: str, preset: str = "medium") -> Tuple[bool, str]:
    """
    改竖处理

    视频结构：
    ┌─────────────┐
    │ 上层贴图     │  437px
    ├─────────────┤
    │ 视频部分     │  406px (scale 后)
    ├─────────────┤
    │ 下层贴图     │  437px
    └─────────────┘
    总高度：1280px，宽度：720px

    Args:
        input_path: 输入视频路径
        image_path: 贴图路径
        output_path: 输出视频路径
        preset: 处理速度（fast/medium/slow）

    Returns:
        (success, message)
    """
    logger.info(f"开始改竖处理: {input_path}")
    logger.info(f"贴图: {image_path}")
    logger.info(f"输出: {output_path}")
    logger.info(f"预设: {preset}")

    # 验证输入
    valid, msg = validate_inputs(input_path, image_path, output_path)
    if not valid:
        return False, msg

    # 获取视频时长
    duration = get_video_duration(input_path)
    if duration is None:
        return False, "无法获取视频时长"

    # 构建 FFmpeg 命令
    # 策略：将贴图作为底层，上下各铺 437px
    # 视频缩放到 720x406，居中叠放

    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-i', input_path,
        '-i', image_path,
        '-i', image_path,  # 同一张贴图用两次（上下）
        '-filter_complex', (
            # 创建 1280x720 黑色背景
            f"color=black:{VERTICAL_WIDTH}x{VERTICAL_HEIGHT}:d={duration} [bg];"
            # 贴图缩放到 720x437（上层）
            f"[1] scale={VERTICAL_WIDTH}:{COVER_HEIGHT} [cover_top];"
            # 视频缩放到 720x406（中层）
            f"[0] scale={VERTICAL_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease [video_scaled];"
            # 贴图缩放到 720x437（下层）
            f"[2] scale={VERTICAL_WIDTH}:{COVER_HEIGHT} [cover_bottom];"
            # 叠放：黑色背景 + 上层贴图 + 中层视频 + 下层贴图
            f"[bg] [cover_top] overlay=0:0 [v1];"
            f"[v1] [video_scaled] overlay=0:{COVER_HEIGHT} [v2];"
            f"[v2] [cover_bottom] overlay=0:{COVER_HEIGHT + VIDEO_HEIGHT} [out]"
        ),
        '-map', '[out]',
        '-map', '0:a:0?',  # 保留音频
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p'
    ]

    # 添加预设参数
    if preset in PRESETS:
        ffmpeg_cmd.extend(PRESETS[preset].split())
    else:
        logger.warning(f"未知预设 {preset}，使用默认值")
        ffmpeg_cmd.extend(PRESETS["medium"].split())

    # 音频编码
    ffmpeg_cmd.extend(['-c:a', 'aac', '-b:a', '128k'])

    # 输出文件
    ffmpeg_cmd.append(output_path)

    logger.info(f"执行: {' '.join(ffmpeg_cmd)}")

    try:
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 分钟超时
        )

        if result.returncode == 0:
            logger.info(f"✅ 改竖成功: {output_path}")
            return True, "改竖成功"
        else:
            error = result.stderr[-500:] if result.stderr else "unknown"
            logger.error(f"❌ 改竖失败: {error}")
            return False, f"FFmpeg 错误: {error}"

    except subprocess.TimeoutExpired:
        logger.error("❌ 处理超时 (600s)")
        return False, "处理超时"
    except Exception as e:
        logger.error(f"❌ 处理异常: {e}")
        return False, str(e)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="改竖处理器 v2.0.0")
    parser.add_argument('--input', required=True, help='输入视频文件')
    parser.add_argument('--image', required=True, help='贴图文件')
    parser.add_argument('--output', required=True, help='输出视频文件')
    parser.add_argument('--preset', default='medium', choices=['fast', 'medium', 'slow'],
                        help='处理速度预设')
    parser.add_argument('--user', default='D', help='用户编码')

    args = parser.parse_args()

    success, message = process_vertical(
        args.input,
        args.image,
        args.output,
        args.preset
    )

    if success:
        print(json.dumps({
            "success": True,
            "output": args.output,
            "message": message
        }))
        sys.exit(0)
    else:
        print(json.dumps({
            "success": False,
            "error": message
        }))
        sys.exit(1)

if __name__ == "__main__":
    import json
    main()
