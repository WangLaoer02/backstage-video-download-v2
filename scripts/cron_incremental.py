#!/usr/bin/env python3
"""
cron 增量检查脚本。
- 搜索近 5 天批次
- 使用 download.py 的本地幂等状态防重复
- 每个日期走 --batch-pipeline，输出缺号和失败列表
"""
import subprocess, json, sys, os, time
from pathlib import Path
from datetime import datetime, timedelta

SCRIPT = str(Path(__file__).resolve().parent / "download.py")

def search_recent_videos():
    """搜索近5天所有批次（26MMDD + 2026MMDD）"""
    today = datetime.now()
    dates = []
    for i in range(5):
        d = today - timedelta(days=i)
        mmdd = d.strftime('%m%d')
        yyyymm = d.strftime('%Y%m')
        dates.append(f'26{mmdd}')
        dates.append(f'{yyyymm[:4]}{mmdd}')

    seen = set()
    found_dates = []
    for date in dates:
        result = subprocess.run(['python3', SCRIPT, '--search', date], capture_output=True, text=True, timeout=10)
        try:
            data = json.loads(result.stdout)
            if data.get('results') and date not in seen:
                seen.add(date)
                found_dates.append(date)
        except:
            pass
    return found_dates

def run_batch(prefix):
    result = subprocess.run(['python3', SCRIPT, '--batch-pipeline', prefix], capture_output=True, text=True, timeout=3600)
    try:
        return json.loads(result.stdout)
    except:
        return {"success": False, "error": result.stderr[-500:] or result.stdout[-500:]}

def main():
    print(f"[cron] 开始增量检查...")

    prefixes = search_recent_videos()
    print(f"[cron] 近5天有素材的批次: {len(prefixes)} 个")

    if not prefixes:
        print("[cron] 无新增素材，退出")
        return

    ok, fail = 0, []
    for prefix in prefixes:
        print(f"[cron] 批次: {prefix}", flush=True)
        result = run_batch(prefix)
        if result.get("success"):
            ok += 1
            print(f"[cron] ✅ {prefix} processed={result.get('processed')} reused/skip included")
        else:
            fail.append({"prefix": prefix, "result": result})
            print(f"[cron] ❌ {prefix}: {result.get('error') or result.get('failed_list') or result.get('missing_sequences')}")
        time.sleep(0.5)

    print(f"[cron] 完成: 成功批次{ok} 失败批次{len(fail)}")
    if fail:
        print(json.dumps({"failed_batches": fail}, ensure_ascii=False))

if __name__ == '__main__':
    main()
