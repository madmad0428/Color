#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
방향2 본실험 분석 — 주 지표는 '탐지 실패율'(정밀도는 천장이라 변별 안 됨).
색조별 실패율 + Wilson 95% 신뢰구간 → CI가 겹치면 '차이는 노이즈'.
전체 카이제곱으로 '색조 효과가 존재하나' 검정(df=7, 임계 14.07 @ .05).
사용: python d2_analyze.py                (d2_results_fr.csv 분석)
      python d2_analyze.py --selftest     (null/효과 있음 가짜데이터로 로직 검증)
"""
import csv, math, sys, random

Z=1.96
def wilson(k,n):
    if n==0: return (float('nan'),float('nan'),float('nan'))
    p=k/n; d=1+Z*Z/n
    c=(p+Z*Z/(2*n))/d
    h=Z/d*math.sqrt(p*(1-p)/n+Z*Z/(4*n*n))
    return p, max(0,c-h), min(1,c+h)

def chi2_hue(rows):
    """색조 × {성공,실패} 카이제곱 통계량."""
    hues=sorted(set(r['hue'] for r in rows))
    tot_f=sum(1 for r in rows if r['fail']=='1'); tot=len(rows)
    if tot==0 or tot_f==0 or tot_f==tot: return 0.0,len(hues)-1
    pf=tot_f/tot; stat=0.0
    for h in hues:
        g=[r for r in rows if r['hue']==h]; n=len(g); f=sum(1 for r in g if r['fail']=='1')
        for obs,exp in [(f,n*pf),(n-f,n*(1-pf))]:
            if exp>0: stat+=(obs-exp)**2/exp
    return stat, len(hues)-1

def analyze(rows):
    rows=[r for r in rows if r.get('fail') not in ('',None)]
    print(f"\n분석 n={len(rows)}  (주 지표: 탐지 실패율 + Wilson 95% CI)")
    print(f"{'색조':>6} | {'실패/n':>8} | {'실패율':>6} | {'95% CI':>16} | 막대")
    print("-"*62)
    hues=sorted(set(r['hue'] for r in rows), key=lambda x:int(x))
    for h in hues:
        g=[r for r in rows if r['hue']==h]; n=len(g); k=sum(1 for r in g if r['fail']=='1')
        p,lo,hi=wilson(k,n)
        bar='█'*round(p*30)
        print(f"{h:>6} | {k:>3}/{n:<4} | {p*100:>5.1f}% | [{lo*100:>4.1f},{hi*100:>5.1f}]% | {bar}")
    stat,df=chi2_hue(rows); crit=14.07
    print(f"\n카이제곱(색조효과) = {stat:.2f} (df={df}, .05 임계 {crit})")
    if stat>crit:
        print("  → 임계 초과: 색조에 따른 실패율 차이가 통계적으로 유의(우연 아님)")
    else:
        print("  → 임계 미만: 색조 간 실패율 차이를 우연과 구분 못 함(= 효과 근거 없음)")
    print("  ※ 판정법: 색조들의 CI가 서로 겹치면 그 차이는 노이즈로 봐야 함")

def selftest():
    random.seed(0); hues=[str(h) for h in [20,65,110,155,200,245,290,335]]
    # (A) null: 모든 색조 실패율 동일(15%)
    A=[{'hue':h,'fail':'1' if random.random()<0.15 else '0'} for h in hues for _ in range(40)]
    # (B) 효과: 245만 실패율 60%, 나머지 15%
    B=[{'hue':h,'fail':'1' if random.random()<(0.60 if h=='245' else 0.15) else '0'} for h in hues for _ in range(40)]
    print("="*62); print("[자체검증 A] null(효과 없음) — 카이제곱 임계 미만이어야 정상"); print("="*62)
    analyze(A)
    print("\n"+"="*62); print("[자체검증 B] 245만 나쁨 — 카이제곱 임계 초과 + 245 CI 분리돼야 정상"); print("="*62)
    analyze(B)

if __name__=="__main__":
    if "--selftest" in sys.argv: selftest()
    else:
        rows=list(csv.DictReader(open("d2_results.csv",encoding="utf-8-sig")))
        analyze(rows)