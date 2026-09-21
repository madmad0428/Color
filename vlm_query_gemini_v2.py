#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLM 질의 파일럿 — Gemini 버전 (전체 재작성본, v2).
이 파일 하나로 기존 vlm_query_gemini.py를 완전히 대체하세요(부분수정 아님).
"""
print("### SCRIPT VERSION: clean_rewrite_v2 ###")   # 이 줄이 안 찍히면 다른 파일이 실행된 것

import csv, json, os, re, math, time

MANIFEST = "stimuli_manifest.csv"
IMG_DIR  = "."
MODEL    = "gemini-3.5-flash-lite"     # 2.5-lite는 신규 사용자에게 막힘(2026-07-21 출시 모델로 교체)
TEMPERATURE = 0.0
N_TRIALS = None
W, H = 800, 520
SLEEP_BETWEEN_CALLS = 4                 # 초. 속도제한 여유를 두기 위한 대기

API_KEY = ""

PROMPT = (
  "이 이미지에는 여러 개의 버튼이 있습니다. 그중 회색이 아닌 '색이 있는 버튼' 하나가 있습니다.\n"
  "그 색 버튼의 '중심'의 픽셀 좌표를 구하세요. 이미지 크기는 가로 800, 세로 520입니다.\n"
  "설명 없이 JSON만 출력: {\"x\": <정수>, \"y\": <정수>}"
)

def parse_xy(text):
    m = re.search(r'\{[^{}]*\}', text, re.S)
    if m:
        try:
            o = json.loads(m.group(0))
            return float(o['x']), float(o['y'])
        except Exception:
            pass
    nums = re.findall(r'-?\d+\.?\d*', text)
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    return None

def normalize(x, y):
    if x > W * 1.3 or y > H * 1.3:
        return x / 1000 * W, y / 1000 * H
    return x, y

def call_model(client, types, img_bytes, retries=3):
    """429(속도제한)면 대기 후 재시도. 그 외 에러는 그대로 문자열로 반환."""
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                    PROMPT,
                ],
                config=types.GenerateContentConfig(
                    temperature=TEMPERATURE,
                    max_output_tokens=500,
                    thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                ),
            )
            return resp.text or "", False
        except Exception as e:
            msg = str(e)
            if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                wait = 20 * (attempt + 1)
                print(f"    (속도제한 — {wait}초 대기 후 재시도 {attempt+1}/{retries})")
                time.sleep(wait)
                continue
            return f"ERROR: {e}", True
    return f"ERROR: retries exhausted", True

def main():
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=API_KEY)

    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))
    if N_TRIALS:
        rows = rows[:N_TRIALS]

    out = []
    for i, r in enumerate(rows):
        with open(os.path.join(IMG_DIR, r['file']), "rb") as f:
            img_bytes = f.read()

        txt, err_occurred = call_model(client, types, img_bytes)
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
              f"true=({r['cx']},{r['cy']})  pred={rec['pred_x']},{rec['pred_y']}  "
              f"err={rec['err_px']}  hit={rec['hit']}", flush=True)

        if i < len(rows) - 1:
            time.sleep(SLEEP_BETWEEN_CALLS)

    with open("vlm_results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    hits = [r['hit'] for r in out if r['hit'] is not None]
    print(f"\n파싱 성공 {len(hits)}/{len(out)}, 히트율 {sum(hits)}/{len(hits) if hits else 0}")

if __name__ == "__main__":
    main()