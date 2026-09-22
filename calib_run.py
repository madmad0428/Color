#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
좌표계 검증 v2 — 박스-안 판정 + 여러 색조 + 환산 잔차 + 색무관성 확인.
목적: (1) 모델의 좌표 환산 규칙 확정 (2) 그 규칙이 색과 무관한지 확인
      (3) 환산 잔차를 수치화(→ 나중에 볼 색조 효과보다 작아야 신뢰 가능)
판정: 예측점이 목표버튼 박스(150x60) 안에 들면 성공 = ScreenSpot 표준.
사용: python calib_run.py            (Gemini 실제 질의; API_KEY 채우기)
      python calib_run.py --simulate (API 없이 분석로직 자체검증)
"""
import csv, json, re, math, sys, statistics

TRUTH="calib_truth.csv"; W,H=800,520; BW,BH=150,60
API_KEY=""; MODEL="gemini-3.5-flash-lite"
PROMPT=("이 이미지에 버튼이 하나 있습니다. 그 버튼 '중심'의 픽셀 좌표를 구하세요.\n"
        "이미지 크기는 가로 800, 세로 520입니다. 설명 없이 JSON만: {\"x\": <정수>, \"y\": <정수>}")

HYP={"절대·x먼저":lambda a,b:(a,b), "절대·y먼저":lambda a,b:(b,a),
     "정규화·x먼저":lambda a,b:(a/1000*W,b/1000*H), "정규화·y먼저":lambda a,b:(b/1000*W,a/1000*H)}

def parse_ab(t):
    m=re.search(r'\{[^{}]*\}',t,re.S)
    if m:
        try: o=json.loads(m.group(0)); return float(o['x']),float(o['y'])
        except Exception: pass
    n=re.findall(r'-?\d+\.?\d*',t)
    return (float(n[0]),float(n[1])) if len(n)>=2 else None

def box_in(px,py,tx,ty):
    return abs(px-tx)<=BW/2 and abs(py-ty)<=BH/2

def pick_hypothesis(records):
    score={}
    for name,conv in HYP.items():
        hits=sum(box_in(*conv(r['ans_a'],r['ans_b']),r['true_x'],r['true_y']) for r in records)
        score[name]=hits/len(records)
    best=max(score,key=lambda k:score[k])
    print(f"\n{'가설':>14} | 박스-안 성공률")
    print("-"*32)
    for n,s in sorted(score.items(),key=lambda x:-x[1]):
        print(f"{n:>14} | {s*100:>5.1f}%  {'<= 최적' if n==best else ''}")
    return best

def analyze(records):
    best=pick_hypothesis(records); conv=HYP[best]
    print(f"\n▶ 최적 좌표계: '{best}'")
    print(f"\n[색무관성 + 잔차] 색조별 (성공률·잔차 서로 비슷해야 = 환산은 색과 무관)")
    print(f"{'색조':>6} | {'박스-안':>7} | {'오차중앙':>8} | {'dx중앙':>7} | {'dy중앙':>7} | {'완전실패':>7}")
    print("-"*60)
    hues=sorted(set(r['hue'] for r in records)); all_res=[]
    for hu in hues:
        rs=[r for r in records if r['hue']==hu]
        errs=[]; dxs=[]; dys=[]; fail=0
        for r in rs:
            px,py=conv(r['ans_a'],r['ans_b'])
            dx,dy=px-r['true_x'],py-r['true_y']; e=math.hypot(dx,dy)
            if e>min(W,H)/2: fail+=1
            else: errs.append(e); dxs.append(dx); dys.append(dy)
        boxin=sum(box_in(*conv(r['ans_a'],r['ans_b']),r['true_x'],r['true_y']) for r in rs)/len(rs)
        med=statistics.median(errs) if errs else float('nan'); all_res+=errs
        print(f"{hu:>6} | {boxin*100:>6.1f}% | {med:>7.1f}px | "
              f"{(statistics.median(dxs) if dxs else 0):>+6.1f} | {(statistics.median(dys) if dys else 0):>+6.1f} | {fail:>4}/{len(rs)}")
    resid=statistics.median(all_res) if all_res else float('nan')
    print(f"\n▶ 전체 환산 잔차(중앙값) = {resid:.1f}px")
    print(f"  → 나중에 볼 '색조별 오차 차이'가 이 값보다 커야 색 효과를 신뢰 가능")
    return best,resid

def run_real():
    from google import genai
    from google.genai import types
    import time
    client=genai.Client(api_key=API_KEY)
    truth=list(csv.DictReader(open(TRUTH,encoding="utf-8-sig"))); records=[]
    for i,r in enumerate(truth):
        img=open(r['file'],"rb").read()
        try:
            resp=client.models.generate_content(model=MODEL,
                contents=[types.Part.from_bytes(data=img,mime_type="image/png"),PROMPT],
                config=types.GenerateContentConfig(temperature=0.0,max_output_tokens=300,
                    thinking_config=types.ThinkingConfig(thinking_level="minimal")))
            txt=resp.text or ""
        except Exception as e: txt=f"ERROR: {e}"
        ab=parse_ab(txt)
        print(f"[{i+1}/{len(truth)}] {r['hue']} true=({r['true_x']},{r['true_y']}) raw={txt[:50]!r}")
        if ab: records.append({'hue':r['hue'],'true_x':int(r['true_x']),'true_y':int(r['true_y']),
                               'ans_a':ab[0],'ans_b':ab[1]})
        time.sleep(4)
    analyze(records)

def run_simulate():
    truth=list(csv.DictReader(open(TRUTH,encoding="utf-8-sig")))
    import random; rnd=random.Random(0); records=[]
    for r in truth:
        tx,ty=int(r['true_x']),int(r['true_y'])
        a=ty/H*1000+rnd.uniform(-10,10); b=tx/W*1000+rnd.uniform(-10,10)  # 정규화·y먼저
        records.append({'hue':r['hue'],'true_x':tx,'true_y':ty,'ans_a':a,'ans_b':b})
    print("[시뮬] 진짜 규칙='정규화·y먼저'. 분석기가 이걸 찾고, 색조별 결과가 비슷해야 정상.")
    best,resid=analyze(records)
    print(f"\n자체검증: {'PASS' if best=='정규화·y먼저' else 'FAIL'}")

if __name__=="__main__":
    (run_simulate if "--simulate" in sys.argv else run_real)()