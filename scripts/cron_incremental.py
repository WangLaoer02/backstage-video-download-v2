#!/usr/bin/env python3
"""
cron增量检查脚本 - 轻量快速版
- 搜索近5天视频，与bitable已有记录比对
- 只处理新增原版横屏视频，跳过"改竖"版本
- 逐条执行下载+改竖+写表
"""
import subprocess, json, sys, os, time
from datetime import datetime, timedelta

SCRIPT = '/Users/galw/.openclaw/skills/backstage-video-download-v2/scripts/download.py'

def get_bitable_written():
    token_cmd = '''curl -s -X POST "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" -H "Content-Type: application/json" -d '{"app_id":"cli_a938d27bfc78dced","app_secret":"zISGY2UlMakJKK9z82j0AblZieQV8vk0"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tenant_access_token'])"'''
    token = subprocess.run(token_cmd, shell=True, capture_output=True, text=True, timeout=10).stdout.strip()
    payload = json.dumps({"page_size": 500})
    cmd = f'curl -s -X POST "https://open.feishu.cn/open-apis/bitable/v1/apps/SYP1b0qvOaY60xszqLycOK9PnNg/tables/tblewZ4BB4tHPnFC/records/search" -H "Authorization: Bearer {token}" -H "Content-Type: application/json" -d \'{payload}\''
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
    try:
        records = json.loads(result.stdout).get('data',{}).get('items',[])
        written = set()
        for r in records:
            fields = r.get('fields',{})
            name = fields.get('原命名','')
            if isinstance(name, list): name = name[0].get('text','') if name else ''
            written.add(str(name))
        return written
    except:
        return set()

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

    all_names = []
    seen = set()
    today_str = today.strftime('%Y%m%d')  # 20260430
    today_26mmdd = '26' + today.strftime('%m%d')  # 260430
    for date in dates:
        result = subprocess.run(['python3', SCRIPT, '--search', date], capture_output=True, text=True, timeout=10)
        try:
            data = json.loads(result.stdout)
            for v in data.get('results', []):
                name = v['name']
                # 跳过文件名格式不规范的今日批次（260430D格式，缺少suffix）
                import re
                if date == today_26mmdd and not re.match(r'^(2026\d{2})(\d{2})([A-Z]+)(\d+)-(.+)-([^-]+)(?:\.mp4)?$', name) and not re.match(r'^(26\d{4})([A-Z]+)(\d+)-(.+)-([^-]+)(?:\.mp4)?$', name):
                    continue
                if name not in seen and '改竖' not in name:
                    seen.add(name)
                    all_names.append(name)
        except:
            pass
    return all_names

def run_pipeline(name):
    result = subprocess.run(['python3', SCRIPT, '--pipeline', name], capture_output=True, text=True, timeout=120)
    try:
        for line in result.stdout.strip().split('\n'):
            try:
                data = json.loads(line)
                if data.get('success') == True:
                    return True
            except:
                continue
    except:
        pass
    return False

def main():
    print(f"[cron] 开始增量检查...")
    
    written = get_bitable_written()
    print(f"[cron] bitable已记录: {len(written)} 条")
    
    all_api = search_recent_videos()
    print(f"[cron] 近5天原版视频: {len(all_api)} 条")
    
    new_videos = [n for n in all_api if n not in written]
    print(f"[cron] 新增待处理: {len(new_videos)} 条")
    
    if not new_videos:
        print("[cron] 无新增素材，退出")
        return
    
    ok, fail = 0, 0
    for name in new_videos:
        print(f"[cron] 处理: {name}", flush=True)
        try:
            success = run_pipeline(name)
            if success:
                ok += 1
                print(f"[cron] ✅ {name}")
            else:
                fail += 1
                print(f"[cron] ❌ {name}")
        except Exception as e:
            fail += 1
            print(f"[cron] ❌ {name}: {e}")
        time.sleep(0.5)
    
    print(f"[cron] 完成: 成功{ok} 失败{fail}")

if __name__ == '__main__':
    main()
