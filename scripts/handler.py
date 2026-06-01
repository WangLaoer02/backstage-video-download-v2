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
import json
import sys
import os
import subprocess
import logging
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

def get_video_dimensions(video_path: str) -> Optional[Tuple[int, int]]:
    """读取首个视频流的编码尺寸。"""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0',
             video_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            width, height = result.stdout.strip().split("x", 1)
            return int(width), int(height)
    except Exception as e:
        logger.error(f"获取视频尺寸失败: {e}")
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

    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-i', input_path,
        '-loop', '1', '-framerate', '30', '-i', image_path,
        '-filter_complex', (
            f"color=black:{VERTICAL_WIDTH}x{VERTICAL_HEIGHT}:d={duration} [bg];"
            f"[1:v] scale={VERTICAL_WIDTH}:{COVER_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={VERTICAL_WIDTH}:{COVER_HEIGHT},setsar=1,format=rgba [cover];"
            f"[cover] split=2 [cover_top][cover_bottom];"
            f"[0:v] scale={VERTICAL_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={VERTICAL_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1,format=rgba [video_scaled];"
            f"[bg][cover_top] overlay=0:0:shortest=0 [v1];"
            f"[v1][video_scaled] overlay=0:{COVER_HEIGHT}:shortest=0 [v2];"
            f"[v2][cover_bottom] overlay=0:{COVER_HEIGHT + VIDEO_HEIGHT}:shortest=0,"
            f"format=yuv420p,setsar=1 [out]"
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

    ffmpeg_cmd.extend([
        '-c:a', 'aac', '-b:a', '128k',
        '-movflags', '+faststart',
        '-t', f"{duration:.3f}"
    ])

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
            dims = get_video_dimensions(output_path)
            if dims != (VERTICAL_WIDTH, VERTICAL_HEIGHT):
                return False, f"输出尺寸异常: {dims}, 期望 {VERTICAL_WIDTH}x{VERTICAL_HEIGHT}"
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
