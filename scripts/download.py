#!/usr/bin/env python3
"""
后台视频下载→改竖 自动化（写表已禁用 v3.1）
移除多用户/复杂规则 - 保留核心三环节
"""
import json, sys, os, re, requests, subprocess, tempfile, shutil, time, random, uuid, difflib
from pathlib import Path
from urllib.parse import quote
from datetime import datetime, timedelta

try:
    from config import (
        SAVE_DIR,
        ASSETS_DIR,
        API_BASE,
        IPv6_ROOT,
        BITABLE_APP_TOKEN,
        BITABLE_TABLE_ID,
        FEISHU_ACCESS_TOKEN,
        FEISHU_APP_ID,
        FEISHU_APP_SECRET,
    )
except ImportError:
    SAVE_DIR = Path(os.getenv("BACKSTAGE_SAVE_DIR", "/Volumes/美术AI龙虾"))
    ASSETS_DIR = Path(os.getenv("BACKSTAGE_ASSETS_DIR", "/Volumes/美术AI龙虾/assets"))
    API_BASE = "http://adopenplatform.rongyao666.com/app/data/api/ApiGetJrttVideoByCategory.php"
    IPv6_ROOT = os.getenv("IPv6_ROOT", "http://[2408:8256:4c87:f19c::c42]:9092")
    BITABLE_APP_TOKEN = os.getenv("BACKSTAGE_BITABLE_APP_TOKEN") or os.getenv("BITABLE_APP_TOKEN", "")
    BITABLE_TABLE_ID = os.getenv("BACKSTAGE_BITABLE_TABLE_ID") or os.getenv("BITABLE_TABLE_ID", "")
    FEISHU_ACCESS_TOKEN = os.getenv("BACKSTAGE_FEISHU_ACCESS_TOKEN") or os.getenv("FEISHU_ACCESS_TOKEN", "")
    FEISHU_APP_ID = os.getenv("BACKSTAGE_FEISHU_APP_ID") or os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET = os.getenv("BACKSTAGE_FEISHU_APP_SECRET") or os.getenv("FEISHU_APP_SECRET", "")

HANDLER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "handler.py")
EXPECTED_VERTICAL_DIMS = (720, 1280)
STATE_FILENAME = ".backstage_pipeline_state.json"
LOCK_FILENAME = ".backstage_pipeline.lock"
IMAGE_EXTENSIONS = ("jpg", "png", "jpeg", "webp")
SAVE_DIR.mkdir(parents=True, exist_ok=True)

def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

DOWNLOAD_CHUNK_SIZE = _env_int("BACKSTAGE_DOWNLOAD_CHUNK_SIZE", 1024 * 1024)
DOWNLOAD_CONNECT_TIMEOUT_S = _env_int("BACKSTAGE_DOWNLOAD_CONNECT_TIMEOUT", 10)
DOWNLOAD_READ_TIMEOUT_S = _env_int("BACKSTAGE_DOWNLOAD_READ_TIMEOUT", 30)
DOWNLOAD_TOTAL_TIMEOUT_S = _env_int("BACKSTAGE_DOWNLOAD_TOTAL_TIMEOUT", 900)
DOWNLOAD_MIN_RATE_BPS = _env_int("BACKSTAGE_DOWNLOAD_MIN_RATE_BPS", 32 * 1024)
DOWNLOAD_MIN_RATE_AFTER_S = _env_int("BACKSTAGE_DOWNLOAD_MIN_RATE_AFTER", 120)
DOWNLOAD_PROGRESS_INTERVAL_S = _env_int("BACKSTAGE_DOWNLOAD_PROGRESS_INTERVAL", 20)
DOWNLOAD_PROGRESS_BYTES = _env_int("BACKSTAGE_DOWNLOAD_PROGRESS_BYTES", 10 * 1024 * 1024)
DOWNLOAD_RETRIES = _env_int("BACKSTAGE_DOWNLOAD_RETRIES", 2)
DOWNLOAD_PART_MAX_AGE_S = _env_int("BACKSTAGE_DOWNLOAD_PART_MAX_AGE", 3600)
MEDIA_USE_ENV_PROXY = os.getenv("BACKSTAGE_USE_PROXY", "0").lower() in ("1", "true", "yes")

def _log_event(event, **fields):
    payload = {"event": event, "ts": datetime.now().isoformat(timespec="seconds")}
    payload.update(fields)
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr, flush=True)

def _new_media_session():
    """Media/API requests bypass env proxy by default; local proxy made large files very slow."""
    session = requests.Session()
    session.trust_env = MEDIA_USE_ENV_PROXY
    return session

def _cleanup_stale_download_parts(local_path):
    cutoff = time.time() - DOWNLOAD_PART_MAX_AGE_S
    for part_path in local_path.parent.glob(f"{local_path.name}.*.part"):
        try:
            if part_path.stat().st_mtime >= cutoff:
                continue
            part_path.unlink()
            _log_event("download_stale_part_removed", path=str(part_path))
        except Exception as e:
            _log_event("download_stale_part_remove_failed", path=str(part_path), error=str(e))

def _reuse_existing_download(local_path, video_name):
    if not local_path.exists():
        return None
    ok, msg = _validate_video_file(str(local_path))
    if ok:
        _log_event(
            "download_reuse_existing",
            name=video_name,
            path=str(local_path),
            mb=round(local_path.stat().st_size / 1024 / 1024, 1),
        )
        return True, f"已存在({local_path.stat().st_size//1024//1024}MB)", str(local_path)
    _log_event(
        "download_invalid_existing_removed",
        name=video_name,
        path=str(local_path),
        reason=msg,
        bytes=local_path.stat().st_size,
    )
    try:
        local_path.unlink()
    except Exception as e:
        return False, f"已有文件异常且无法删除: {msg}; {e}", None
    return None

ROLE_PROFILES = [
    {"subdir": "naruto", "canonical": "宇智波鼬", "aliases": ["宇智波鼬", "鼬", "鼬神", "itachi", "Itachi"], "asset_keywords": ["宇智波鼬", "鼬"]},
    {"subdir": "naruto", "canonical": "宇智波斑", "aliases": ["宇智波斑", "斑", "madara", "Madara"], "asset_keywords": ["宇智波斑", "斑"]},
    {"subdir": "naruto", "canonical": "宇智波佐助", "aliases": ["宇智波佐助", "佐助", "sasuke", "Sasuke"], "asset_keywords": ["宇智波佐助", "佐助"]},
    {"subdir": "naruto", "canonical": "漩涡鸣人", "aliases": ["漩涡鸣人", "鸣人", "金鸣", "naruto", "Naruto"], "asset_keywords": ["漩涡鸣人", "鸣人", "金鸣"]},
    {"subdir": "naruto", "canonical": "波风水门", "aliases": ["波风水门", "水门", "四代", "四代火影"], "asset_keywords": ["波风水门", "水门"]},
    {"subdir": "naruto", "canonical": "纲手", "aliases": ["纲手"], "asset_keywords": ["纲手"]},
    {"subdir": "naruto", "canonical": "千手柱间", "aliases": ["千手柱间", "柱间", "初代", "初代火影"], "asset_keywords": ["千手柱间", "柱间"]},
    {"subdir": "naruto", "canonical": "自来也", "aliases": ["自来也"], "asset_keywords": ["自来也"]},
    {"subdir": "naruto", "canonical": "佩恩", "aliases": ["佩恩", "长门"], "asset_keywords": ["佩恩"]},
    {"subdir": "naruto", "canonical": "夜凯", "aliases": ["夜凯", "死门凯"], "asset_keywords": ["夜凯"]},
    {"subdir": "naruto", "canonical": "春野樱", "aliases": ["春野樱", "小樱", "樱"], "asset_keywords": ["春野樱", "小樱"]},
    {"subdir": "naruto", "canonical": "日向雏田", "aliases": ["日向雏田", "雏田"], "asset_keywords": ["日向雏田", "雏田"]},
    {"subdir": "naruto", "canonical": "旗木卡卡西", "aliases": ["旗木卡卡西", "卡卡西"], "asset_keywords": ["旗木卡卡西", "卡卡西"]},
    {"subdir": "naruto", "canonical": "迈特凯", "aliases": ["迈特凯", "凯"], "asset_keywords": ["迈特凯", "凯"]},
    {"subdir": "naruto", "canonical": "宇智波带土", "aliases": ["宇智波带土", "带土"], "asset_keywords": ["宇智波带土", "带土"]},
    {"subdir": "naruto", "canonical": "大蛇丸", "aliases": ["大蛇丸"], "asset_keywords": ["大蛇丸"]},
    {"subdir": "naruto", "canonical": "小南", "aliases": ["小南"], "asset_keywords": ["小南"]},
    {"subdir": "naruto", "canonical": "迪达拉", "aliases": ["迪达拉"], "asset_keywords": ["迪达拉"]},
    {"subdir": "naruto", "canonical": "飞段", "aliases": ["飞段"], "asset_keywords": ["飞段"]},
    {"subdir": "naruto", "canonical": "香燐", "aliases": ["香燐", "香磷"], "asset_keywords": ["香燐", "香磷"]},
    {"subdir": "naruto", "canonical": "天天", "aliases": ["天天"], "asset_keywords": ["天天"]},
    {"subdir": "naruto", "canonical": "玖辛奈", "aliases": ["玖辛奈"], "asset_keywords": ["玖辛奈"]},
    {"subdir": "jujutsu", "canonical": "五条悟", "aliases": ["五条悟", "五条"], "asset_keywords": ["五条悟", "五条"]},
    {"subdir": "jujutsu", "canonical": "宿傩", "aliases": ["宿傩", "两面宿傩"], "asset_keywords": ["宿傩"]},
    {"subdir": "jujutsu", "canonical": "虎杖悠仁", "aliases": ["虎杖悠仁", "虎杖"], "asset_keywords": ["虎杖悠仁", "虎杖"]},
    {"subdir": "jujutsu", "canonical": "伏黑甚尔", "aliases": ["伏黑甚尔", "甚尔"], "asset_keywords": ["伏黑甚尔", "甚尔"]},
    {"subdir": "jujutsu", "canonical": "伏黑惠", "aliases": ["伏黑惠"], "asset_keywords": ["伏黑惠"]},
    {"subdir": "jujutsu", "canonical": "乙骨忧太", "aliases": ["乙骨忧太", "乙骨"], "asset_keywords": ["乙骨忧太", "乙骨"]},
    {"subdir": "jujutsu", "canonical": "真人", "aliases": ["真人"], "asset_keywords": ["真人"]},
    {"subdir": "jujutsu", "canonical": "东堂葵", "aliases": ["东堂葵", "东堂"], "asset_keywords": ["东堂葵", "东堂"]},
    {"subdir": "jujutsu", "canonical": "夏油杰", "aliases": ["夏油杰", "夏油"], "asset_keywords": ["夏油杰", "夏油"]},
    {"subdir": "jujutsu", "canonical": "七海建人", "aliases": ["七海建人", "七海"], "asset_keywords": ["七海建人", "七海"]},
    {"subdir": "jujutsu", "canonical": "禅院真希", "aliases": ["禅院真希", "真希", "禅院"], "asset_keywords": ["禅院真希", "真希", "禅院"]},
    {"subdir": "jujutsu", "canonical": "冥冥", "aliases": ["冥冥"], "asset_keywords": ["冥冥"]},
    {"subdir": "jujutsu", "canonical": "秤金次", "aliases": ["秤金次", "秤"], "asset_keywords": ["秤金次", "秤"]},
    {"subdir": "jujutsu", "canonical": "胀相", "aliases": ["胀相"], "asset_keywords": ["胀相"]},
    {"subdir": "kimetsu", "canonical": "灶门炭治郎", "aliases": ["灶门炭治郎", "炭治郎"], "asset_keywords": ["灶门炭治郎", "炭治郎"]},
    {"subdir": "kimetsu", "canonical": "灶门祢豆子", "aliases": ["灶门祢豆子", "祢豆子"], "asset_keywords": ["灶门祢豆子", "祢豆子"]},
    {"subdir": "kimetsu", "canonical": "我妻善逸", "aliases": ["我妻善逸", "善逸"], "asset_keywords": ["我妻善逸", "善逸"]},
    {"subdir": "kimetsu", "canonical": "蝴蝶忍", "aliases": ["蝴蝶忍", "蝴蝶"], "asset_keywords": ["蝴蝶忍", "蝴蝶"]},
    {"subdir": "kimetsu", "canonical": "甘露寺蜜璃", "aliases": ["甘露寺蜜璃", "甘露寺", "蜜璃"], "asset_keywords": ["甘露寺蜜璃", "甘露寺", "蜜璃"]},
    {"subdir": "kimetsu", "canonical": "富冈义勇", "aliases": ["富冈义勇", "富冈", "义勇"], "asset_keywords": ["富冈义勇", "义勇"]},
    {"subdir": "kimetsu", "canonical": "炼狱杏寿郎", "aliases": ["炼狱杏寿郎", "炼狱", "杏寿郎"], "asset_keywords": ["炼狱杏寿郎", "炼狱", "杏寿郎"]},
    {"subdir": "kimetsu", "canonical": "时透无一郎", "aliases": ["时透无一郎", "无一郎"], "asset_keywords": ["无一郎", "时透无一郎"]},
    {"subdir": "kimetsu", "canonical": "猗窝座", "aliases": ["猗窝座"], "asset_keywords": ["猗窝座"]},
    {"subdir": "kimetsu", "canonical": "岩柱", "aliases": ["岩柱", "悲鸣", "行冥"], "asset_keywords": ["岩柱", "悲鸣", "行冥"]},
    {"subdir": "kimetsu", "canonical": "黑死牟", "aliases": ["黑死牟"], "asset_keywords": ["黑死牟"]},
    {"subdir": "kimetsu", "canonical": "继国缘一", "aliases": ["继国缘一", "缘一"], "asset_keywords": ["继国缘一", "缘一"]},
]

ROLE_MISREADS = {
    "鼫": "宇智波鼬",
    "鼬人": "宇智波鼬",
    "鹤人": "漩涡鸣人",
    "鶴人": "漩涡鸣人",
    "呜人": "漩涡鸣人",
    "嗚人": "漩涡鸣人",
    "鸣入": "漩涡鸣人",
    "鳴人": "漩涡鸣人",
    "名人": "漩涡鸣人",
}

FAMILY_HINTS = {
    "naruto": ["火影", "忍者", "晓组织", "九尾", "查克拉", "佐助", "鸣人", "鼬", "小樱", "雏田", "洗髓"],
    "jujutsu": ["咒术", "咒回", "领域", "五条", "宿傩", "虎杖", "伏黑", "乙骨"],
    "kimetsu": ["鬼灭", "呼吸", "炭治郎", "祢豆子", "善逸", "蝴蝶", "炼狱", "无一郎"],
}

FAMILY_DEFAULTS = {
    "naruto": ["宇智波鼬", "漩涡鸣人", "宇智波佐助", "春野樱", "日向雏田"],
    "jujutsu": ["五条悟", "宿傩", "虎杖悠仁", "伏黑甚尔", "乙骨忧太"],
    "kimetsu": ["灶门炭治郎", "灶门祢豆子", "我妻善逸", "蝴蝶忍", "炼狱杏寿郎", "时透无一郎"],
}

NON_ROLE_PHRASES = {
    "真人": ["引流真人", "真人跳", "真人试玩", "真人实拍", "真人拍摄", "真人素材"],
}

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
    """Per-user/date lock to prevent duplicate vertical outputs and sequence races.

    实现要点：
    - 用 fcntl.flock(LOCK_EX|LOCK_NB) + 短轮询 30s 拿锁
    - 拿锁时写入持锁 PID + 时间戳，超时可诊断是哪个进程卡死
    - 用 os.open(O_RDWR) 而非 open("a")，避免 macOS 上 TextIOWrapper 包装的 flock 行为差异
    - 注意：macOS flock 在跨线程场景 advisory 行为不可靠，生产 use case
      （launchd noon/evening、OpenClaw cron）都是跨进程调起，本类足够。
    """
    DEFAULT_TIMEOUT_S = 30
    POLL_INTERVAL_S = 0.5

    def __init__(self, date_str, user_code, timeout=DEFAULT_TIMEOUT_S):
        self.path = get_save_dir(date_str, user_code) / LOCK_FILENAME
        self.timeout = timeout
        self.fd = None
        self.acquired = False

    def __enter__(self):
        import fcntl, os, time
        # 确保 lock 文件存在
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self.fd = os.open(str(self.path), os.O_RDWR)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.acquired = True
                # 记录持锁 PID + 时间戳，便于超时诊断
                try:
                    os.ftruncate(self.fd, 0)
                    os.lseek(self.fd, 0, 0)
                    os.write(self.fd, f"pid={os.getpid()} at={int(time.time())}\n".encode())
                except Exception:
                    pass
                return self
            except (BlockingIOError, OSError) as e:
                if time.monotonic() >= deadline:
                    holder = self._read_holder()
                    raise TimeoutError(
                        f"PipelineLock 超时 ({self.timeout}s): {self.path} "
                        f"仍被持有 (last holder: {holder})"
                    ) from e
                time.sleep(self.POLL_INTERVAL_S)

    def _read_holder(self):
        try:
            with open(self.path, "r") as f:
                return f.read().strip()
        except Exception:
            return "unknown"

    def __exit__(self, exc_type, exc, tb):
        import fcntl
        if self.fd is not None:
            try:
                if self.acquired:
                    fcntl.flock(self.fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(self.fd)
            except Exception:
                pass
            self.fd = None
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

def _extract_seq_from_name(name, date, user_code):
    fname = Path(name).name
    m = re.match(rf'^{re.escape(date)}{re.escape(user_code)}(\d+)-', fname)
    return int(m.group(1)) if m else None

def get_next_seq(date, user_code, source_seq=None, min_seq=1):
    """扫描日期目录，找到相同用户代码的最大序号，返回下一个可用成品序号。

    参数:
        date: 26MMDD
        user_code: 用户代码
        source_seq: 旧参数，保留兼容但不再采用；改竖成品必须顺延，不能与原始素材同号
        min_seq: 本批次成品允许使用的最小序号，例如原始 BY1/BY2 时传 3
    """
    if source_seq is not None:
        _log_event("sequence_source_seq_ignored", date=date, user_code=user_code, source_seq=source_seq)
    max_seq = 0
    save_dir = get_save_dir(date, user_code)
    if not save_dir.exists():
        return max(1, int(min_seq or 1))
    for fname in os.listdir(save_dir):
        if not fname.lower().endswith('.mp4'):
            continue
        if 'vertical_' in fname:
            continue
        seq = _extract_seq_from_name(fname, date, user_code)
        if seq is not None:
            max_seq = max(max_seq, seq)
    return max(max_seq + 1, int(min_seq or 1))

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

def _iter_role_profiles(subdir=None):
    for profile in ROLE_PROFILES:
        if subdir and profile["subdir"] != subdir:
            continue
        yield profile

def _profile_by_canonical(canonical):
    for profile in ROLE_PROFILES:
        if profile["canonical"] == canonical:
            return profile
    return None

def _role_prompt_candidates():
    grouped = {}
    for profile in ROLE_PROFILES:
        grouped.setdefault(profile["subdir"], []).append(profile["canonical"])
    labels = {
        "naruto": "火影忍者",
        "jujutsu": "咒术回战",
        "kimetsu": "鬼灭之刃",
    }
    parts = []
    for key in ["naruto", "jujutsu", "kimetsu"]:
        values = " / ".join(dict.fromkeys(grouped.get(key, [])))
        parts.append(f"{labels[key]}（{values}）")
    return "，".join(parts)

def _normalize_role_text(text):
    if not text:
        return ""
    text = str(text).strip()
    text = re.sub(r'[\s"\'“”‘’《》【】\[\]{}（）(),，。:：;；|/\\]+', '', text)
    return text

def _infer_family_hint(*texts):
    joined = " ".join(t for t in texts if t)
    scores = {}
    for family, hints in FAMILY_HINTS.items():
        score = sum(1 for hint in hints if hint in joined)
        if score:
            scores[family] = score
    if not scores:
        return None
    return max(scores.items(), key=lambda item: item[1])[0]

def _find_role_asset(profile):
    if not profile:
        return None
    subdir = profile["subdir"]
    base = Path(ASSETS_DIR) / subdir
    keywords = profile.get("asset_keywords") or [profile["canonical"]]
    for keyword in keywords:
        candidates = []
        for ext in IMAGE_EXTENSIONS:
            if base.exists():
                candidates.extend(base.glob(f"*{keyword}*.{ext}"))
        if candidates:
            return str(random.choice(candidates))
    for keyword in keywords:
        candidates = []
        for ext in IMAGE_EXTENSIONS:
            candidates.extend(Path(ASSETS_DIR).rglob(f"*{keyword}*.{ext}"))
        if candidates:
            return str(random.choice(candidates))
    return None

def _match_role_from_text(text, preferred_family=None, allow_fuzzy=False):
    normalized = _normalize_role_text(text)
    if not normalized:
        return None

    candidates = []
    for profile in ROLE_PROFILES:
        if preferred_family and profile["subdir"] != preferred_family:
            continue
        for alias in profile["aliases"]:
            alias_norm = _normalize_role_text(alias)
            if not alias_norm:
                continue
            if alias_norm in NON_ROLE_PHRASES:
                phrase_hit = any(_normalize_role_text(phrase) in normalized for phrase in NON_ROLE_PHRASES[alias_norm])
                if phrase_hit:
                    continue
            idx = normalized.find(alias_norm)
            if idx >= 0:
                candidates.append((idx, -len(alias_norm), profile))

    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][2]

    for wrong, canonical in ROLE_MISREADS.items():
        if wrong in normalized:
            profile = _profile_by_canonical(canonical)
            if profile and (not preferred_family or profile["subdir"] == preferred_family):
                return profile

    if not allow_fuzzy:
        return None

    choices = []
    for profile in ROLE_PROFILES:
        if preferred_family and profile["subdir"] != preferred_family:
            continue
        for alias in profile["aliases"]:
            alias_norm = _normalize_role_text(alias)
            if len(alias_norm) >= 2:
                choices.append((alias_norm, profile))
    best = None
    for alias, profile in choices:
        ratio = difflib.SequenceMatcher(None, normalized, alias).ratio()
        # 只接受非常接近的短词纠错，避免把未知角色硬贴到错误 IP。
        threshold = 0.67 if max(len(normalized), len(alias)) <= 3 else 0.78
        if ratio >= threshold and (best is None or ratio > best[0]):
            best = (ratio, profile)
    return best[1] if best else None

def _select_role_asset_from_text(text, preferred_family=None, allow_fuzzy=False):
    profile = _match_role_from_text(text, preferred_family=preferred_family, allow_fuzzy=allow_fuzzy)
    path = _find_role_asset(profile)
    if path:
        return path, profile
    return None, profile

def _select_family_default_asset(family):
    for canonical in FAMILY_DEFAULTS.get(family, []):
        profile = _profile_by_canonical(canonical)
        path = _find_role_asset(profile)
        if path:
            return path, profile
    return None, None

def _correct_role_with_llm(raw_text, filename="", preferred_family=None):
    """Use a local language model as a conservative role normalizer when available."""
    raw = _normalize_role_text(raw_text)
    if not raw:
        return None

    local_match = _match_role_from_text(raw, preferred_family=preferred_family, allow_fuzzy=True)
    if local_match:
        return local_match["canonical"]

    try:
        candidates = [
            p["canonical"] for p in _iter_role_profiles(preferred_family)
            if _find_role_asset(p)
        ]
        if not candidates:
            return None
        prompt = (
            "你是动漫角色名纠错器。只从候选列表中选择最可能的一个角色名，"
            "不要解释；如果完全无法判断，只返回未知。\n"
            f"视频文件名：{filename or '未知'}\n"
            f"AI原始识别：{raw_text}\n"
            f"候选：{'、'.join(candidates)}\n"
            "特别注意：鼫通常是宇智波鼬的误识别，鹤人/呜人通常是漩涡鸣人的误识别。"
        )
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "qwen2.5:7b", "prompt": prompt, "stream": False},
            timeout=20
        )
        if resp.status_code == 200:
            text = (resp.json().get("response") or "").strip()
            profile = _match_role_from_text(text, preferred_family=preferred_family, allow_fuzzy=True)
            if profile:
                return profile["canonical"]
    except Exception as e:
        print(json.dumps({"warning": f"角色名纠错 LLM 不可用: {e}"}), file=sys.stderr)
    return None

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
        f"候选：{_role_prompt_candidates()}。"
        "如果看到相近但不确定的短词，优先纠正常见角色名，例如鼫=宇智波鼬、鹤人/呜人=漩涡鸣人。"
        "找不到时只返回'未知'。"
    )

    def _extract(content):
        cleaned = _normalize_role_text(content)
        if not cleaned or cleaned in ("未知", "无法识别", "无", "不知道"):
            return None
        profile = _match_role_from_text(cleaned, allow_fuzzy=True)
        if profile:
            return profile["canonical"]
        # 保留原始短词，后续交给语言模型纠错，不要在 Vision 阶段直接丢弃。
        return cleaned[:80]

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
            if role:
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
    贴图匹配：
    1. 文件名角色关键词（按最早出现位置，不按字典顺序）
    2. Vision API 识别 → 错词表/模糊匹配/本地 LLM 纠错
    3. IP 家族默认角色贴图（仍优先专属贴图，避免通用 fallback）
    4. 最后才使用 fallback 通用贴图并标记待确认

    Returns:
        tuple: (贴图路径, 是否为兜底) — 有结果时
        None: 完全无法匹配
    """
    preferred_family = _infer_family_hint(filename)

    result, profile = _select_role_asset_from_text(filename, preferred_family=preferred_family, allow_fuzzy=False)
    if result:
        print(json.dumps({
            "info": f"文件名匹配贴图: {profile['canonical']}",
            "cover": result
        }, ensure_ascii=False), file=sys.stderr)
        return result, False

    print(json.dumps({"info": f"文件名未匹配 '{filename}'，启动 AI 角色识别..."}), file=sys.stderr)
    frame_path = _extract_key_frame(video_path) if video_path else None
    if frame_path:
        ai_result = _call_vision_api_v2(frame_path)
        if ai_result:
            print(json.dumps({"info": f"AI 识别结果: {ai_result}"}), file=sys.stderr)
            family = preferred_family or _infer_family_hint(filename, ai_result)
            result, profile = _select_role_asset_from_text(ai_result, preferred_family=family, allow_fuzzy=True)
            if result:
                print(json.dumps({
                    "info": f"AI 结果已匹配贴图: {profile['canonical']}",
                    "cover": result
                }, ensure_ascii=False), file=sys.stderr)
                return result, False

            corrected = _correct_role_with_llm(ai_result, filename=filename, preferred_family=family)
            if corrected:
                profile = _profile_by_canonical(corrected)
                result = _find_role_asset(profile)
                if result:
                    print(json.dumps({
                        "info": f"AI 结果已纠错为: {corrected}",
                        "raw": ai_result,
                        "cover": result
                    }, ensure_ascii=False), file=sys.stderr)
                    return result, False
        try:
            os.remove(frame_path)
        except:
            pass

    # 如果能判断 IP 家族，但具体角色没识别出来，优先使用该 IP 的高覆盖角色贴图。
    if preferred_family:
        result, profile = _select_family_default_asset(preferred_family)
        if result:
            print(json.dumps({
                "warning": f"未识别具体角色，使用 {preferred_family} 专属默认贴图: {profile['canonical']}",
                "cover": result
            }, ensure_ascii=False), file=sys.stderr)
            return result, True

    # 最后才兜底：专用 fallback 目录通用贴图
    fallback_dir = Path(ASSETS_DIR) / "fallback"
    if fallback_dir.exists():
        imgs = []
        for ext in IMAGE_EXTENSIONS:
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

def _is_sequence_valid_for_product(path, parsed, min_output_seq=1):
    seq = _extract_seq_from_name(Path(path).name, parsed["date"], parsed["user_code"])
    return seq is not None and seq >= int(min_output_seq or 1)

def _record_has_reusable_vertical(record, parsed, min_output_seq=1):
    vertical = record.get("vertical")
    if not _is_valid_completed_output(vertical):
        return False
    if record.get("status") == "竖版原视频":
        return True
    return _is_sequence_valid_for_product(vertical, parsed, min_output_seq=min_output_seq)

def _find_existing_vertical(video_name, parsed, source_path=None, min_output_seq=1):
    """查找同一 source 已生成的合规改竖成品。

    选接策略：seq 跟 video_name 序号最接近的（处理旧版序号错位遗留的多个 match）。
    """
    save_dir = get_save_dir(parsed["date"], parsed["user_code"])
    prefix = f"{parsed['date']}{parsed['user_code']}"
    suffix_part = f"-{parsed['suffix']}" if parsed["suffix"] else ""
    suffix = f"-龙虾改竖{parsed['content']}{suffix_part}.mp4"
    target_seq = parsed["seq"]
    matches = []
    for path in save_dir.glob(f"{prefix}*-龙虾改竖*.mp4"):
        if path.name.endswith(suffix) and _is_valid_completed_output(path):
            if not _is_sequence_valid_for_product(path, parsed, min_output_seq=min_output_seq):
                _log_event(
                    "pipeline_ignore_existing_low_seq",
                    name=video_name,
                    vertical=str(path),
                    min_output_seq=min_output_seq,
                )
                continue
            if source_path and path.stat().st_mtime < Path(source_path).stat().st_mtime:
                continue
            seq_match = re.match(rf'^{parsed["date"]}{parsed["user_code"]}(\d+)-', path.name)
            seq = int(seq_match.group(1)) if seq_match else 0
            matches.append((seq, path))
    if not matches:
        return None
    # 选 seq 最接近 target_seq 的（处理旧版序号错位遗留）
    matches.sort(key=lambda x: (abs(x[0] - target_seq), x[0]))
    return str(matches[0][1])

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
        resp = _new_media_session().get(url, timeout=(DOWNLOAD_CONNECT_TIMEOUT_S, DOWNLOAD_READ_TIMEOUT_S))
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

def _normalize_user_filter(user_filter):
    if not user_filter:
        return None
    value = str(user_filter).strip().upper()
    return value or None

def _filter_names_by_user(names, user_filter):
    user_filter = _normalize_user_filter(user_filter)
    if not user_filter:
        return list(names)
    filtered = []
    for name in names:
        parsed = parse_filename(name)
        if parsed and parsed["user_code"].upper() == user_filter:
            filtered.append(name)
    return filtered

def _result_matches_user(item, user_filter):
    user_filter = _normalize_user_filter(user_filter)
    if not user_filter:
        return True
    parsed = parse_filename(item.get("name", ""))
    return bool(parsed and parsed["user_code"].upper() == user_filter)

def _parse_option_value(flag):
    if flag not in sys.argv:
        return None
    idx = sys.argv.index(flag)
    if idx + 1 >= len(sys.argv):
        return None
    value = sys.argv[idx + 1]
    if value.startswith("--"):
        return None
    return value

def _chief_all_users_authorized():
    return os.environ.get("OPENCLAW_CHIEF_INSTANCE") == "18789"

def _all_users_requested():
    return "--all-users" in sys.argv or "--confirm-all-users" in sys.argv

def _validate_user_scope(command_name, user_filter):
    user_filter = _normalize_user_filter(user_filter)
    if user_filter:
        return True, None
    if "--all-users" in sys.argv and "--confirm-all-users" in sys.argv and _chief_all_users_authorized():
        return True, None
    if _all_users_requested() and not _chief_all_users_authorized():
        return False, f"{command_name} 全员模式只允许 18789 主实例授权环境执行"
    return False, f"{command_name} 必须提供 --user USER；全员模式需 18789 主实例环境 + --all-users --confirm-all-users"

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

def _build_batch_seq_floors(names):
    """For each date/user batch, products should start after the highest source seq."""
    floors = {}
    for name in names:
        parsed = parse_filename(name)
        if not parsed:
            continue
        key = (parsed["date"], parsed["user_code"])
        floors[key] = max(floors.get(key, 0), parsed["seq"] + 1)
    return floors

def _infer_min_output_seq_for_source(video_name, parsed):
    """Infer output sequence floor for single --pipeline runs.

    Batch mode passes this explicitly. Manual single runs still need to know that
    BY1/BY2 source material means products must start from BY3.
    """
    floor = parsed["seq"] + 1
    prefix = f"{parsed['date']}{parsed['user_code']}"

    try:
        results, err = search_videos(prefix)
        if not err:
            names = []
            for name in _eligible_source_names(results):
                other = parse_filename(name)
                if other and other["date"] == parsed["date"] and other["user_code"] == parsed["user_code"]:
                    names.append(name)
            api_floor = _build_batch_seq_floors(names).get((parsed["date"], parsed["user_code"]))
            if api_floor:
                floor = max(floor, api_floor)
    except Exception as e:
        _log_event("sequence_floor_api_infer_failed", name=video_name, error=str(e))

    try:
        save_dir = get_save_dir(parsed["date"], parsed["user_code"])
        for path in save_dir.glob(f"{prefix}*.mp4"):
            if is_generated_vertical_name(path.name):
                continue
            other = parse_filename(path.name)
            if other and other["date"] == parsed["date"] and other["user_code"] == parsed["user_code"]:
                floor = max(floor, other["seq"] + 1)
    except Exception as e:
        _log_event("sequence_floor_local_infer_failed", name=video_name, error=str(e))

    return max(1, floor)

def run_batch_pipeline(prefix, dry_run=False, user_filter=None):
    batch_start = time.monotonic()
    user_filter = _normalize_user_filter(user_filter)
    _log_event("batch_start", prefix=prefix, dry_run=dry_run, user_filter=user_filter)
    results, err = search_videos(prefix)
    if err:
        _log_event("batch_failed", prefix=prefix, stage="search", error=err)
        return {"success": False, "error": err}

    all_names = _eligible_source_names(results)
    names = _filter_names_by_user(all_names, user_filter)
    skipped = [
        v.get("name", "") for v in results
        if _result_matches_user(v, user_filter) and is_generated_vertical_name(v.get("name", ""))
    ]
    missing = _missing_sequences(names)
    seq_floors = _build_batch_seq_floors(names)
    if dry_run:
        return {
            "success": True,
            "prefix": prefix,
            "user_filter": user_filter,
            "total": len(results),
            "eligible_all_users": len(all_names),
            "eligible": len(names),
            "skipped_vertical": len(skipped),
            "missing_sequences": missing,
            "seq_floors": {f"{date}{user}": floor for (date, user), floor in sorted(seq_floors.items())},
            "todo": names
        }

    ok, fail = [], []
    total = len(names)
    for index, name in enumerate(names, start=1):
        item_start = time.monotonic()
        _log_event("batch_item_start", prefix=prefix, user_filter=user_filter, index=index, total=total, name=name)
        parsed = parse_filename(name)
        min_output_seq = seq_floors.get((parsed["date"], parsed["user_code"]), 1) if parsed else 1
        result = full_pipeline(name, min_output_seq=min_output_seq)
        if result.get("success"):
            ok.append({"name": name, "vertical": result.get("vertical"), "reused": result.get("reused_existing", False)})
            _log_event(
                "batch_item_done",
                prefix=prefix,
                user_filter=user_filter,
                index=index,
                total=total,
                name=name,
                reused=bool(result.get("reused_existing", False)),
                seconds=round(time.monotonic() - item_start, 1),
            )
        else:
            fail.append({"name": name, "error": result.get("error", "unknown")})
            _log_event(
                "batch_item_failed",
                prefix=prefix,
                user_filter=user_filter,
                index=index,
                total=total,
                name=name,
                error=result.get("error", "unknown"),
                seconds=round(time.monotonic() - item_start, 1),
            )
    _log_event(
        "batch_done",
        prefix=prefix,
        user_filter=user_filter,
        processed=len(ok),
        failed=len(fail),
        missing=len(missing),
        seconds=round(time.monotonic() - batch_start, 1),
    )

    return {
        "success": len(fail) == 0 and len(missing) == 0,
        "prefix": prefix,
        "user_filter": user_filter,
        "total": len(results),
        "eligible_all_users": len(all_names),
        "eligible": len(names),
        "processed": len(ok),
        "failed": len(fail),
        "skipped_vertical": len(skipped),
        "missing_sequences": missing,
        "processed_list": ok,
        "failed_list": fail,
        "skipped_list": skipped
    }

def _parse_anchor_date(value):
    if not value:
        return datetime.now()
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%y%m%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析日期: {value}")

def _week_dates(anchor=None):
    anchor = _parse_anchor_date(anchor or os.getenv("BACKSTAGE_WEEK_ANCHOR_DATE"))
    start = anchor - timedelta(days=anchor.weekday())
    days = (anchor.date() - start.date()).days + 1
    return [start + timedelta(days=i) for i in range(days)]

def _date_prefixes_for_search(day):
    return [day.strftime("%y%m%d"), day.strftime("%Y%m%d")]

def _dedupe_names(names):
    deduped = []
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped

def _iter_week_local_dirs(dates, user_filter=None):
    user_filter = _normalize_user_filter(user_filter)
    if user_filter:
        roots = [(user_filter, SAVE_DIR / user_filter / "后台下载")]
    else:
        roots = []
        try:
            for user_dir in sorted(SAVE_DIR.iterdir()):
                backstage_dir = user_dir / "后台下载"
                if user_dir.is_dir() and backstage_dir.exists():
                    roots.append((user_dir.name, backstage_dir))
        except Exception:
            roots = []

    for user_code, backstage_dir in roots:
        for day in dates:
            yield user_code, day, backstage_dir / day.strftime("%Y-%m-%d")

def _local_week_source_scan(dates, user_filter=None):
    """Find local week source videos that may no longer appear in backstage search."""
    user_filter = _normalize_user_filter(user_filter)
    week_date_codes = {day.strftime("%y%m%d") for day in dates}
    names = []
    vertical_originals = []
    errors = []

    for _user_code, _day, folder in _iter_week_local_dirs(dates, user_filter=user_filter):
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.mp4")):
            if "vertical_" in path.name:
                continue
            name = path.stem
            parsed = parse_filename(name)
            if not parsed:
                errors.append({"path": str(path), "error": "unparseable_filename"})
                continue
            if parsed["date"] not in week_date_codes:
                continue
            if user_filter and parsed["user_code"].upper() != user_filter:
                continue
            if is_generated_vertical_name(path.name):
                continue

            ok, msg = _validate_video_file(str(path))
            if not ok:
                errors.append({"name": name, "path": str(path), "error": msg})
                continue
            if is_vertical_video(str(path)):
                vertical_originals.append(name)
                continue
            names.append(name)

    return {
        "names": _dedupe_names(names),
        "vertical_originals": _dedupe_names(vertical_originals),
        "errors": errors,
    }

def run_week_pipeline(dry_run=False, user_filter=None):
    """Run this calendar week's backstage pipeline without relying on an LLM to guess dates."""
    batch_start = time.monotonic()
    user_filter = _normalize_user_filter(user_filter)
    dates = _week_dates()
    week_start = dates[0].strftime("%Y-%m-%d")
    week_end = dates[-1].strftime("%Y-%m-%d")
    week_date_codes = {day.strftime("%y%m%d") for day in dates}
    searched_prefixes = []
    search_errors = []
    by_name = {}

    _log_event(
        "week_start",
        dry_run=dry_run,
        user_filter=user_filter,
        week_start=week_start,
        week_end=week_end,
    )

    for day in dates:
        for prefix in _date_prefixes_for_search(day):
            results, err = search_videos(prefix)
            count = len(results) if results else 0
            searched_prefixes.append({"prefix": prefix, "count": count, "error": err})
            if err:
                search_errors.append({"prefix": prefix, "error": err})
                continue
            for item in results or []:
                name = item.get("name", "")
                parsed = parse_filename(name)
                if parsed and parsed["date"] in week_date_codes:
                    by_name[name] = item

    all_results = list(by_name.values())
    all_names = _eligible_source_names(all_results)
    api_names = _filter_names_by_user(all_names, user_filter)
    local_scan = _local_week_source_scan(dates, user_filter=user_filter)
    local_names = local_scan["names"]
    api_name_set = set(api_names)
    local_only_names = [name for name in local_names if name not in api_name_set]
    names = _dedupe_names(api_names + local_only_names)
    skipped = [
        v.get("name", "") for v in all_results
        if _result_matches_user(v, user_filter) and is_generated_vertical_name(v.get("name", ""))
    ]
    missing = _missing_sequences(names)
    seq_floors = _build_batch_seq_floors(names)
    _log_event(
        "week_local_scan",
        user_filter=user_filter,
        local_sources=len(local_names),
        local_only=len(local_only_names),
        vertical_originals=len(local_scan["vertical_originals"]),
        errors=len(local_scan["errors"]),
    )

    if dry_run:
        return {
            "success": len(search_errors) == 0 and len(local_scan["errors"]) == 0,
            "mode": "week-pipeline-dry-run",
            "week_start": week_start,
            "week_end": week_end,
            "user_filter": user_filter,
            "searched_prefixes": searched_prefixes,
            "search_errors": search_errors,
            "eligible_all_users": len(all_names),
            "eligible": len(names),
            "eligible_from_api": len(api_names),
            "eligible_from_local": len(local_only_names),
            "local_sources": local_names,
            "local_only": local_only_names,
            "local_vertical_originals": local_scan["vertical_originals"],
            "local_scan_errors": local_scan["errors"],
            "skipped_vertical": len(skipped),
            "missing_sequences": missing,
            "seq_floors": {f"{date}{user}": floor for (date, user), floor in sorted(seq_floors.items())},
            "todo": names,
        }

    ok, fail = [], []
    total = len(names)
    for index, name in enumerate(names, start=1):
        item_start = time.monotonic()
        _log_event("week_item_start", user_filter=user_filter, index=index, total=total, name=name)
        parsed = parse_filename(name)
        min_output_seq = seq_floors.get((parsed["date"], parsed["user_code"]), 1) if parsed else 1
        result = full_pipeline(name, min_output_seq=min_output_seq)
        if result.get("success"):
            ok.append({"name": name, "vertical": result.get("vertical"), "reused": result.get("reused_existing", False)})
            _log_event(
                "week_item_done",
                user_filter=user_filter,
                index=index,
                total=total,
                name=name,
                reused=bool(result.get("reused_existing", False)),
                seconds=round(time.monotonic() - item_start, 1),
            )
        else:
            fail.append({"name": name, "error": result.get("error", "unknown")})
            _log_event(
                "week_item_failed",
                user_filter=user_filter,
                index=index,
                total=total,
                name=name,
                error=result.get("error", "unknown"),
                seconds=round(time.monotonic() - item_start, 1),
            )

    _log_event(
        "week_done",
        user_filter=user_filter,
        processed=len(ok),
        failed=len(fail),
        missing=len(missing),
        search_errors=len(search_errors),
        local_scan_errors=len(local_scan["errors"]),
        seconds=round(time.monotonic() - batch_start, 1),
    )

    return {
        "success": len(search_errors) == 0 and len(local_scan["errors"]) == 0 and len(fail) == 0 and len(missing) == 0,
        "mode": "week-pipeline",
        "week_start": week_start,
        "week_end": week_end,
        "user_filter": user_filter,
        "searched_prefixes": searched_prefixes,
        "search_errors": search_errors,
        "eligible_all_users": len(all_names),
        "eligible": len(names),
        "eligible_from_api": len(api_names),
        "eligible_from_local": len(local_only_names),
        "local_sources": local_names,
        "local_only": local_only_names,
        "local_vertical_originals": local_scan["vertical_originals"],
        "local_scan_errors": local_scan["errors"],
        "processed": len(ok),
        "failed": len(fail),
        "skipped_vertical": len(skipped),
        "missing_sequences": missing,
        "processed_list": ok,
        "failed_list": fail,
        "skipped_list": skipped,
    }

def download_single(video_name):
    parsed = parse_filename(video_name)
    if not parsed:
        return False, "文件名格式错误", None

    save_dir = get_save_dir(parsed["date"], parsed["user_code"])
    local_path = save_dir / f"{video_name}.mp4"
    reuse = _reuse_existing_download(local_path, video_name)
    if reuse:
        return reuse

    encoded = quote(video_name, safe='')
    url = f"{API_BASE}?name={encoded}"

    try:
        session = _new_media_session()
        resp = session.get(url, timeout=(DOWNLOAD_CONNECT_TIMEOUT_S, DOWNLOAD_READ_TIMEOUT_S))
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

    reuse = _reuse_existing_download(local_path, video_name)
    if reuse:
        return reuse
    _cleanup_stale_download_parts(local_path)

    last_error = None
    for attempt in range(1, DOWNLOAD_RETRIES + 2):
        tmp_path = local_path.with_suffix(local_path.suffix + f".{uuid.uuid4().hex}.part")
        start = time.monotonic()
        last_log_at = start
        last_log_bytes = 0
        bytes_written = 0
        try:
            _log_event(
                "download_start",
                name=video_name,
                attempt=attempt,
                max_attempts=DOWNLOAD_RETRIES + 1,
                url=video_url,
                path=str(local_path),
                proxy=MEDIA_USE_ENV_PROXY,
            )
            with session.get(
                video_url,
                stream=True,
                timeout=(DOWNLOAD_CONNECT_TIMEOUT_S, DOWNLOAD_READ_TIMEOUT_S),
            ) as vr:
                vr.raise_for_status()
                total_header = vr.headers.get("content-length")
                expected_total = int(total_header) if total_header and total_header.isdigit() else None
                with open(tmp_path, 'wb') as f:
                    for chunk in vr.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        now = time.monotonic()
                        if now - start > DOWNLOAD_TOTAL_TIMEOUT_S:
                            raise TimeoutError(f"下载总耗时超过 {DOWNLOAD_TOTAL_TIMEOUT_S}s")
                        if not chunk:
                            continue
                        f.write(chunk)
                        bytes_written += len(chunk)
                        elapsed = max(now - start, 0.001)
                        avg_rate = bytes_written / elapsed
                        if elapsed >= DOWNLOAD_MIN_RATE_AFTER_S and avg_rate < DOWNLOAD_MIN_RATE_BPS:
                            raise TimeoutError(
                                f"下载均速过低 {avg_rate/1024:.1f}KB/s < {DOWNLOAD_MIN_RATE_BPS/1024:.0f}KB/s"
                            )
                        if (now - last_log_at >= DOWNLOAD_PROGRESS_INTERVAL_S
                                or bytes_written - last_log_bytes >= DOWNLOAD_PROGRESS_BYTES):
                            _log_event(
                                "download_progress",
                                name=video_name,
                                attempt=attempt,
                                mb=round(bytes_written / 1024 / 1024, 1),
                                total_mb=round(expected_total / 1024 / 1024, 1) if expected_total else None,
                                avg_kbps=round(avg_rate / 1024, 1),
                            )
                            last_log_at = now
                            last_log_bytes = bytes_written

            if expected_total and bytes_written != expected_total:
                raise IOError(f"下载大小不完整 {bytes_written} != {expected_total}")
            os.replace(tmp_path, local_path)

            ok, msg = _validate_video_file(str(local_path))
            if not ok:
                try:
                    local_path.unlink()
                except Exception:
                    pass
                raise IOError(f"下载后校验失败: {msg}")

            _log_event(
                "download_done",
                name=video_name,
                attempt=attempt,
                mb=round(os.path.getsize(local_path) / 1024 / 1024, 1),
                seconds=round(time.monotonic() - start, 1),
            )
            return True, f"下载完成({os.path.getsize(local_path)//1024//1024}MB)", str(local_path)
        except Exception as e:
            last_error = e
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
            _log_event(
                "download_attempt_failed",
                name=video_name,
                attempt=attempt,
                max_attempts=DOWNLOAD_RETRIES + 1,
                error=str(e),
            )
            if attempt <= DOWNLOAD_RETRIES:
                time.sleep(min(2 * attempt, 6))

    return False, f"下载失败: {last_error}", None

def _get_tenant_token():
    """获取飞书 tenant access token（使用 requests 避免代理缓存问题）"""
    if FEISHU_ACCESS_TOKEN:
        return FEISHU_ACCESS_TOKEN
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        _log_event("feishu_credentials_missing", required="BACKSTAGE_FEISHU_APP_ID/BACKSTAGE_FEISHU_APP_SECRET")
        return ""
    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
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
    if not BITABLE_APP_TOKEN or not BITABLE_TABLE_ID:
        return None
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
    if not BITABLE_APP_TOKEN or not BITABLE_TABLE_ID:
        print(f"[write_to_bitable] ⏭️ 未配置 BITABLE_APP_TOKEN/BITABLE_TABLE_ID，跳过写表 [{original_name}]")
        return False
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

def full_pipeline(video_name, min_output_seq=None):
    parsed = parse_filename(video_name)
    if not parsed:
        return {"success": False, "error": f"文件名格式错误: {video_name}"}

    if min_output_seq is None:
        min_output_seq = _infer_min_output_seq_for_source(video_name, parsed)
    min_output_seq = int(min_output_seq or 1)
    _log_event("pipeline_start", name=video_name, min_output_seq=min_output_seq)

    with PipelineLock(parsed["date"], parsed["user_code"]):
        state = _load_state(parsed["date"], parsed["user_code"])
        record = state["records"].get(video_name, {})
        if record.get("vertical") and _record_has_reusable_vertical(record, parsed, min_output_seq=min_output_seq):
            _log_event("pipeline_reuse_state", name=video_name, vertical=record["vertical"])
            return _pipeline_success(
                video_name, parsed, record.get("downloaded", ""), record["vertical"],
                record.get("status", "改竖"), cover=record.get("cover") or None,
                cover_uncertain=record.get("cover_uncertain", False), reused=True
            )
        if record.get("vertical"):
            _log_event(
                "pipeline_ignore_state_low_seq",
                name=video_name,
                vertical=record.get("vertical"),
                min_output_seq=min_output_seq,
            )

    success, msg, download_path = download_single(video_name)
    if not success:
        _log_event("pipeline_failed", name=video_name, stage="download", error=msg)
        return {"success": False, "error": f"下载失败: {msg}"}

    ok, msg2 = _validate_video_file(download_path)
    if not ok:
        _log_event("pipeline_failed", name=video_name, stage="validate_download", error=msg2)
        return {"success": False, "error": f"下载文件异常: {msg2}"}

    with PipelineLock(parsed["date"], parsed["user_code"]):
        state = _load_state(parsed["date"], parsed["user_code"])
        record = state["records"].get(video_name, {})
        if record.get("vertical") and _record_has_reusable_vertical(record, parsed, min_output_seq=min_output_seq):
            _log_event("pipeline_reuse_state_after_download", name=video_name, vertical=record["vertical"])
            return _pipeline_success(
                video_name, parsed, download_path, record["vertical"],
                record.get("status", "改竖"), cover=record.get("cover") or None,
                cover_uncertain=record.get("cover_uncertain", False), reused=True
            )
        if record.get("vertical"):
            _log_event(
                "pipeline_ignore_state_low_seq_after_download",
                name=video_name,
                vertical=record.get("vertical"),
                min_output_seq=min_output_seq,
            )
        existing_vertical = _find_existing_vertical(
            video_name, parsed, source_path=download_path, min_output_seq=min_output_seq
        )
        if existing_vertical:
            result = _pipeline_success(
                video_name, parsed, download_path, existing_vertical,
                "改竖", cover=record.get("cover") or None, reused=True
            )
            _remember_success(state, video_name, result)
            _save_state(parsed["date"], parsed["user_code"], state)
            _log_event("pipeline_reuse_existing", name=video_name, vertical=existing_vertical)
            return result

        if is_vertical_video(download_path):
            result = _pipeline_success(video_name, parsed, download_path, download_path, "竖版原视频")
            _remember_success(state, video_name, result)
            _save_state(parsed["date"], parsed["user_code"], state)
            _log_event("pipeline_done", name=video_name, status="竖版原视频", vertical=download_path)
            return result

    cover, cover_uncertain = find_cover_image(video_name, video_path=download_path) or (None, False)
    success, output_path = process_vertical(download_path, cover)
    if not success:
        _log_event("pipeline_failed", name=video_name, stage="vertical", error=output_path)
        return {"success": False, "error": f"改竖失败: {output_path}"}

    ok_move, msg_move = _validate_video_file(output_path)
    if not ok_move:
        _log_event("pipeline_failed", name=video_name, stage="validate_vertical", error=msg_move)
        return {"success": False, "error": f"改竖成品异常: {msg_move}"}
    if not is_vertical_video(output_path):
        err = f"改竖成品尺寸异常: {get_video_dimensions(output_path)}"
        _log_event("pipeline_failed", name=video_name, stage="validate_vertical_dims", error=err)
        return {"success": False, "error": err}

    with PipelineLock(parsed["date"], parsed["user_code"]):
        state = _load_state(parsed["date"], parsed["user_code"])
        record = state["records"].get(video_name, {})
        if record.get("vertical") and _record_has_reusable_vertical(record, parsed, min_output_seq=min_output_seq):
            try:
                if output_path and os.path.exists(output_path) and output_path != download_path:
                    os.remove(output_path)
            except Exception:
                pass
            _log_event("pipeline_reuse_state_after_vertical", name=video_name, vertical=record["vertical"])
            return _pipeline_success(
                video_name, parsed, download_path, record["vertical"],
                record.get("status", "改竖"), cover=record.get("cover") or cover,
                cover_uncertain=record.get("cover_uncertain", cover_uncertain), reused=True
            )
        if record.get("vertical"):
            _log_event(
                "pipeline_ignore_state_low_seq_after_vertical",
                name=video_name,
                vertical=record.get("vertical"),
                min_output_seq=min_output_seq,
            )
        next_seq = get_next_seq(parsed["date"], parsed["user_code"], min_seq=min_output_seq)
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
        _log_event("pipeline_done", name=video_name, status="改竖", vertical=str(final_path))
        return result

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "用法: download.py '视频名' | --search '前缀' | --download-prefix '前缀' | --pipeline '视频名' | --batch-pipeline '前缀' | --week-pipeline"}))
        return

    arg1 = sys.argv[1]
    dry_run = "--dry-run" in sys.argv
    user_filter = _parse_option_value("--user")
    allowed_flags = {"--dry-run", "--user", "--all-users", "--confirm-all-users"}
    unknown_flags = [
        arg for i, arg in enumerate(sys.argv[2:], start=2)
        if arg.startswith("--")
        and arg not in allowed_flags
        and not (i > 0 and sys.argv[i - 1] == "--user")
    ]
    if unknown_flags:
        print(json.dumps({"success": False, "error": f"未知参数: {', '.join(unknown_flags)}"}, ensure_ascii=False))
        return
    if "--user" in sys.argv and not user_filter:
        print(json.dumps({"success": False, "error": "请提供用户代码，如 --user TM"}, ensure_ascii=False))
        return
    if user_filter and _all_users_requested():
        print(json.dumps({"success": False, "error": "--user 不能与 --all-users/--confirm-all-users 同时使用"}, ensure_ascii=False))
        return

    if arg1 == '--download-prefix':
        prefix = sys.argv[2] if len(sys.argv) > 2 else ''
        if not prefix:
            print(json.dumps({"error": "请提供前缀，如 --download-prefix 260421"}))
            return
        ok_scope, scope_error = _validate_user_scope("--download-prefix", user_filter)
        if not ok_scope:
            print(json.dumps({"success": False, "error": scope_error}, ensure_ascii=False))
            return
        if dry_run:
            result = run_batch_pipeline(prefix, dry_run=True, user_filter=user_filter)
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
            if not _result_matches_user(v, user_filter):
                continue
            if is_generated_vertical_name(name):
                skipped.append(name); continue
            success, message, path = download_single(name)
            if success:
                downloaded.append({"name": name, "path": str(path)})
        print(json.dumps({"success": True, "total": len(results), "user_filter": _normalize_user_filter(user_filter), "downloaded": len(downloaded), "skipped_vertical": len(skipped), "downloaded_list": downloaded, "skipped_list": skipped}, ensure_ascii=False))

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
        ok_scope, scope_error = _validate_user_scope("--batch-pipeline", user_filter)
        if not ok_scope:
            print(json.dumps({"success": False, "error": scope_error}, ensure_ascii=False))
            return
        result = run_batch_pipeline(prefix, dry_run=dry_run, user_filter=user_filter)
        print(json.dumps(result, ensure_ascii=False))

    elif arg1 == '--week-pipeline':
        ok_scope, scope_error = _validate_user_scope("--week-pipeline", user_filter)
        if not ok_scope:
            print(json.dumps({"success": False, "error": scope_error}, ensure_ascii=False))
            return
        result = run_week_pipeline(dry_run=dry_run, user_filter=user_filter)
        print(json.dumps(result, ensure_ascii=False))

    else:
        success, message, path = download_single(arg1)
        print(json.dumps({"success": success, "message": message, "path": path} if success else {"success": False, "error": message}, ensure_ascii=False))

if __name__ == "__main__":
    main()
