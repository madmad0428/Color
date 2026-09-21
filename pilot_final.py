#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
파일럿 최종 — v3의 '극성 혼입'을 교정.
v3 문제: 대비를 올리며 밝은배경↔어두운배경이 뒤집혀 대비와 극성이 섞임.
해법: 극성을 하나로 고정 — 버튼이 '항상 배경보다 밝다'(=배경은 어두운 회색).
      이 방향이 도달 가능한 대비 범위가 더 넓다(버튼 어두운 방향은 ~3.2:1에서 막힘).
산출: 색조 격리된 버튼 4색(밝기·채도·WCAG휘도 동일) × 대비 3수준, 정답좌표 포함.
"""
import csv, math, os, random
from coloraide import Color
from PIL import Image, ImageDraw

OUT="."; os.makedirs(OUT,exist_ok=True)
def wcag_L(c): return c.luminance()
def contrast(a,b): hi,lo=max(a,b),min(a,b); return (hi+0.05)/(lo+0.05)
HUES={'빨강':34,'노랑':95,'초록':142,'파랑':282}
TARGET_LW, C_STAR = 0.28, 64      # v3에서 찾은 스위트스팟(공통 채도 최대)
CONTRASTS=[1.5,3.0,4.5]

def color_fixed(hue,Lw,Cstar,tol=0.002):
    lo,hi=0.,100.; best=None
    for _ in range(45):
        m=(lo+hi)/2; c=Color('lch-d65',[m,Cstar,hue]); best=c
        if abs(wcag_L(c)-Lw)<tol: break
        lo,hi=(m,hi) if wcag_L(c)<Lw else (lo,m)
    return best.convert('srgb').fit('srgb')

BTN={n:color_fixed(h,TARGET_LW,C_STAR) for n,h in HUES.items()}

# 극성 고정: 버튼이 항상 더 밝음 → 배경은 어두운 회색. 도달 가능 대비 상한 확인.
ceiling=(TARGET_LW+0.05)/0.05      # bg_L=0일 때의 대비비
print(f"버튼 WCAG휘도={TARGET_LW}, 고정 극성=버튼이 배경보다 밝음")
print(f"이 극성으로 도달 가능한 대비 상한 ≈ {ceiling:.1f}:1")
for r in CONTRASTS:
    if r>ceiling: print(f"  ⚠ {r}:1 은 이 극성으로 불가(버튼 휘도를 올려야 함, 단 채도 손해)")

def gray_L(L):
    lo,hi=0.,1.
    for _ in range(40):
        m=(lo+hi)/2
        lo,hi=(m,hi) if wcag_L(Color('srgb',[m]*3))<L else (lo,m)
    return Color('srgb',[(lo+hi)/2]*3)

bg_by={}
print("\n대비 | 배경L | 배경HEX | 실측대비 | 극성")
for r in CONTRASTS:
    bgL=(TARGET_LW+0.05)/r-0.05          # 항상 어두운 배경(버튼이 밝음)
    bg=gray_L(max(bgL,0)); bg_by[r]=bg
    pol='버튼>배경' if wcag_L(bg)<TARGET_LW else '역전!'
    print(f"{r:>4}:1 | {wcag_L(bg):>5.3f} | {bg.to_string(hex=True)} | {contrast(wcag_L(bg),TARGET_LW):>5.2f}:1 | {pol}")

def make_ui(tc,bg,path,seed=0,W=800,H=520,flip=False):
    rnd=random.Random(seed)
    img=Image.new('RGB',(W,H),tuple(int(round(v*255)) for v in bg.coords())); d=ImageDraw.Draw(img)
    bw,bh=150,60; placed=[]; bgl=wcag_L(bg)
    ok=lambda x,y: all(not(abs(px-x)<bw+30 and abs(py-y)<bh+25) for px,py in placed)
    for _ in range(4):
        for _ in range(200):
            x=rnd.randint(20,W-bw-20); y=rnd.randint(20,H-bh-20)
            if ok(x,y): break
        placed.append((x,y))
        g=int(round(min(bgl+0.14,0.85)*255))   # 방해버튼: 배경보다 약간 밝은 무채색
        d.rounded_rectangle([x,y,x+bw,y+bh],radius=10,fill=(g,g,g))
    for _ in range(200):
        tx=rnd.randint(20,W-bw-20); ty=rnd.randint(20,H-bh-20)
        if ok(tx,ty): break
    d.rounded_rectangle([tx,ty,tx+bw,ty+bh],radius=10,fill=tuple(int(round(v*255)) for v in tc.coords()))
    cx,cy=tx+bw//2,ty+bh//2
    if flip: img=img.transpose(Image.FLIP_LEFT_RIGHT); cx=W-cx
    img.save(path); return (cx,cy)

man=[]
for ri,r in enumerate(CONTRASTS):
    for hi,n in enumerate(HUES):
        for flip in (False,True):            # 좌우 반전 쌍(위치 편향 상쇄)
            tag=n+('_R' if flip else '_L')
            p=f"{OUT}/ui_c{r}_{tag}.png"; c=make_ui(BTN[n],bg_by[r],p,seed=ri*10+hi,flip=flip)
            man.append({'contrast':r,'hue':n,'flip':flip,'btn_hex':BTN[n].to_string(hex=True),
                        'bg_hex':bg_by[r].to_string(hex=True),'cx':c[0],'cy':c[1],'file':os.path.basename(p)})
with open(f"{OUT}/stimuli_manifest.csv","w",newline="",encoding="utf-8-sig") as f:
    w=csv.DictWriter(f,fieldnames=list(man[0].keys())); w.writeheader(); w.writerows(man)
print(f"\n생성 {len(man)}개(대비{len(CONTRASTS)}×색조{len(HUES)}×반전2) + stimuli_manifest.csv")