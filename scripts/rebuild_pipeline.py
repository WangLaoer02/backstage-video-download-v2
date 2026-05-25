#!/usr/bin/env python3
"""清理+重跑全套 pipeline"""
import subprocess, json, os, sys, time

UAT = subprocess.run(
    ['security', 'find-generic-password', '-s', 'openclaw-feishu-uat',
     '-a', 'cli_a95bb0b4d7789cca:ou_e9dbf7ae826a707ada0796d2a01312d3', '-w'],
    capture_output=True, text=True
).stdout.strip()
uat_data = json.loads(UAT)
ACCESS_TOKEN = uat_data['accessToken']

BITABLE_APP_TOKEN = "XmyBb5LkBa1Z1qshn66cXJzZn3f"
BITABLE_TABLE_ID = "tblfzNPVIsidZ9KM"

env = os.environ.copy()
env["VISION_API_KEY"] = ""
env["VISION_API_URL"] = "http://localhost:11434/api/generate"
env["IPv6_ROOT"] = "http://[2408:8256:4c87:1dce:198d:7e8b:cc03:88aa]:9092"
env["FEISHU_ACCESS_TOKEN"] = ACCESS_TOKEN

script_dir = "/Users/galw/.openclaw/skills/backstage-video-download-v2/scripts"

# 视频列表：(日期目录, 原始文件名)
videos = [
    # 0421
    ("2026-04-21", "260421HR1-混擦边有什么好玩洛克王国黑死牟-原创-XSY"),
    ("2026-04-21", "260421HR3-洛克王国打得过吗三人-原创-XSY"),
    ("2026-04-21", "260421HR5-剪辑千抽验证-原创-XSY"),
    ("2026-04-21", "260421HR6-剪辑千抽验证-原创-XSY"),
    ("2026-04-21", "260421JR1-漩涡鸣人像素700一图流技能-原创-BY"),
    ("2026-04-21", "260421M1-主流阵容3D卡牌-KY-ZC"),
    ("2026-04-21", "260421TM1-发行人义勇攻略快产剪辑-原创-ZZX"),
    ("2026-04-21", "260421TM2-擦屏引流1500抽五条悟-QJ-ZZX"),
    ("2026-04-21", "260421TM3-发行人大佬和我差距引流首充6元得鬼化炎柱-原创-ZZX"),
    ("2026-04-21", "260421TM4-发行人扇巴掌引流左边不要继国缘一-原创-ZZX"),
    ("2026-04-21", "260421TM5-发行人义勇弹黑死牟引流首充六元得水柱-原创-ZZX"),
    ("2026-04-21", "260421TM6-发行人豌豆射手祢豆子快产剪辑-原创-ZZX"),
    ("2026-04-21", "260421ZL1-滑动SBTI属性积木人700级虎杖-RF"),
    ("2026-04-21", "260421ZL2-滑动SBTI属性积木人700级日车-RF"),
    ("2026-04-21", "260421ZL3-引流微信前贴五条悟一图流-RF-CSC"),
    ("2026-04-21", "260421ZL4-AI真人引流秒选甚尔-ZL-CSC"),
    # 0420
    ("2026-04-20", "260420JR1-擦边舞接和风打开昨天刚注册的号-YJJ"),
    ("2026-04-20", "260420JR2-擦边舞接纲手展示崩铁UI战斗-YJJ"),
    ("2026-04-20", "260420JR3-擦边舞接和风主力培养佩恩-原创"),
    ("2026-04-20", "260420JR4-擦边舞接合区去鬼服换主界面-原创"),
    ("2026-04-20", "260420JR5-擦边舞接3点教你玩五条悟-原创"),
    ("2026-04-20", "260420JR6-擦边舞接主播官方承诺重度五条悟-M"),
    ("2026-04-20", "260420JR7-卡卡西像素700一图流技能-原创-BY"),
    ("2026-04-20", "260420JR8-宇智波鼬像素700一图流技能-原创-BY"),
    ("2026-04-20", "260420JR9-擦边舞接女主播千抽福利-原创"),
    ("2026-04-20", "260420JR10-波风水门像素700一图流技能-原创-BY"),
    ("2026-04-20", "260420LJJ1-1570抽开头有一千抽伏黑甚尔换红色-原创"),
    ("2026-04-20", "260420LJJ2-新角色不想抽-KY"),
    ("2026-04-20", "260420LJJ3-拉力车千抽引流抖小攻略一不小心-TM-ZZX"),
    ("2026-04-20", "260420LJJ4-拉力车千抽引流一打五黑死牟-TM-ZZX"),
    ("2026-04-20", "260420LJJ5-首充鼬踩捧换版面-TM-ZZX"),
    ("2026-04-20", "260420TM1-发行人千抽剪辑-原创-ZZX"),
    ("2026-04-20", "260420TM2-发行人千抽剪辑-原创-ZZX"),
    ("2026-04-20", "260420TM3-发行人千抽剪辑-原创-ZZX"),
    ("2026-04-20", "260420TM4-发行人千抽剪辑-原创-ZZX"),
    ("2026-04-20", "260420TM5-发行人千抽剪辑-原创-ZZX"),
    ("2026-04-20", "260420TM6-发行人千抽剪辑-原创-ZZX"),
    ("2026-04-20", "260420TM7-拉力车千抽引流SBTI一图流700级黑死牟-原创-ZZX"),
    ("2026-04-20", "260420TM8-拉力车千抽引流SBTI一图流700级缘一-原创-ZZX"),
    ("2026-04-20", "260420TM9-拉力车千抽引流擦边鬼灭手游不是氪金氪不起口播福利-原创-ZZX"),
    ("2026-04-20", "260420TM10-拉力车千抽引流鬼灭手游不是氪金氪不起口播福利-原创-ZZX"),
    ("2026-04-20", "260420TM11-拉力车千抽引流开局选蝴蝶忍口播-原创-ZZX"),
    ("2026-04-20", "260420TM12-改首充6元鼬踩捧-原创-ZZX"),
    ("2026-04-20", "260420TM13-十级送卡卡西-原创-ZZX"),
    ("2026-04-20", "260420TM14-改首充6元鼬踩捧-原创-ZZX"),
    ("2026-04-20", "260420TM15-呐喊引流大蛇鼬踩捧解说带佐助换开头-YJJ-ZZX"),
    ("2026-04-20", "260420WY1-打酱板鸭说不说接800关五条悟-原创"),
    ("2026-04-20", "260420WY2-打酱板鸭说不说接呐喊开局秒选甚尔-原创"),
    ("2026-04-20", "260420WY3-打酱板鸭说不说接首充6元五条悟-原创"),
    ("2026-04-20", "260420ZL1-基本主流阵容-KY"),
    ("2026-04-20", "260420ZL2-打得过吗三人-QJ-XSY"),
    ("2026-04-20", "260420ZL4-拉力车千抽引流700级悲鸣屿行冥一图流-TM-ZZX"),
    ("2026-04-20", "260420ZL5-拉力车千抽引流700级继国缘一一图流-TM-ZZX"),
    ("2026-04-20", "260420D1-开局四选一卡卡西-D-ZZH"),
]

print(f"总共 {len(videos)} 条待处理")
success, fail, skip = 0, 0, 0

for date_dir, video_name in videos:
    print(f"\n[{success + fail + skip + 1}/{len(videos)}] {date_dir} | {video_name[:40]}", flush=True)
    r = subprocess.run(
        [sys.executable, os.path.join(script_dir, "download.py"), "--pipeline", video_name],
        capture_output=True, text=True, env=env
    )
    try:
        d = json.loads(r.stdout)
        if d.get("success"):
            vn = d.get("vertical","").split("/")[-1]
            print(f"  ✅ -> {vn}")
            success += 1
        else:
            err = d.get("error","?")
            print(f"  ❌ {err}")
            fail += 1
    except Exception as e:
        # 可能是下载已存在（跳过）
        if "已下载" in r.stdout or os.path.exists(f"/Volumes/美术AI龙虾/公共资源/后台下载/{date_dir}/{video_name}.mp4"):
            print(f"  ⏭️ 跳过（文件已存在）")
            skip += 1
        else:
            print(f"  ❌ parse error: {r.stdout[:100]}")
            fail += 1
    time.sleep(0.5)

print(f"\n===== Pipeline 完成：成功 {success} / 失败 {fail} / 跳过 {skip} =====")
