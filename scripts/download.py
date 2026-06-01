#!/usr/bin/env python3
"""
后台视频下载→改竖 自动化（写表已禁用 v3.1）
移除多用户/复杂规则 - 保留核心三环节
"""
import json, sys, os, re, requests, subprocess, tempfile, shutil, time, random, uuid
from pathlib import Path
from urllib.parse import quote
from datetime import datetime

try:
    from config import SAVE_DIR, ASSETS_DIR, API_BASE, IPv6_ROOT, BITABLE_APP_TOKEN, BITABLE_TABLE_ID, FEISHU_ACCESS_TOKEN
except ImportError:
    SAVE_DIR = Path(os.getenv("BACKSTAGE_SAVE_DIR", "/Volumes/美术AI龙虾"))
    ASSETS_DIR = Path(os.getenv("BACKSTAGE_ASSETS_DIR", "/Volumes/美术AI龙虾/assets"))
    API_BASE = "http://adopenplatform.rongyao666.com/app/data/api/ApiGetJrttVideoByCategory.php"
    IPv6_ROOT = os.getenv("IPv6_ROOT", "http://[2408:8256:4c87:f19c::c42]:9092")
    BITABLE_APP_TOKEN = os.getenv("BITABLE_APP_TOKEN", "SYP1b0qvOaY60xszqLycOK9PnNg")
    BITABLE_TABLE_ID = os.getenv("BITABLE_TABLE_ID", "tblewZ4BB4tHPnFC")
    FEISHU_ACCESS_TOKEN = os.getenv("FEISHU_ACCESS_TOKEN", "")

HANDLER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "handler.py")
EXPECTED_VERTICAL_DIMS = (720, 1280)
STATE_FILENAME = ".backstage_pipeline_state.json"
LOCK_FILENAME = ".backstage_pipeline.lock"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

def get_date_subdir(date_str):
    """按日期创建子目录：2026-04-21"""
    if len(date_str) == 6 and date_str.startswith('26'):
        mm, dd = int(date_str[2:4]), int(date_str[4:6])
        return f"2026-{mm:02d}-{dd:02d}"
    if len(date_str) == 8 and date_str.startswith('2026'):
        mm, dd = int(date_str[4:6]), int(date_str[6:8])
        return f"2026-{mm:02d}-{dd:02d}"
    return None

def get_date_user_subdir(date_str, user_code):
    """按日期+用户创建子目录：2026-04-21/D/"""
    date_subdir = get_date_subdir(date_str)
    if not date_subdir:
        return None
    return f"{date_subdir}/{user_code}"

def get_save_dir(date_str, user_code):
    """获取用户的保存目录：SAVE_DIR/{user_code}/后台下载/YYYY-MM-DD/"""
    date_subdir = get_date_subdir(date_str)
    save_path = SAVE_DIR / user_code / "后台下载" / date_subdir
    save_path.mkdir(parents=True, exist_ok=True)
    return save_path

class PipelineLock:
    """Per-user/date lock to prevent duplicate vertical outputs and sequence races."""
    def __init__(self, date_str, user_code):
        self.path = get_save_dir(date_str, user_code) / LOCK_FILENAME
        self.fp = None

    def __enter__(self):
        import fcntl
        self.fp = open(self.path, "a")
        fcntl.flock(self.fp.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        import fcntl
        if self.fp:
            fcntl.flock(self.fp.fileno(), fcntl.LOCK_UN)
            self.fp.close()
        return False

def _state_path(date_str, user_code):
    return get_save_dir(date_str, user_code) / STATE_FILENAME

def _load_state(date_str, user_code):
    path = _state_path(date_str, user_code)
    if not path.exists():
        return {"version": 1, "records": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("records"), dict):
            return data
    except Exception:
        pass
    return {"version": 1, "records": {}}

def _save_state(date_str, user_code, state):
    path = _state_path(date_str, user_code)
    tmp_path = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp_path, path)

def parse_filename(name):
    """解析 {26MMDD}{USER_CODE}{seq}-{content}-{suffix}.mp4 或 {2026MMDD}{USER_CODE}{seq}-{content}-{suffix}.mp4"""
    stem = re.sub(r'\.mp4$', '', name)
    # 支持 26MMDDUSER1-内容、26MMDD-USER1-内容、2026MMDDUSER1-内容。
    m = re.match(r'^(26\d{4})-?([A-Z]+)(\d+)-(.+)$', stem)
    if m:
        date, user_code, seq, body = m.groups()
    else:
        m = re.match(r'^(2026\d{4})-?([A-Z]+)(\d+)-(.+)$', stem)
        if not m:
            return None
        full_date, user_code, seq, body = m.groups()
        date = "26" + full_date[4:]

    if "-" in body:
        content, suffix = body.rsplit("-", 1)
    else:
        content, suffix = body, ""
    if not content:
        return None
    return {"date": date, "user_code": user_code, "seq": int(seq), "content": content, "suffix": suffix}

def get_date_dir(date_str):
    """返回 YYYY-MM-DD 格式的日期目录名"""
    return get_date_subdir(date_str)

def get_next_seq(date, user_code):
    """扫描日期目录，找到相同用户代码的最大序号，返回下一个序号。

    扫描范围：SAVE_DIR/YYYY-MM-DD/ 下所有 mp4（原始+成品）
    跳过含 "vertical_" 的临时文件。
    """
    max_seq = 0
    save_dir = get_save_dir(date, user_code)
    if not save_dir.exists():
        return 1
    for fname in os.listdir(save_dir):
        if not fname.lower().endswith('.mp4'):
            continue
        if 'vertical_' in fname:
            continue
        m = re.match(rf'^{date}{user_code}(\d+)-', fname)
        if m:
            seq = int(m.group(1))
            max_seq = max(max_seq, seq)
    return max_seq + 1

def build_filename(date, user_code, seq, content, suffix):
    """组合输出文件名：{26MMDD}{USER_CODE}{seq}-龙虾改竖{content}-{suffix}.mp4"""
    suffix_part = f"-{suffix}" if suffix else ""
    return f"{date}{user_code}{seq}-龙虾改竖{content}{suffix_part}.mp4"

def is_generated_vertical_name(name):
    """Only skip products generated by this pipeline, not source titles containing 改竖."""
    return "龙虾改竖" in name

def build_ipv6_link(parsed, final_name):
    date_str = parsed["date"]
    date_folder = f"20{date_str[0:2]}-{date_str[2:4]}-{date_str[4:6]}"
    return f"{IPv6_ROOT}/{parsed['user_code']}/后台下载/{date_folder}/{final_name}"

def _call_vision_api(frame_path):
    """从视频关键帧调用 MiniMax Vision API 识别 IP 角色（通过 mmx CLI）"""
    import subprocess, os, json
    if not os.path.exists(frame_path):
        return None

    # 使用 mmx vision describe 调用 MiniMax VLM
    try:
        result = subprocess.run(
            ["mmx", "vision", "describe", frame_path, "--output", "json", "--non-interactive"],
            capture_output=True, text=True, timeout=30, cwd=os.path.dirname(frame_path) or "/tmp"
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        description = data.get("description", "") or data.get("content", "") or ""
        # 提取纯文本描述（去掉场景说明）
        return description[:200] if description else None
    except Exception as e:
        print(json.dumps({"warning": f"Vision API 调用失败: {e}"}), file=sys.stderr)
        return None

def _extract_key_frame(video_path, timestamp_pct=0.3):
    """从视频指定百分比处提取一帧作为关键帧"""
    import uuid
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return None
        duration = float(result.stdout.strip())
        target_ts = duration * timestamp_pct

        frame_path = f"/tmp/vision_frame_{uuid.uuid4().hex}.jpg"
        r = subprocess.run([
            "ffmpeg", "-y", "-ss", str(target_ts), "-i", video_path,
            "-vframes", "1", "-q:v", "2", "-s", "720x406", frame_path
        ], capture_output=True, timeout=30)
        if r.returncode == 0 and os.path.exists(frame_path):
            return frame_path
    except Exception as e:
        print(json.dumps({"warning": f"抽帧失败: {e}"}), file=sys.stderr)
    return None

def _call_vision_api_v2(frame_path):
    """Vision API 级联: MiniMax mmx → Ollama qwen2.5vl:7b 兜底"""
    import subprocess, os, json, requests, base64, pathlib

    if not os.path.exists(frame_path):
        return None

    prompt = (
        "识别这个图片中最显著的动漫角色名称，只返回角色名，不要解释。"
        "候选：火影忍者（鸣人/鼬/斑/佐助/小樱/雏田/卡卡西/佩恩），"
        "咒术回战（五条/宿傩/虎杖/伏黑/乙骨/真人/东堂），"
        "鬼灭之刃（炭治郎/祢豆子/善逸/蝴蝶/甘露寺/义勇/杏寿郎）。"
        "找不到时只返回'未知'。"
    )

    def _extract(content):
        if not content or content in ("未知","无法识别","无"):
            return content if content else None
        # 完整角色关键词（从贴图库提取）
        chars = [
            "宇智波鼬","宇智波斑","宇智波佐助","漩涡鸣人","千手柱间","佩恩","纲手","自来也",
            "夜凯","旗木卡卡西","春野樱","日向雏田","迈特凯","宇智波带土",
            "五条悟","宿傩","虎杖悠仁","伏黑甚尔","伏黑惠","乙骨忧太","真人","东堂葵",
            "灶门炭治郎","灶门祢豆子","我妻善逸","蝴蝶忍","甘露寺蜜璃","富冈义勇",
            "炼狱杏寿郎","猗窝座","岩柱","黑死牟","继国缘一",
            # 别名+单字匹配
            "鼬","斑","佐助","鸣人","水门","柱间","纲手","小樱","凯","带土",
            "五条","宿傩","虎杖","伏黑","乙骨","真人","东堂",
            "炭治郎","祢豆子","善逸","蝴蝶","甘露寺","义勇","杏寿郎","猗窝座",
            "行冥","岩柱","悲鸣","大蛇丸","小南","迪达拉","飞段","香燐","自来也",
        ]
        for c in chars:
            if c in content:
                return c
        return None

    # 1. MiniMax mmx
    try:
        r = subprocess.run(
            ["mmx","vision","describe","--image",frame_path,
             "--prompt",prompt,"--output","json","--non-interactive"],
            capture_output=True, text=True, timeout=60
        )
        if r.returncode == 0:
            d = json.loads(r.stdout)
            txt = (d.get("content") or "").strip()
            role = _extract(txt)
            if role and role not in ("未知","无法识别","无"):
                return role
            # MiniMax未命中或返回未知 → 继续Ollama
    except Exception:
        pass

    # 2. Ollama qwen2.5vl:7b 兜底（不耗额度）
    try:
        b64 = base64.b64encode(pathlib.Path(frame_path).read_bytes()).decode()
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model":"qwen2.5vl:7b","prompt":prompt,"images":[b64],"stream":False},
            timeout=90
        )
        if resp.status_code == 200:
            txt = resp.json().get("response","").strip()
            role = _extract(txt)
            if role and role not in ("未知","无法识别","无"):
                return role
    except Exception:
        pass

    return None




def find_cover_image(filename="", video_path=None):
    """
    贴图匹配（与 SKILL.md v2.0.0 一致）：
    1. Kimetsu 关键词 → assets/kimetsu/
    2. Jujutsu 关键词 → assets/jujutsu/
    3. Naruto 关键词 → assets/naruto/
    4. 【新增】Vision API 识别（关键词无命中时）→ AI 抽帧识别 IP
    5. 兜底 → assets/fallback/ 通用贴图（标记待确认）

    Returns:
        tuple: (贴图路径, 是否为兜底) — 有结果时
        None: 完全无法匹配
    """
    import glob

    kimetsu_map = {
        "义勇": "富冈义勇", "富冈": "富冈义勇", "炭治郎": "灶门炭治郎",
        "善逸": "我妻善逸", "祢豆子": "灶门祢豆子", "蜜璃": "甘露寺蜜璃",
        "甘露寺": "甘露寺蜜璃", "蝴蝶": "蝴蝶忍", "蝴蝶忍": "蝴蝶忍",
        "岩柱": "岩柱", "悲鸣": "岩柱", "行冥": "岩柱",
        "炼狱": "炼狱杏寿郎", "杏寿郎": "炼狱杏寿郎",
        "黑死牟": "黑死牟",
    }
    jujutsu_map = {
        "甚尔": "伏黑甚尔", "伏黑": "伏黑甚尔", "宿傩": "宿傩",
        "五条悟": "五条悟", "五条": "五条悟", "虎杖": "虎杖悠仁", "七海": "七海",
        "东堂": "东堂葵", "禅院": "禅院", "真人": "真人",
        "夏油": "夏油杰", "乙骨": "乙骨",
    }
    naruto_map = {
        "鼬": "宇智波鼬", "斑": "宇智波斑", "佐助": "宇智波佐助",
        "鸣人": "漩涡鸣人", "水门": "波风水门", "纲手": "纲手",
        "柱间": "千手柱间", "初代": "千手柱间", "初代火影": "千手柱间", "自来也": "自来也", "佩恩": "佩恩",
        "夜凯": "夜凯", "小樱": "春野樱",
        "卡卡西": "旗木卡卡西", "凯": "迈特凯",
    }

    def search_ip(ip_keyword_map, subdir):
        for kw, char in ip_keyword_map.items():
            if kw in filename:
                for ext in ["jpg", "png", "jpeg", "webp"]:
                    dir_path = Path(ASSETS_DIR) / subdir
                    paths = list(dir_path.glob(f"*{char}*.{ext}"))
                    if paths:
                        return str(random.choice(paths))
                    # 模糊：只要文件名包含该词就行
                    all_paths = list(Path(ASSETS_DIR).rglob(f"*{char}*.{ext}"))
                    if all_paths:
                        return str(random.choice(all_paths))
        return None

    # 1. 鬼灭
    result = search_ip(kimetsu_map, "kimetsu")
    if result:
        return result, False
    # 2. 咒术
    result = search_ip(jujutsu_map, "jujutsu")
    if result:
        return result, False
    # 3. 火影
    result = search_ip(naruto_map, "naruto")
    if result:
        return result, False

    # 4. 【新增】AI 抽帧识别：关键词无命中 → 提取关键帧 → Vision API
    print(json.dumps({"info": f"关键词未匹配 '{filename}'，启动 AI 角色识别..."}), file=sys.stderr)
    frame_path = _extract_key_frame(video_path) if video_path else None
    if frame_path:
        ai_result = _call_vision_api_v2(frame_path)
        if ai_result:
            print(json.dumps({"info": f"AI 识别结果: {ai_result}"}), file=sys.stderr)
            # P2: 双向模糊匹配 — 把 AI 返回的词当作关键词，在所有候选角色名中找交集
            all_chars = {**naruto_map, **jujutsu_map, **kimetsu_map}
            found_path = None
            for kw, char in all_chars.items():
                # kw 命中 AI 结果，或者 AI 结果里有 kw 的任意一个字
                if kw in ai_result or char in ai_result or any(c in ai_result for c in kw):
                    for subdir in ["naruto", "jujutsu", "kimetsu"]:
                        dir_path = Path(ASSETS_DIR) / subdir
                        for ext in ["jpg", "png", "jpeg", "webp"]:
                            candidates = list(dir_path.glob(f"*{char}*.{ext}"))
                            if candidates:
                                return str(random.choice(candidates)), False
                            all_cands = list(Path(ASSETS_DIR).rglob(f"*{char}*.{ext}"))
                            if all_cands:
                                return str(random.choice(all_cands)), False
        try:
            os.remove(frame_path)
        except:
            pass

    # 兜底：专用 fallback 目录通用贴图
    fallback_dir = Path(ASSETS_DIR) / "fallback"
    if fallback_dir.exists():
        imgs = []
        for ext in ["jpg", "png", "jpeg", "webp"]:
            imgs.extend(fallback_dir.glob(f"*.{ext}"))
        if imgs:
            return str(random.choice(imgs)), True   # (path, is_fallback=True → 写表时标记待确认)
    return None, False

def check_moov_integrity(path):
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name", "-of", "json", path], capture_output=True, timeout=15)
        return result.returncode == 0
    except:
        return False

def repair_moov(path):
    dir_name = os.path.dirname(path) or "."
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4", dir=dir_name)
    os.close(tmp_fd)

    try:
        r1 = subprocess.run(["ffmpeg", "-y", "-i", path, "-c", "copy", "-movflags", "+faststart", tmp_path], capture_output=True, timeout=180)
        if r1.returncode == 0:
            shutil.move(tmp_path, path)
            return True
    except:
        pass

    try:
        r2 = subprocess.run(["ffmpeg", "-y", "-i", path, "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-movflags", "+faststart", tmp_path], capture_output=True, timeout=600)
        if r2.returncode == 0:
            shutil.move(tmp_path, path)
            return True
    except:
        pass
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass

    return False

def get_video_dimensions(video_path):
    """返回 (width, height)，失败返回 None"""
    try:
        import re
        result = subprocess.run(
            ["ffprobe", "-v", "error",
             "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=s=x:p=0", video_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            w, h = map(int, result.stdout.strip().split("x"))
            return w, h
    except:
        pass
    return None

def is_vertical_video(video_path):
    return get_video_dimensions(video_path) == EXPECTED_VERTICAL_DIMS

def _is_valid_completed_output(path):
    if not path:
        return False
    ok, _ = _validate_video_file(str(path), min_size_kb=50)
    if not ok:
        return False
    return is_vertical_video(str(path))

def _find_existing_vertical(video_name, parsed, source_path=None):
    save_dir = get_save_dir(parsed["date"], parsed["user_code"])
    prefix = f"{parsed['date']}{parsed['user_code']}"
    suffix_part = f"-{parsed['suffix']}" if parsed["suffix"] else ""
    suffix = f"-龙虾改竖{parsed['content']}{suffix_part}.mp4"
    matches = []
    for path in save_dir.glob(f"{prefix}*-龙虾改竖*.mp4"):
        if path.name.endswith(suffix) and _is_valid_completed_output(path):
            if source_path and path.stat().st_mtime < Path(source_path).stat().st_mtime:
                continue
            seq_match = re.match(rf'^{parsed["date"]}{parsed["user_code"]}(\d+)-', path.name)
            seq = int(seq_match.group(1)) if seq_match else 0
            matches.append((seq, path))
    if len(matches) == 1:
        return str(matches[0][1])
    return None

def process_vertical(video_path, cover_image):
    if not cover_image:
        return False, "无可用贴图"

    # 检测视频尺寸，跳过已是竖版的视频
    dims = get_video_dimensions(video_path)
    if dims:
        w, h = dims
        if w == 720 and h == 1280:
            print(json.dumps({"warning": f"视频已是 720x1280，跳过改竖"}), file=sys.stderr)
            # 复制原文件作为"改竖成品"
            return True, video_path
        print(f"视频尺寸: {w}x{h}，执行改竖", file=sys.stderr)

    if not check_moov_integrity(video_path):
        if not repair_moov(video_path):
            return False, "源文件损坏且修复失败"

    output_path = os.path.join(tempfile.gettempdir(), f"vertical_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex}.mp4")
    cmd = ["python3", HANDLER_SCRIPT, "--input", video_path, "--image", cover_image, "--output", output_path, "--preset", "medium"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=os.path.dirname(HANDLER_SCRIPT))
        if result.returncode == 0 and os.path.exists(output_path):
            ok, msg = _validate_video_file(output_path, min_size_kb=20)
            if not ok:
                return False, f"改竖输出文件异常: {msg}"
            if not is_vertical_video(output_path):
                return False, f"改竖输出尺寸异常: {get_video_dimensions(output_path)}"
            return True, output_path
        err = (result.stderr or result.stdout or "").strip()
        if err:
            return False, err[-500:]
    except Exception as e:
        return False, str(e)

    return False, "改竖失败"

def search_videos(prefix):
    encoded = quote(prefix, safe='')
    url = f"{API_BASE}?name={encoded}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None, f"API 失败: {resp.status_code}"
        data = resp.json()
    except Exception as e:
        return None, f"请求异常: {e}"

    info = data.get('info', [])
    if not info:
        return [], None

    results = []
    for v in info:
        name = v.get('name', '')
        parsed = parse_filename(name)
        if parsed:
            local_path = get_save_dir(parsed["date"], parsed["user_code"]) / f"{name}.mp4"
        else:
            local_path = SAVE_DIR / f"{name}.mp4"
        results.append({
            "name": name,
            "id": v.get('id', ''),
            "video_url": v.get('video_url', ''),
            "already_downloaded": os.path.exists(local_path),
            "size_mb": os.path.getsize(local_path) // 1024 // 1024 if os.path.exists(local_path) else None
        })
    return results, None

def _eligible_source_names(results):
    names = []
    seen = set()
    for item in results:
        name = item.get("name", "")
        if not name or is_generated_vertical_name(name):
            continue
        if not parse_filename(name):
            continue
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names

def _missing_sequences(names):
    groups = {}
    for name in names:
        parsed = parse_filename(name)
        if not parsed:
            continue
        key = (parsed["date"], parsed["user_code"])
        groups.setdefault(key, set()).add(parsed["seq"])
    missing = []
    for (date, user_code), seqs in sorted(groups.items()):
        if not seqs:
            continue
        expected = set(range(min(seqs), max(seqs) + 1))
        gaps = sorted(expected - seqs)
        if gaps:
            missing.append({"date": date, "user_code": user_code, "missing_seq": gaps})
    return missing

def run_batch_pipeline(prefix, dry_run=False):
    results, err = search_videos(prefix)
    if err:
        return {"success": False, "error": err}

    names = _eligible_source_names(results)
    skipped = [v.get("name", "") for v in results if is_generated_vertical_name(v.get("name", ""))]
    missing = _missing_sequences(names)
    if dry_run:
        return {
            "success": True,
            "prefix": prefix,
            "total": len(results),
            "eligible": len(names),
            "skipped_vertical": len(skipped),
            "missing_sequences": missing,
            "todo": names
        }

    ok, fail = [], []
    for name in names:
        result = full_pipeline(name)
        if result.get("success"):
            ok.append({"name": name, "vertical": result.get("vertical"), "reused": result.get("reused_existing", False)})
        else:
            fail.append({"name": name, "error": result.get("error", "unknown")})

    return {
        "success": len(fail) == 0 and len(missing) == 0,
        "prefix": prefix,
        "total": len(results),
        "eligible": len(names),
        "processed": len(ok),
        "failed": len(fail),
        "skipped_vertical": len(skipped),
        "missing_sequences": missing,
        "processed_list": ok,
        "failed_list": fail,
        "skipped_list": skipped
    }

def download_single(video_name):
    parsed = parse_filename(video_name)
    if not parsed:
        return False, "文件名格式错误", None

    save_dir = get_save_dir(parsed["date"], parsed["user_code"])
    local_path = save_dir / f"{video_name}.mp4"
    if os.path.exists(local_path):
        return True, f"已存在({os.path.getsize(local_path)//1024//1024}MB)", str(local_path)

    encoded = quote(video_name, safe='')
    url = f"{API_BASE}?name={encoded}"

    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return False, f"API 返回 {resp.status_code}", None
        data = resp.json()
    except Exception as e:
        return False, f"API 请求失败: {e}", None

    info = data.get('info', [])
    if not info:
        return False, f"无匹配结果", None

    matched = next((v for v in info if v.get('name') == video_name), None)
    if not matched:
        return False, "无精确匹配结果", None
    video_url = matched.get('video_url')
    if not video_url:
        return False, "无 video_url", None

    name = matched.get('name', video_name)
    user_code = parsed["user_code"]
    local_path = save_dir / f"{name}.mp4"

    if os.path.exists(local_path):
        # 已存在则直接返回，跳过下载
        return True, f"已存在({os.path.getsize(local_path)//1024//1024}MB)", str(local_path)

    try:
        vr = requests.get(video_url, stream=True, timeout=120)
        vr.raise_for_status()
        with open(local_path, 'wb') as f:
            for chunk in vr.iter_content(chunk_size=8192):
                f.write(chunk)
        return True, f"下载完成({os.path.getsize(local_path)//1024//1024}MB)", str(local_path)
    except Exception as e:
        return False, f"下载失败: {e}", None

def _get_tenant_token():
    """获取飞书 tenant access token（使用 requests 避免代理缓存问题）"""
    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": "cli_a938d27bfc78dced", "app_secret": "zISGY2UlMakJKK9z82j0AblZieQV8vk0"},
            timeout=10
        )
        result = resp.json()
        if result.get("code") == 0:
            return result.get("tenant_access_token", "")
    except:
        pass
    return ""

def _bitable_check_exists(original_name, token):
    """查询记录是否已存在于表格中。

    匹配策略：
    1. 按【原命名】精确匹配
    2. 无法精确匹配时，按【日期+用户代码】模糊匹配（处理文件名后缀变化，如 D-ZZH→原创）

    返回：record_id 或 None
    """
    parsed = parse_filename(original_name)

    # 策略1：精确原命名匹配
    search_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records/search"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    exact_payload = {
        "filter": {"conjunction": "and", "conditions": [{"field_name": "原命名", "operator": "is", "value": [original_name]}]},
        "page_size": 1
    }
    try:
        resp = requests.post(search_url, headers=headers, json=exact_payload, timeout=15)
        result = resp.json()
        if result.get("code") == 0:
            items = result.get("data", {}).get("items", [])
            if items:
                return items[0].get("record_id")
    except Exception:
        pass

    # 策略2：按用户代码匹配（文件名后缀变化时降级保底）
    if parsed:
        user_code = parsed.get("user_code")
        if user_code:
            user_payload = {
                "filter": {"conjunction": "and", "conditions": [{"field_name": "用户", "operator": "is", "value": [user_code]}]},
                "page_size": 1
            }
            try:
                resp = requests.post(search_url, headers=headers, json=user_payload, timeout=15)
                result = resp.json()
                if result.get("code") == 0:
                    items = result.get("data", {}).get("items", [])
                    if items:
                        return items[0].get("record_id")
            except Exception:
                pass

    return None


def write_to_bitable(original_name, video_link, status, ip_name="", user="", vertical_name="", cover_uncertain=False):
    """写入飞书多维表格（完整字段）

    幂等写入：已存在则自动更新（而非静默跳过），确保链接始终同步。
    """
    from datetime import datetime
    token = _get_tenant_token()
    if not token:
        print(f"[write_to_bitable] ❌ 无法获取 tenant token，跳过写表 [{original_name}]")
        return False

    # 构建通用字段（用于新增和更新）
    timestamp_ms = int(datetime.now().timestamp() * 1000)
    display_name = vertical_name if vertical_name else original_name
    fields = {
        "原命名": original_name,
        "Ipv6视频链接": {"link": video_link, "text": display_name},
        "状态": status,
        "序号日期": timestamp_ms,
        "IP名字": ip_name if ip_name else "其他",
        "用户": user if user else "D",
        "是否异常": "待确认" if cover_uncertain else "正常",
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 幂等查重：已存在则更新（而非静默跳过），避免文件名变化导致数据未同步
    existing_rid = _bitable_check_exists(original_name, token)
    if existing_rid:
        update_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records/{existing_rid}"
        try:
            resp = requests.put(update_url, headers=headers, json={"fields": fields}, timeout=15)
            result = resp.json()
            if result.get("code") == 0:
                print(f"[write_to_bitable] 🔄 更新已有记录 [{original_name}] record_id={existing_rid}")
                return True
            else:
                print(f"[write_to_bitable] ❌ 更新失败 [{original_name}] code={result.get('code')} msg={result.get('msg','')}")
                return False
        except Exception as e:
            print(f"[write_to_bitable] ❌ 更新异常 [{original_name}]: {e}")
            return False

    # 新增记录
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records"
    try:
        resp = requests.post(url, headers=headers, json={"fields": fields}, timeout=15)
        result = resp.json()
        if resp.status_code in (200, 201) and result.get("code") == 0:
            print(f"[write_to_bitable] ✅ 新增成功 [{original_name}]")
            return True
        else:
            print(f"[write_to_bitable] ❌ 写表失败 [{original_name}] HTTP={resp.status_code} code={result.get('code')} msg={result.get('msg','')}")
            return False
    except Exception as e:
        print(f"[write_to_bitable] ❌ 写表异常 [{original_name}]: {e}")
        return False

def _validate_video_file(path, min_size_kb=50):
    """校验视频文件有效性：大小 + ffprobe 时长"""
    if not os.path.exists(path):
        return False, f"文件不存在: {path}"
    size_kb = os.path.getsize(path) // 1024
    if size_kb < min_size_kb:
        return False, f"文件过小: {size_kb}KB < {min_size_kb}KB"
    # ffprobe 校验时长
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0:
            dur = float(r.stdout.strip())
            if dur < 0.5:
                return False, f"视频时长异常: {dur}s"
            return True, f"OK ({size_kb}KB, {dur:.1f}s)"
    except:
        pass
    return True, f"OK ({size_kb}KB)"


def _retry_write_to_bitable(original_name, video_link, status, ip_name, user, vertical_name, cover_uncertain=False, max_retries=2):
    """写表功能已禁用（2026-05-08），始终返回成功"""
    print(f"[write_to_bitable] ⏭️ 写表已禁用，跳过 [{original_name}]")
    return True

def _pipeline_success(video_name, parsed, download_path, final_path, status, cover=None, cover_uncertain=False, reused=False):
    final_name = Path(final_path).name
    ipv6_link = build_ipv6_link(parsed, final_name)

    ip_names = {
        "naruto": "火影忍者", "jujutsu": "咒术回战",
        "kimetsu": "鬼灭之刃"
    }
    ip_name = "其他"
    if cover:
        for folder, name in ip_names.items():
            if folder in str(cover):
                ip_name = name
                break

    user_code_to_user = {
        "HR": "HR", "JR": "JR", "M": "M", "TM": "TM",
        "ZL": "ZL", "D": "D", "LJJ": "LJJ", "ZX": "ZX",
        "WY": "WY", "RY": "RY", "YB": "YB"
    }
    user = user_code_to_user.get(parsed["user_code"], parsed["user_code"])
    _retry_write_to_bitable(video_name, ipv6_link, status, ip_name, user, final_name, cover_uncertain=cover_uncertain)

    result = {
        "success": True,
        "status": status,
        "downloaded": download_path,
        "vertical": str(final_path),
        "link": ipv6_link
    }
    if cover:
        result["cover"] = str(cover)
    if reused:
        result["reused_existing"] = True
    return result

def _remember_success(state, video_name, result, cover_uncertain=False):
    state["records"][video_name] = {
        "status": result.get("status", "改竖"),
        "downloaded": result.get("downloaded"),
        "vertical": result.get("vertical"),
        "link": result.get("link"),
        "cover": result.get("cover", ""),
        "cover_uncertain": bool(cover_uncertain),
        "updated_at": datetime.now().isoformat(timespec="seconds")
    }

def full_pipeline(video_name):
    parsed = parse_filename(video_name)
    if not parsed:
        return {"success": False, "error": f"文件名格式错误: {video_name}"}

    with PipelineLock(parsed["date"], parsed["user_code"]):
        state = _load_state(parsed["date"], parsed["user_code"])
        record = state["records"].get(video_name, {})
        if record.get("vertical") and _is_valid_completed_output(record["vertical"]):
            return _pipeline_success(
                video_name, parsed, record.get("downloaded", ""), record["vertical"],
                record.get("status", "改竖"), cover=record.get("cover") or None,
                cover_uncertain=record.get("cover_uncertain", False), reused=True
            )

        success, msg, download_path = download_single(video_name)
        if not success:
            return {"success": False, "error": f"下载失败: {msg}"}

        ok, msg2 = _validate_video_file(download_path)
        if not ok:
            return {"success": False, "error": f"下载文件异常: {msg2}"}

        existing_vertical = _find_existing_vertical(video_name, parsed, source_path=download_path)
        if existing_vertical:
            result = _pipeline_success(
                video_name, parsed, download_path, existing_vertical,
                "改竖", cover=record.get("cover") or None, reused=True
            )
            _remember_success(state, video_name, result)
            _save_state(parsed["date"], parsed["user_code"], state)
            return result

        if is_vertical_video(download_path):
            result = _pipeline_success(video_name, parsed, download_path, download_path, "竖版原视频")
            _remember_success(state, video_name, result)
            _save_state(parsed["date"], parsed["user_code"], state)
            return result

        cover, cover_uncertain = find_cover_image(video_name, video_path=download_path) or (None, False)
        success, output_path = process_vertical(download_path, cover)
        if not success:
            return {"success": False, "error": f"改竖失败: {output_path}"}

        ok_move, msg_move = _validate_video_file(output_path)
        if not ok_move:
            return {"success": False, "error": f"改竖成品异常: {msg_move}"}
        if not is_vertical_video(output_path):
            return {"success": False, "error": f"改竖成品尺寸异常: {get_video_dimensions(output_path)}"}

        next_seq = get_next_seq(parsed["date"], parsed["user_code"])
        save_dir = get_save_dir(parsed["date"], parsed["user_code"])
        while True:
            final_name = build_filename(parsed["date"], parsed["user_code"], next_seq, parsed["content"], parsed["suffix"])
            final_path = save_dir / final_name
            if not final_path.exists():
                break
            next_seq += 1
        shutil.move(output_path, final_path)

        ok_final, msg_final = _validate_video_file(str(final_path))
        if not ok_final:
            return {"success": False, "error": f"成品文件异常: {msg_final}"}
        if not is_vertical_video(str(final_path)):
            return {"success": False, "error": f"最终成品尺寸异常: {get_video_dimensions(str(final_path))}"}

        result = _pipeline_success(
            video_name, parsed, download_path, final_path, "改竖",
            cover=cover, cover_uncertain=cover_uncertain
        )
        _remember_success(state, video_name, result, cover_uncertain=cover_uncertain)
        _save_state(parsed["date"], parsed["user_code"], state)
        return result

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "用法: download.py '视频名' | --search '前缀' | --download-prefix '前缀' | --pipeline '视频名' | --batch-pipeline '前缀'"}))
        return

    arg1 = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    if arg1 == '--download-prefix':
        prefix = sys.argv[2] if len(sys.argv) > 2 else ''
        if not prefix:
            print(json.dumps({"error": "请提供前缀，如 --download-prefix 260421"}))
            return
        if dry_run:
            result = run_batch_pipeline(prefix, dry_run=True)
            result["mode"] = "download-prefix-dry-run"
            print(json.dumps(result, ensure_ascii=False))
            return
        results, err = search_videos(prefix)
        if err:
            print(json.dumps({"error": err}))
            return
        downloaded, skipped = [], []
        for v in results:
            name = v.get("name", "")
            if is_generated_vertical_name(name):
                skipped.append(name); continue
            success, message, path = download_single(name)
            if success:
                downloaded.append({"name": name, "path": str(path)})
        print(json.dumps({"success": True, "total": len(results), "downloaded": len(downloaded), "skipped_vertical": len(skipped), "downloaded_list": downloaded, "skipped_list": skipped}, ensure_ascii=False))

    elif arg1 == '--search':
        prefix = sys.argv[2] if len(sys.argv) > 2 else ''
        results, err = search_videos(prefix)
        print(json.dumps({"error": err} if err else {"success": True, "count": len(results), "results": results}, ensure_ascii=False))

    elif arg1 == '--pipeline':
        video_name = sys.argv[2] if len(sys.argv) > 2 else ''
        result = full_pipeline(video_name)
        print(json.dumps(result, ensure_ascii=False))

    elif arg1 == '--batch-pipeline':
        prefix = sys.argv[2] if len(sys.argv) > 2 else ''
        if not prefix:
            print(json.dumps({"error": "请提供前缀，如 --batch-pipeline 260421"}))
            return
        result = run_batch_pipeline(prefix, dry_run=dry_run)
        print(json.dumps(result, ensure_ascii=False))

    else:
        success, message, path = download_single(arg1)
        print(json.dumps({"success": success, "message": message, "path": path} if success else {"success": False, "error": message}, ensure_ascii=False))

if __name__ == "__main__":
    main()
