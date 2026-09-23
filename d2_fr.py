#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
재파일럿 — 본설계 자극(방해버튼 포함)을 Gemini에 돌려 색조 효과를 측정.
좌표계는 calib으로 확정된 '정규화·x먼저'를 고정 사용(추측 로직 제거).
측정: 색조별/대비별 — 박스-안 성공률 + 오차중앙값(완전실패 제외) + 완전실패율 + dx/dy.

기능:
  - 이어서 돌리기(resume): 이미 끝낸 파일은 건너뜀 → 무료 티어(하루 20건)로 며칠 분할 가능
  - 결과는 매 건 즉시 저장(중간에 끊겨도 진행 보존)
사용:
  python repilot_run.py           # 질의(이어서) + 마지막에 분석
  python repilot_run.py --analyze # 질의 없이 저장된 결과만 재분석(무료·즉시)
"""
import csv, json, os, re, math, sys, time, statistics

MANIFEST="d2_manifest_fr.csv"      # gen_v2가 만든 것
IMG_DIR="."
RESULTS="d2_results_fr.csv"
MODEL="gemini-3.5-flash-lite"
API_KEY=""
W,H=880,600; BW,BH=150,60
SLEEP=4                               # 호출 간 대기(초)
MAX_PER_RUN=None                      # 한 번에 최대 몇 건(무료면 18 정도로 제한 권장), None=전부

PROMPT=("이 이미지에는 글자가 적힌 버튼이 여러 개 있습니다.\n"
        "그중 '로그인' 이라고 적힌 버튼의 '중심'의 픽셀 좌표를 구하세요. 이미지 크기는 가로 880, 세로 600입니다.\n"
        "설명 없이 JSON만 출력: {\"x\": <정수>, \"y\": <정수>}")

# calib 확정: 정규화(0~1000)·x먼저
def convert(x, y): return (x/1000*W, y/1000*H)

def parse_ab(t):
    m=re.search(r'\{[^{}]*\}',t,re.S)
    if m:
        try: o=json.loads(m.group(0)); return float(o['x']),float(o['y'])
        except Exception: pass
    n=re.findall(r'-?\d+\.?\d*',t)
    return (float(n[0]),float(n[1])) if len(n)>=2 else None

def box_in(px,py,tx,ty): return abs(px-tx)<=BW/2 and abs(py-ty)<=BH/2

FIELDS=['file','layout','hue','flip','true_x','true_y',
        'pred_x','pred_y','err','dx','dy','box_in','fail','raw']

def load_done():
    if not os.path.exists(RESULTS): return set()
    with open(RESULTS,encoding='utf-8-sig') as f:
        return {r['file'] for r in csv.DictReader(f)}

def append_result(rec):
    new=not os.path.exists(RESULTS)
    with open(RESULTS,'a',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        if new: w.writeheader()
        w.writerow(rec)

def query_all():
    from google import genai
    from google.genai import types
    client=genai.Client(api_key=API_KEY)
    rows=list(csv.DictReader(open(MANIFEST,encoding='utf-8-sig')))
    done=load_done()
    todo=[r for r in rows if r['file'] not in done]
    if MAX_PER_RUN: todo=todo[:MAX_PER_RUN]
    print(f"전체 {len(rows)} / 완료 {len(done)} / 이번에 돌릴 것 {len(todo)}")
    for i,r in enumerate(todo):
        img=open(os.path.join(IMG_DIR,r['file']),'rb').read()
        txt=""
        for attempt in range(3):
            try:
                resp=client.models.generate_content(model=MODEL,
                    contents=[types.Part.from_bytes(data=img,mime_type="image/png"),PROMPT],
                    config=types.GenerateContentConfig(temperature=0.0,max_output_tokens=300,
                        thinking_config=types.ThinkingConfig(thinking_level="minimal")))
                txt=resp.text or ""; break
            except Exception as e:
                msg=str(e)
                if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                    wait=25*(attempt+1); print(f"  (속도제한 {wait}s 대기)"); time.sleep(wait); continue
                txt=f"ERROR: {e}"; break
        ab=parse_ab(txt) if not txt.startswith("ERROR") else None
        tx,ty=int(r['cx']),int(r['cy'])
        rec={'file':r['file'],'layout':r['layout'],'hue':r['target_hue'],
             'flip':r['flip'],'true_x':tx,'true_y':ty,'raw':txt[:100]}
        if ab:
            px,py=convert(*ab); dx,dy=px-tx,py-ty; e=math.hypot(dx,dy)
            rec.update({'pred_x':round(px),'pred_y':round(py),'err':round(e,1),
                        'dx':round(dx,1),'dy':round(dy,1),
                        'box_in':int(box_in(px,py,tx,ty)),'fail':int(e>min(W,H)/2)})
        else:
            rec.update({'pred_x':'','pred_y':'','err':'','dx':'','dy':'','box_in':'','fail':''})
        append_result(rec)
        print(f"[{i+1}/{len(todo)}] r['target_hue'] L{r['layout']} "
              f"err={rec.get('err')} box_in={rec.get('box_in')}", flush=True)
        if i<len(todo)-1: time.sleep(SLEEP)
    analyze()

def _agg(rows):
    """한 그룹의 (박스-안%, 오차중앙값[실패제외], 완전실패율, dx중앙, dy중앙, n)"""
    ok=[r for r in rows if r.get('err') not in ('',None)]
    fails=[r for r in ok if int(r['fail'])==1]
    good=[r for r in ok if int(r['fail'])==0]
    boxin=sum(int(r['box_in']) for r in ok)/len(ok) if ok else float('nan')
    med=statistics.median([float(r['err']) for r in good]) if good else float('nan')
    dxm=statistics.median([float(r['dx']) for r in good]) if good else float('nan')
    dym=statistics.median([float(r['dy']) for r in good]) if good else float('nan')
    return boxin, med, len(fails), dxm, dym, len(ok)

def analyze():
    if not os.path.exists(RESULTS): print("결과 파일 없음"); return
    rows=list(csv.DictReader(open(RESULTS,encoding='utf-8-sig')))
    print(f"\n{'='*66}\n분석 (n={len(rows)})  — 오차중앙값은 완전실패 제외\n{'='*66}")
    for key,label in [('hue','목표색조')]:
        print(f"\n[{label}별]")
        print(f"{label:>7} | {'박스-안':>7} | {'오차중앙':>8} | {'완전실패':>8} | {'dx중앙':>7} | {'dy중앙':>7} | n")
        print("-"*66)
        for v in sorted(set(r[key] for r in rows)):
            g=[r for r in rows if r[key]==v]
            bi,med,nf,dxm,dym,n=_agg(g)
            print(f"{v:>7} | {bi*100:>6.1f}% | {med:>7.1f}px | {nf:>4}/{n:<3} | {dxm:>+6.1f} | {dym:>+6.1f} | {n}")
    # 파랑 이상치·대비 비단조 재현 여부를 눈에 띄게
    print(f"\n※ 확인 포인트: (1)특정 색조만 오차중앙/완전실패 튀나(파랑?) "
          f"(2)대비 3.0이 1.5·4.5보다 나은 비단조 재현되나 (3)레이아웃 걸쳐 일관된가")

if __name__=="__main__":
    analyze() if "--analyze" in sys.argv else query_all()