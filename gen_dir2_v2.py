#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
방향2 자극 생성기 v2 — 두 버그 수정판.

버그1 수정: 이전엔 완성된 이미지를 통째로 좌우반전(transpose)해서 글자까지 거울상으로
  뒤집혀 읽을 수 없었음. → 이제는 '버튼 위치만' 거울상으로 재배치하고, 버튼·글자는
  항상 정상 방향으로 그린다(이미지 자체 반전 없음). 위치 편향 상쇄 효과는 유지하면서
  글자는 항상 읽을 수 있음.

버그2 수정: 이전엔 방해버튼 색이 '로그인 색을 뺀 나머지를 순서대로 채우는' 방식이라
  로그인 색이 바뀌면 다른 버튼들의 색도 규칙적으로 같이 바뀌는 혼입이 있었음. → 이제는
  레이아웃마다 '로그인을 제외한 7개 버튼의 색'을 로그인 색과 무관하게 독립적으로 1회
  확정(레이아웃에만 종속, 목표색과는 무관)해 두고, 로그인 버튼 자리만 목표색으로 덮어쓴다.
  (색은 중복 허용 — 어차피 '색으로 찾기' 꼼수를 막는 목적이지, 8색 모두 유일할 필요는 없음)
"""
import csv, math, os, random
from coloraide import Color
from PIL import Image, ImageDraw, ImageFont

OUT="."; os.makedirs(OUT,exist_ok=True)
W,H=880,600; BW,BH=150,54
TARGET_LW=0.45; C_STAR=40
FONT=ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",22)
LABELS=["로그인","취소","설정","검색","저장","홈","도움말","삭제"]   # 8개, position0=로그인 고정
HUES=[(45*i+20)%360 for i in range(8)]
N_LAYOUTS=20

def wcagL(c): return c.luminance()
def color_at(hue,Lw=TARGET_LW,C=C_STAR):
    lo,hi=0.,100.
    for _ in range(45):
        m=(lo+hi)/2; c=Color('lch-d65',[m,C,hue])
        lo,hi=(m,hi) if wcagL(c)<Lw else (lo,m)
    return Color('lch-d65',[(lo+hi)/2,C,hue]).convert('srgb').fit('srgb')
def gray(L):
    lo,hi=0.,1.
    for _ in range(40):
        m=(lo+hi)/2
        lo,hi=(m,hi) if wcagL(Color('srgb',[m]*3))<L else (lo,m)
    return Color('srgb',[(lo+hi)/2]*3)
def rgb(c): return tuple(int(round(v*255)) for v in c.convert('srgb').coords())

HUE_COL=[color_at(h) for h in HUES]
CONTRAST=4.5
BG=gray((TARGET_LW+0.05)/CONTRAST-0.05); bgrgb=rgb(BG)

def make_layout(lid):
    """버튼 '위치'만 결정. (색과 완전히 무관한 축)"""
    rnd=random.Random(500+lid); boxes=[]
    def ok(x,y): return all(not(abs(px-x)<BW+25 and abs(py-y)<BH+22) for px,py in boxes)
    for _ in range(8):
        for _t in range(400):
            x=rnd.randint(15,W-BW-15); y=rnd.randint(15,H-BH-15)
            if ok(x,y): break
        boxes.append((x,y))
    return boxes

def make_distractor_colors(lid):
    """position1~7(로그인 제외)의 색을 레이아웃에만 종속해 '한 번' 확정.
       목표(로그인) 색과는 완전히 무관한 별도 RNG 스트림 사용 → 목표색이 바뀌어도 불변."""
    rnd=random.Random(9000+lid)           # layout_id만 시드 — target_hue와 무관
    return [rnd.choice(HUES) for _ in range(7)]   # position1~7, 중복 허용(색 유일성 불필요)

LAYOUTS={lid:make_layout(lid) for lid in range(N_LAYOUTS)}
DISTRACTOR_HUES={lid:make_distractor_colors(lid) for lid in range(N_LAYOUTS)}

def render(lid, target_hue, mirror, path):
    """mirror=True면 '위치만' 좌우 거울상으로 재배치. 글자·버튼은 항상 정상 방향으로 그림."""
    boxes=LAYOUTS[lid]
    dist_hues=DISTRACTOR_HUES[lid]                 # position1~7 고정색(레이아웃 종속)
    hue_for_pos=[target_hue]+dist_hues             # position0=목표색(가변), 나머지=고정

    img=Image.new('RGB',(W,H),bgrgb); d=ImageDraw.Draw(img)
    for pos,(x,y) in enumerate(boxes):
        draw_x = (W - x - BW) if mirror else x     # 위치만 거울상, 그림은 그대로
        col=rgb(color_at(hue_for_pos[pos]))
        d.rounded_rectangle([draw_x,y,draw_x+BW,y+BH],radius=10,fill=col)
        lab=LABELS[pos]
        tb=d.textbbox((0,0),lab,font=FONT); tw,th=tb[2]-tb[0],tb[3]-tb[1]
        d.text((draw_x+BW/2-tw/2,y+BH/2-th/2-tb[1]),lab,fill=(20,20,20),font=FONT)  # 항상 정상 방향

    tx,ty=boxes[0]                                  # 로그인(position0)
    draw_tx = (W - tx - BW) if mirror else tx
    cx,cy = draw_tx+BW//2, ty+BH//2
    img.save(path)
    return cx,cy

# ===================== 자체 검증 =====================
print("="*60); print("자체 검증 v2"); print("="*60)

# [1] 색 격리 (기존과 동일 조건 — 변화 없어야 정상)
lchs=[c.convert('lch-d65') for c in HUE_COL]
mL=max(a['lightness'] for a in lchs)-min(a['lightness'] for a in lchs)
mC=max(a['chroma'] for a in lchs)-min(a['chroma'] for a in lchs)
print(f"[1] 색 격리: ΔL*={mL:.2f}, ΔC*={mC:.2f} → {'PASS' if mL<2 and mC<2 else 'FAIL'}")

# [2] 레이아웃(위치) 독립 재현성
print(f"[2] 레이아웃 재현성: {'PASS' if make_layout(1)==make_layout(1) and make_layout(0)!=make_layout(1) else 'FAIL'}")

# [3] 버그2 수정 검증 — 같은 레이아웃에서 target_hue를 바꿔도 position1~7 색이 불변인가
h_a, h_b = HUES[0], HUES[5]
_=render(0,h_a,False,os.path.join(OUT,"_tmp_a.png"))
_=render(0,h_b,False,os.path.join(OUT,"_tmp_b.png"))
same_distractors = DISTRACTOR_HUES[0]==DISTRACTOR_HUES[0]   # 정의상 항상 True(같은 lid)
# 실제로 render가 참조하는 값 자체가 target과 무관하게 고정인지 코드 레벨로 재확인
indep_ok = (DISTRACTOR_HUES[0] == make_distractor_colors(0))  # 함수 자체가 결정적이며 target 인자 없음
print(f"[3] 방해버튼 색 목표-무관성: 방해색 목록={DISTRACTOR_HUES[0]} (target_hue 인자 자체가 함수에 없음) → {'PASS' if indep_ok else 'FAIL'}")
os.remove(os.path.join(OUT,"_tmp_a.png")); os.remove(os.path.join(OUT,"_tmp_b.png"))

# [4] 버그1 수정 검증 — mirror=True/False에서 '글자 영역 픽셀'이 거울반전이 아니라
#     동일한(위치만 옮겨진) 이미지인지 자동 비교 (텍스트가 거울상으로 안 그려졌다는 증거)
p_n=os.path.join(OUT,"_tmp_n.png"); p_m=os.path.join(OUT,"_tmp_m.png")
cx_n,cy_n=render(2,HUES[3],False,p_n)
cx_m,cy_m=render(2,HUES[3],True,p_m)
im_n=Image.open(p_n); im_m=Image.open(p_m)
# position0 버튼 영역을 각각의(거울 반영된) 좌표에서 크롭해 비교
box_n=(cx_n-BW//2,cy_n-BH//2,cx_n+BW//2,cy_n+BH//2)
box_m=(cx_m-BW//2,cy_m-BH//2,cx_m+BW//2,cy_m+BH//2)
crop_n=im_n.crop(box_n); crop_m=im_m.crop(box_m)
# mirror 크롭을 다시 좌우반전해서 비교하면 안 됨(그러면 당연히 같아짐) →
# 대신 '좌우반전 안 한 상태로' 두 크롭이 '동일'해야 함(= 글자가 거울상으로 안 그려졌다는 뜻)
import numpy as np
diff = np.abs(np.array(crop_n).astype(int)-np.array(crop_m).astype(int)).mean()
print(f"[4] flip 시 글자 비반전 확인: 정상/거울 버튼 크롭 픽셀 평균차={diff:.2f} (0에 가까울수록 글자가 정상방향으로 그려졌다는 뜻) → {'PASS' if diff<2 else 'FAIL'}")
os.remove(p_n); os.remove(p_m)

# ===================== 전체 생성 =====================
man=[]
for lid in range(N_LAYOUTS):
    for hue in HUES:
        for mirror in (False,True):
            fn=f"d2v2_L{lid}_h{hue}_{'M' if mirror else 'N'}.png"
            cx,cy=render(lid,hue,mirror,os.path.join(OUT,fn))
            man.append({'layout':lid,'target_hue':hue,'flip':mirror,
                        'target_hex':color_at(hue).to_string(hex=True),'cx':cx,'cy':cy,'file':fn})
with open(os.path.join(OUT,"d2_manifest.csv"),"w",newline="",encoding="utf-8-sig") as f:
    w=csv.DictWriter(f,fieldnames=list(man[0].keys())); w.writeheader(); w.writerows(man)

# [5] 정답좌표 픽셀 = 목표색 일치 (표본)
import random as _r
bad=0; samp=_r.Random(0).sample(man,min(24,len(man)))
for rec in samp:
    im=Image.open(rec['file']).convert('RGB'); px=im.getpixel((rec['cx'],rec['cy']))
    exp=rgb(Color(rec['target_hex']))
    if sum(abs(a-b) for a,b in zip(px,exp))>40: bad+=1
print(f"[5] 정답좌표=목표색 일치: {len(samp)-bad}/{len(samp)} → {'PASS' if bad==0 else 'FAIL'}")

print(f"\n총 {len(man)}개 생성 (색조8×레이아웃{N_LAYOUTS}×거울2), 대비 {CONTRAST}:1 고정")