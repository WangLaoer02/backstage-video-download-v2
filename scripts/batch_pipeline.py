#!/usr/bin/env python3
"""批量跑改竖pipeline"""
import subprocess, json, os, sys

videos = [
    "260421HR1-混擦边有什么好玩洛克王国黑死牟-原创-XSY",
    "260421HR3-洛克王国打得过吗三人-原创-XSY",
    "260421HR5-剪辑千抽验证-原创-XSY",
    "260421HR6-剪辑千抽验证-原创-XSY",
    "260421M1-主流阵容3D卡牌-KY-ZC",
    "260421TM1-发行人义勇攻略快产剪辑-原创-ZZX",
    "260421TM2-擦屏引流1500抽五条悟-QJ-ZZX",
    "260421TM3-发行人大佬和我差距引流首充6元得鬼化炎柱-原创-ZZX",
    "260421TM4-发行人扇巴掌引流左边不要继国缘一-原创-ZZX",
    "260421TM5-发行人义勇弹黑死牟引流首充六元得水柱-原创-ZZX",
    "260421TM6-发行人豌豆射手祢豆子快产剪辑-原创-ZZX",
    "260421ZL1-滑动SBTI属性积木人700级虎杖-RF",
    "260421ZL2-滑动SBTI属性积木人700级日车-RF",
    "260421ZL3-引流微信前贴五条悟一图流-RF-CSC",
    "260421ZL4-AI真人引流秒选甚尔-ZL-CSC",
]

env = os.environ.copy()
env["VISION_API_KEY"] = ""
env["VISION_API_URL"] = "http://localhost:11434/api/generate"
env["IPv6_ROOT"] = "http://[2408:8256:4c87:1dce:198d:7e8b:cc03:88aa]:9092"
env["FEISHU_ACCESS_TOKEN"] = "t-g1044ljzVMNNL24FORYJD3UP2OIEHFMKQE3AHP4N"

script_dir = os.path.dirname(os.path.abspath(__file__))
success, fail = 0, []
for v in videos:
    r = subprocess.run(
        [sys.executable, os.path.join(script_dir, "download.py"), "--pipeline", v],
        capture_output=True, text=True, env=env
    )
    try:
        d = json.loads(r.stdout)
        if d.get("success"):
            success += 1
            print(f"✅ {v}")
        else:
            fail.append(v)
            print(f"❌ {v}: {d.get('error','?')}")
    except:
        fail.append(v)
        print(f"❌ {v}: parse error {r.stdout[:100]}")

print(f"\n===== 批次完成：成功 {success} / 失败 {len(fail)} =====")
if fail:
    print("失败列表：", fail)