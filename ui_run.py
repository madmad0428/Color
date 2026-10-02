#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
실제 UI 자극 — 정답좌표 자동추출 + 모델 질의 + 분석.

전제: 스크린샷의 목표 버튼을 아래 8색조 중 하나로 칠해 저장해 둔 상태.
     파일명 규칙:  <사이트>_<라벨>_<색조>.png     예) github_New_245.png
     (색조는 20/65/110/155/200/245/290/335 중 하나)

동작:
  1) 각 이미지에서 '해당 색조' 픽셀 덩어리를 찾아 가장 큰 연결성분 = 목표 버튼으로 보고
     박스·중심좌표를 자동 산출 → ui_manifest.csv 생성
  2) 모델에 "그 라벨 버튼 중심 좌표"를 물어 결과 저장
  3) 색조별 집계

사용:
  python ui_run.py --build     # 1) 정답좌표 추출(이미지만 있으면 됨, API 불필요)
  python ui_run.py --check     # 추출 결과를 눈으로 확인할 오버레이 이미지 생성
  python ui_run.py             # 2) 모델 질의(이어서 돌리기 지원)
  python ui_run.py --analyze   # 3) 집계만
"""
import csv, json, os, re, math, sys, time, glob, statistics

IMG_DIR   = "."
MANIFEST  = "ui_manifest.csv"
RESULTS   = "ui_results.csv"
MODEL     = "gemini-3.5-flash-lite"
API_KEY   = ""
SLEEP     = 4
MAX_PER_RUN = None          # 무료 티어면 18 등으로 제한

# 통제된 8색조 (WCAG휘도 0.45 / CIELAB L* 72.9 / C* 40 동일, 색조만 45도 간격)
HUE_RGB = {
    20:(250,151,156), 65:(228,166,113), 110:(178,184,109), 155:(113,196,147),
    200:(24,198,203), 245:(67,191,244), 290:(165,174,248), 335:(230,155,211),
}
TOL = 45                    # 색 매칭 허용오차(맨해튼 거리). 안티앨리어싱 고려
MIN_AREA = 300              # 이보다 작은 덩어리는 버튼으로 안 봄

# ---------------- 1) 정답좌표 자동 추출 ----------------
def parse_name(fn):
    """<사이트>_<라벨>_<색조>.png → (site, label, hue)"""
    base = os.path.splitext(os.path.basename(fn))[0]
    parts = base.split("_")
    if len(parts) < 3: return None
    try: hue = int(parts[-1])
    except ValueError: return None
    if hue not in HUE_RGB: return None
    return parts[0], "_".join(parts[1:-1]), hue

def detect_button(path, hue):
    """해당 색조 픽셀의 최대 연결성분 = 목표 버튼. 반환 (x0,y0,x1,y1,area) 또는 None"""
    from PIL import Image
    import numpy as np
    from scipy import ndimage
    a = np.array(Image.open(path).convert("RGB")).astype(int)
    mask = (np.abs(a - np.array(HUE_RGB[hue])).sum(2) < TOL)
    if mask.sum() == 0: return None
    lab, n = ndimage.label(mask)
    sizes = ndimage.sum(mask, lab, range(1, n+1))
    i = int(np.argmax(sizes))
    if sizes[i] < MIN_AREA: return None
    ys, xs = np.where(lab == i+1)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()), int(sizes[i])

def build():
    from PIL import Image
    rows = []
    files = sorted(glob.glob(os.path.join(IMG_DIR, "*.png")) + glob.glob(os.path.join(IMG_DIR, "*.jpg")))
    for f in files:
        meta = parse_name(f)
        if not meta:
            print(f"  [건너뜀] 파일명 규칙 불일치: {os.path.basename(f)}"); continue
        site, label, hue = meta
        det = detect_button(f, hue)
        if not det:
            print(f"  [실패] 색조 {hue} 영역 못 찾음: {os.path.basename(f)}"); continue
        x0,y0,x1,y1,area = det
        W,H = Image.open(f).size
        rows.append({'file':os.path.basename(f), 'site':site, 'label':label, 'hue':hue,
                     'img_w':W, 'img_h':H,
                     'x0':x0,'y0':y0,'x1':x1,'y1':y1,
                     'cx':(x0+x1)//2, 'cy':(y0+y1)//2,
                     'bw':x1-x0+1, 'bh':y1-y0+1, 'area':area})
        print(f"  {os.path.basename(f):<34} 중심=({(x0+x1)//2},{(y0+y1)//2}) 크기={x1-x0+1}x{y1-y0+1} 면적={area}")
    if not rows: print("추출된 항목 없음"); return
    with open(MANIFEST,"w",newline="",encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    # --- 자체 검증 ---
    print("\n[검증] 같은 사이트·라벨의 8색조가 '같은 위치'를 가리키는가 (색만 바뀌었으므로 일치해야 정상)")
    from collections import defaultdict
    g = defaultdict(list)
    for r in rows: g[(r['site'], r['label'])].append(r)
    ok = True
    for (site,label), rs in sorted(g.items()):
        cxs = [r['cx'] for r in rs]; cys = [r['cy'] for r in rs]
        dx, dy = max(cxs)-min(cxs), max(cys)-min(cys)
        good = dx <= 3 and dy <= 3
        ok &= good
        print(f"  {site}/{label}: n={len(rs)}, 중심 편차 dx={dx} dy={dy} → {'OK' if good else '불일치(확인 필요)'}")
    print(f"\n총 {len(rows)}건 → {MANIFEST} 저장. 검증 {'통과' if ok else '주의 — 불일치 항목 확인'}")

# ---------------- 확인용 오버레이 ----------------
def check():
    from PIL import Image, ImageDraw
    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))
    os.makedirs("_check", exist_ok=True)
    for r in rows:
        im = Image.open(os.path.join(IMG_DIR, r['file'])).convert("RGB")
        d = ImageDraw.Draw(im)
        x0,y0,x1,y1 = int(r['x0']),int(r['y0']),int(r['x1']),int(r['y1'])
        cx,cy = int(r['cx']),int(r['cy'])
        d.rectangle([x0,y0,x1,y1], outline=(255,0,0), width=3)
        d.line([cx-14,cy,cx+14,cy], fill=(255,0,0), width=3)
        d.line([cx,cy-14,cx,cy+14], fill=(255,0,0), width=3)
        im.save(os.path.join("_check", r['file']))
    print(f"_check/ 폴더에 {len(rows)}장 생성 — 빨간 박스가 목표 버튼에 정확히 맞는지 눈으로 확인하세요")

# ---------------- 2) 모델 질의 ----------------
def parse_xy(t):
    m = re.search(r'\{[^{}]*\}', t, re.S)
    if m:
        try:
            o = json.loads(m.group(0)); return float(o['x']), float(o['y'])
        except Exception: pass
    n = re.findall(r'-?\d+\.?\d*', t)
    return (float(n[0]), float(n[1])) if len(n) >= 2 else None

FIELDS = ['file','site','label','hue','true_x','true_y','pred_x','pred_y',
          'err','dx','dy','box_in','fail','raw']

def query():
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=API_KEY)
    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))
    done = set()
    if os.path.exists(RESULTS):
        done = {r['file'] for r in csv.DictReader(open(RESULTS, encoding="utf-8-sig"))}
    todo = [r for r in rows if r['file'] not in done]
    if MAX_PER_RUN: todo = todo[:MAX_PER_RUN]
    print(f"전체 {len(rows)} / 완료 {len(done)} / 이번 {len(todo)}")

    for i, r in enumerate(todo):
        W,H = int(r['img_w']), int(r['img_h'])
        prompt = (f"이 화면에서 '{r['label']}' 버튼의 중심 픽셀 좌표를 구하세요.\n"
                  f"이미지 크기는 가로 {W}, 세로 {H}입니다.\n"
                  "설명 없이 JSON만 출력: {\"x\": <정수>, \"y\": <정수>}")
        img = open(os.path.join(IMG_DIR, r['file']), "rb").read()
        txt, err_flag = "", False
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=MODEL,
                    contents=[types.Part.from_bytes(data=img, mime_type="image/png"), prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.0, max_output_tokens=300,
                        thinking_config=types.ThinkingConfig(thinking_level="minimal")))
                txt = resp.text or ""; break
            except Exception as e:
                msg = str(e)
                if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                    wait = 25*(attempt+1); print(f"  (속도제한 {wait}s 대기)"); time.sleep(wait); continue
                txt = f"ERROR: {e}"; err_flag = True; break

        ab = None if err_flag or txt.startswith("ERROR") else parse_xy(txt)
        tx, ty = int(r['cx']), int(r['cy'])
        bw, bh = int(r['bw']), int(r['bh'])
        rec = {'file':r['file'],'site':r['site'],'label':r['label'],'hue':r['hue'],
               'true_x':tx,'true_y':ty,'raw':txt[:100]}
        if ab:
            # Gemini 확정 좌표계: 0~1000 정규화, x먼저
            px, py = ab[0]/1000*W, ab[1]/1000*H
            dx, dy = px-tx, py-ty; e = math.hypot(dx,dy)
            rec.update({'pred_x':round(px),'pred_y':round(py),'err':round(e,1),
                        'dx':round(dx,1),'dy':round(dy,1),
                        'box_in':int(abs(dx)<=bw/2 and abs(dy)<=bh/2),
                        'fail':int(e > min(W,H)/2)})
        else:
            rec.update({'pred_x':'','pred_y':'','err':'','dx':'','dy':'','box_in':'','fail':''})

        new = not os.path.exists(RESULTS)
        with open(RESULTS,'a',newline='',encoding='utf-8-sig') as fp:
            w = csv.DictWriter(fp, fieldnames=FIELDS)
            if new: w.writeheader()
            w.writerow(rec)
        print(f"[{i+1}/{len(todo)}] {r['site']}/{r['label']} hue{r['hue']} "
              f"err={rec.get('err')} box_in={rec.get('box_in')}", flush=True)
        if i < len(todo)-1: time.sleep(SLEEP)
    analyze()

# ---------------- 3) 분석 ----------------
def analyze():
    if not os.path.exists(RESULTS): print("결과 파일 없음"); return
    rows = [r for r in csv.DictReader(open(RESULTS, encoding="utf-8-sig")) if r['err'] != '']
    if not rows: print("유효 결과 없음"); return
    print(f"\n{'='*64}\n분석 n={len(rows)}\n{'='*64}")
    for key, label in [('hue','색조'), ('site','사이트'), ('label','라벨')]:
        vals = sorted(set(r[key] for r in rows), key=lambda x: (int(x) if x.isdigit() else x))
        if len(vals) < 2 and key != 'hue': continue
        print(f"\n[{label}별]")
        print(f"{label:>8} | {'박스-안':>7} | {'오차중앙':>8} | {'완전실패':>8} | n")
        print("-"*52)
        for v in vals:
            g = [r for r in rows if r[key]==v]
            good = [r for r in g if r['fail']=='0']
            bi = sum(int(r['box_in']) for r in g)/len(g)
            med = statistics.median([float(r['err']) for r in good]) if good else float('nan')
            nf = sum(1 for r in g if r['fail']=='1')
            print(f"{v:>8} | {bi*100:>6.1f}% | {med:>7.1f}px | {nf:>3}/{len(g):<3} | {len(g)}")

if __name__ == "__main__":
    if "--build" in sys.argv: build()
    elif "--check" in sys.argv: check()
    elif "--analyze" in sys.argv: analyze()
    else: query()