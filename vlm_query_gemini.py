#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLM 질의 파일럿 — Gemini 버전.
준비:
  pip install google-genai pillow
  export GEMINI_API_KEY=" "      # Google AI Studio(aistudio.google.com)에서 무료 발급
사용:
  python vlm_query_gemini.py
"""
import csv, json, os, re, math, sys
print("### 이 파일이 실행되고 있음 ###")

MANIFEST = "stimuli_manifest.csv"          # 네 경로로 수정
IMG_DIR  = "."                              # 이미지 폴더
MODEL    = "gemini-2.5-flash"              # 2.0-flash는 2026-06-01 종료됨. 무료 티어 지원.
TEMPERATURE = 0.0                          # 반복 필요하면 >0
N_TRIALS = 6                               # 파일럿용. 전체면 None
W, H = 800, 520

PROMPT = (
  "이 이미지에는 여러 개의 버튼이 있습니다. 그중 회색이 아닌 '색이 있는 버튼' 하나가 있습니다.\n"
  "그 색 버튼의 '중심'의 픽셀 좌표를 구하세요. 이미지 크기는 가로 800, 세로 520입니다.\n"
  "설명 없이 JSON만 출력: {\"x\": <정수>, \"y\": <정수>}"
)

def parse_xy(text):
    m=re.search(r'\{[^{}]*\}', text, re.S)
    if m:
        try:
            o=json.loads(m.group(0)); return float(o['x']), float(o['y'])
        except Exception: pass
    nums=re.findall(r'-?\d+\.?\d*', text)
    if len(nums)>=2: return float(nums[0]), float(nums[1])
    return None

def normalize(x,y):
    # Gemini 2.x는 종종 0~1000 정규화 좌표를 냄 → 픽셀로 환산
    if x>W*1.3 or y>H*1.3:
        return x/1000*W, y/1000*H
    return x, y

def main():
    from google import genai
    from google.genai import types
    key=" "
    client=genai.Client(api_key=key)

    rows=list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))
    if N_TRIALS: rows=rows[:N_TRIALS]
    out=[]
    for i,r in enumerate(rows):
        with open(os.path.join(IMG_DIR, r['file']),"rb") as f:
            img_bytes=f.read()

        err_occurred=False
        try:
            resp=client.models.generate_content(
                model=MODEL,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                    PROMPT,
                ],
                config=types.GenerateContentConfig(
                    temperature=TEMPERATURE,
                    max_output_tokens=500,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            txt = resp.text or ""
        except Exception as e:
            txt = f"ERROR: {e}"
            err_occurred = True

        print("  >>> RAW:", repr(txt), flush=True)

        pred = None if err_occurred else parse_xy(txt)

        rec = {'file': r['file'], 'contrast': r['contrast'], 'hue': r['hue'],
               'true_x': int(r['cx']), 'true_y': int(r['cy']), 'raw': txt[:120]}
        if pred:
            px, py = normalize(*pred)
            err = math.hypot(px - int(r['cx']), py - int(r['cy']))
            rec.update({'pred_x': round(px), 'pred_y': round(py),
                        'err_px': round(err, 1), 'hit': err < 90})
        else:
            rec.update({'pred_x': None, 'pred_y': None, 'err_px': None, 'hit': None})

        out.append(rec)
        print(f"[{i+1}/{len(rows)}] {r['hue']} c{r['contrast']}  "
              f"true=({r['cx']},{r['cy']})  pred={rec.get('pred_x')},{rec.get('pred_y')}  "
              f"err={rec.get('err_px')}  hit={rec.get('hit')}", flush=True)

    with open("vlm_results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    hits = [r['hit'] for r in out if r['hit'] is not None]
    print(f"\n파싱 성공 {len(hits)}/{len(out)}, 히트율 {sum(hits)}/{len(hits) if hits else 0}")
    print("→ 확인: (1)좌표 파싱 (2)좌표계-Gemini는 0~1000 정규화가 흔함 (3)temperature (4)색조별 err 차이")

if __name__=="__main__":
    main()