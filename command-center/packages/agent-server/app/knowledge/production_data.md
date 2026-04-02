# Production Agent Knowledge — MES DB + 생산 분석 패턴
기준일: 2026-04-02

## 1. MES DB 접속 정보
- Server: 192.161.0.16:1433 (내부망)
- Database: MES
- User: mestmp / 읽기 전용
- ODBC 드라이버: "ODBC Driver 18 for SQL Server" 우선, 없으면 17, "SQL Server" 순

## 2. 공장 코드
| 코드 | 이름 | 비고 |
|------|------|------|
| 1100 | 퍼플카운티 | 퍼플 |
| 1200 | 그린카운티 | 그린 |
| 1300 | 제3공장 | 3공장 |

## 3. 핵심 테이블 맵 (2026-03-29 기준)

### 실시간 트랜잭션 (대시보드 핵심)
| ID | 테이블 | 건수 | 용도 |
|----|--------|------|------|
| RT-01 | MWIPLOTHIS | 2,172,402 | 생산 LOT별 CV/IN/OUT 트랜잭션 — ★실시간 모니터링 |
| RT-02 | MWIPLOTSTS | 369,870 | LOT 현재 상태/위치/수량 — ★LOT 진행상태 추적 |
| RT-03 | MWIPORDSTS | 14,961 | 생산 작업지시 현황 — ★지시 대비 실적 추적 |
| RT-04 | MWIPNWKSTS | 5,522 | 라인별 비가동 시간/유형/사유 — ★가동률 분석 |
| RT-05 | MWIPLOTCQH | 350,151 | LOT별 품질확인 이력 |
| RT-06 | MINVLOTHIS | 5,110,691 | 자재 입출고 트랜잭션 |
| RT-07 | MINVLOTISS | 2,348,210 | 원부자재 출고 이력 |
| RT-08 | MINVLOTSTS | 746,714 | 자재 LOT 현재 상태 |
| RT-09 | MQCMREQSTS | 113,377 | 품질검사 요청 현황 |
| RT-10 | CQCMAPRSTS | 34,112 | 품질 승인 현황 |
| RT-11 | MWIPBOMCMP | 788,643 | BOM 자재 구성 |

### I/F 인터페이스 (ERP ↔ MES)
| ID | 테이블 | 건수 | 용도 |
|----|--------|------|------|
| IF-01 | IWIPMATDEF | 1,180,320 | 자재마스터 (ERP→MES) |
| IF-05 | IWIPORDSTS | 91,859 | 작업지시 인터페이스 (ERP→MES) — 수주 원본 추적 |
| IF-06 | IINVDLVDTL | 23,903 | 납품상세 |
| IF-08 | IINVSHPDTL | 11,559 | 출하상세 |
| IF-09 | IQCMINCSTS | 15,610 | 수입검사 |

### 마스터/정의 테이블 (조인용)
| ID | 테이블 | 건수 | 용도 |
|----|--------|------|------|
| MST-01 | MWIPMATDEF | 424,104 | 품목코드→품목명/규격/단위 — ★모든 조회의 기본 조인 |
| MST-04 | MWIPLINDEF | 268 | 라인코드→라인명/유형/교대시간 — ★라인유형(충진/타정/포장) |
| MST-05 | MWIPOPRDEF | 651 | 공정코드→공정명 |
| MST-07 | MWIPCUSDEF | 2,433 | 거래처코드→거래처명 |
| MST-08 | MWIPVENDEF | 4,371 | 공급업체 마스터 |

## 4. MWIPORDSTS 핵심 컬럼 (작업지시)
```
PLAN_DATE     — 계획일자 (YYYYMMDD)
ORD_DATE      — 지시일자 (YYYYMMDD)
FACTORY_CODE  — 공장코드 (1100/1200/1300)
LINE_CODE     — 라인코드
ORDER_NO      — 작업지시번호
MAT_CODE      — 제품코드
ORD_QTY       — 계획수량
ORD_OUT_QTY   — 실적수량
RCV_GOOD_QTY  — 양품수량
RCV_LOSS_QTY  — 불량수량
ORD_STATUS    — 상태 (PLAN/WAIT/CONFIRM/PROCESS/CLOSE/DELETE)
ORD_START_TIME — 시작시간
ORD_END_TIME  — 종료시간
```
- 항상 `ORD_STATUS NOT IN ('DELETE')` 조건 포함
- 달성률 = ORD_OUT_QTY / ORD_QTY × 100
- 불량률 = RCV_LOSS_QTY / (RCV_GOOD_QTY + RCV_LOSS_QTY) × 100
- 완료 판단: ORD_STATUS = 'CLOSE' OR ORD_OUT_QTY >= ORD_QTY × 0.95

## 5. IWIPORDSTS 핵심 컬럼 (수주 인터페이스)
```
SO_NO         — 수주번호
CUST_PO_NO    — 고객 PO번호
CUSTOMER_CODE — 거래처코드
ORDER_NO      — 작업지시번호 (MWIPORDSTS 조인키)
ORD_QTY       — 수주수량
ORD_END_TIME  — 납기일 (YYYYMMDD)
ORD_START_TIME — 시작일
CONFIRM_DATE  — 확정일
IF_SQ         — I/F 시퀀스 (최신=가장 큰 값)
```
- 최신 수주만 조회: `ROW_NUMBER() OVER(PARTITION BY FACTORY_CODE, ORDER_NO ORDER BY IF_SQ DESC) = 1`
- 26년 데이터: `CONFIRM_DATE >= '20260101'`
- 이월 진행중 포함: `ORD_STATUS IN ('PLAN','WAIT','CONFIRM','PROCESS') AND ORD_OUT_QTY < ORD_QTY*0.95`

## 6. 검증된 SQL 패턴

### 공장별 일일 생산 KPI
```sql
SELECT
    FACTORY_CODE,
    COUNT(DISTINCT ORDER_NO) as ORD_COUNT,
    SUM(ORD_QTY) as PLAN_QTY,
    SUM(ORD_OUT_QTY) as PROD_QTY,
    SUM(RCV_GOOD_QTY) as GOOD_QTY,
    SUM(RCV_LOSS_QTY) as LOSS_QTY,
    CASE WHEN SUM(ORD_QTY)>0
         THEN CAST(100.0*SUM(ORD_OUT_QTY)/SUM(ORD_QTY) AS decimal(5,2))
         ELSE 0 END as ACHIEVEMENT,
    CASE WHEN SUM(RCV_GOOD_QTY+RCV_LOSS_QTY)>0
         THEN CAST(100.0*SUM(RCV_GOOD_QTY)/(SUM(RCV_GOOD_QTY)+SUM(RCV_LOSS_QTY)) AS decimal(5,2))
         ELSE 100 END as YIELD_RATE
FROM MWIPORDSTS
WHERE PLAN_DATE = 'YYYYMMDD'
  AND ORD_STATUS NOT IN ('DELETE')
GROUP BY FACTORY_CODE
ORDER BY FACTORY_CODE
```

### 불량률 Top3 품목
```sql
SELECT TOP 3
    o.MAT_CODE, m.MAT_DESC,
    SUM(o.RCV_LOSS_QTY) as LOSS_QTY,
    CAST(100.0*SUM(o.RCV_LOSS_QTY)/(SUM(o.RCV_GOOD_QTY)+SUM(o.RCV_LOSS_QTY)) AS decimal(5,2)) as DEFECT_RATE
FROM MWIPORDSTS o
LEFT JOIN MWIPMATDEF m ON o.FACTORY_CODE=m.FACTORY_CODE AND o.MAT_CODE=m.MAT_CODE
WHERE o.PLAN_DATE='YYYYMMDD'
  AND (o.RCV_GOOD_QTY+o.RCV_LOSS_QTY) > 100
GROUP BY o.MAT_CODE, m.MAT_DESC
HAVING SUM(o.RCV_LOSS_QTY) > 0
ORDER BY DEFECT_RATE DESC
```

### 납기 리스크 분석 (미완료 수주)
```sql
WITH LATEST_I AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER(PARTITION BY FACTORY_CODE, ORDER_NO ORDER BY IF_SQ DESC) AS _rn
        FROM IWIPORDSTS WHERE SO_NO IS NOT NULL AND SO_NO <> ''
    ) _t WHERE _rn=1
)
SELECT i.SO_NO, i.CUSTOMER_CODE,
    MIN(v.VENDOR_DESC) AS cust_name,
    SUM(i.ORD_QTY) AS so_qty,
    SUM(ISNULL(o.ORD_OUT_QTY,0)) AS total_out,
    SUM(i.ORD_QTY)-SUM(ISNULL(o.ORD_OUT_QTY,0)) AS remaining,
    MAX(i.ORD_END_TIME) AS deadline,
    CAST(SUM(ISNULL(o.ORD_OUT_QTY,0))*100.0/SUM(i.ORD_QTY) AS DECIMAL(5,1)) AS pct
FROM LATEST_I i
INNER JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
LEFT JOIN MWIPVENDEF v ON i.CUSTOMER_CODE=v.VENDOR_CODE AND i.FACTORY_CODE=v.FACTORY_CODE
WHERE (i.CONFIRM_DATE >= '20260101'
   OR (o.ORD_STATUS IN ('PLAN','WAIT','CONFIRM','PROCESS') AND (o.ORD_QTY=0 OR o.ORD_OUT_QTY < o.ORD_QTY*0.95)))
GROUP BY i.SO_NO, i.CUSTOMER_CODE
HAVING SUM(ISNULL(o.ORD_OUT_QTY,0)) < SUM(i.ORD_QTY)*0.98
ORDER BY MAX(i.ORD_END_TIME), SUM(i.ORD_QTY) DESC
```
- 납기 리스크 분류: deadline < today AND pct < 95% → OVERDUE / deadline ≤ 다음달 AND pct < 50% → HIGH / deadline < today → MEDIUM

### 미완료 작업지시 잔량 (백로그)
```sql
SELECT COUNT(*) as CNT, SUM(ORD_QTY - ORD_OUT_QTY) as REMAIN_QTY
FROM MWIPORDSTS
WHERE ORD_STATUS = 'CONFIRM' AND ORD_OUT_QTY < ORD_QTY AND ORD_QTY > 0
  AND FACTORY_CODE IN ('1100','1200','1300')
```

### 7일내 자재 부족 예측
```sql
SELECT COUNT(*) as CNT
FROM (
    SELECT b.CHILD_MAT_CODE,
        SUM(o.ORD_QTY * b.COMPONENT_QTY / 1000.0) as NEED,
        ISNULL(inv.STK, 0) as STK
    FROM MWIPORDSTS o
    INNER JOIN MWIPBOMCMP b ON o.MAT_CODE = b.BOM_SET_CODE
    LEFT JOIN (SELECT MAT_CODE, SUM(QTY) as STK FROM CINVBASDAT WHERE STATUS='S' AND QTY>0 GROUP BY MAT_CODE) inv
        ON b.CHILD_MAT_CODE = inv.MAT_CODE
    WHERE o.ORD_STATUS = 'CONFIRM' AND o.ORD_OUT_QTY = 0
      AND o.PLAN_DATE BETWEEN CONVERT(char(8), GETDATE(), 112) AND CONVERT(char(8), DATEADD(day,7,GETDATE()), 112)
    GROUP BY b.CHILD_MAT_CODE, inv.STK
    HAVING ISNULL(inv.STK, 0) < SUM(o.ORD_QTY * b.COMPONENT_QTY / 1000.0)
) t
```

### 유통기한 임박 재고 (30일 이내)
```sql
SELECT COUNT(*) as CNT FROM CINVBASDAT
WHERE USE_TERM IS NOT NULL AND LEN(USE_TERM) = 8
  AND STATUS = 'S' AND QTY > 0
  AND DATEDIFF(day, GETDATE(), CONVERT(datetime, USE_TERM, 112)) BETWEEN 0 AND 30
```

### 납기 변경 이력 감지
```sql
WITH ranked AS (
    SELECT SHIP_ORD_NO, SHIP_PLAN_DATE, CUSTOMER_CODE, IF_SQ,
        LAG(SHIP_PLAN_DATE) OVER (PARTITION BY SHIP_ORD_NO ORDER BY IF_SQ) as PREV_DATE
    FROM IINVSHPMST
    WHERE SHIP_PLAN_DATE IS NOT NULL AND SHIP_PLAN_DATE != ''
)
SELECT r.SHIP_ORD_NO, r.PREV_DATE as OLD_DATE, r.SHIP_PLAN_DATE as NEW_DATE,
    r.CUSTOMER_CODE, c.CUSTOMER_DESC,
    CASE WHEN r.SHIP_PLAN_DATE < r.PREV_DATE THEN 'EARLIER' ELSE 'LATER' END as DIRECTION,
    DATEDIFF(day, CONVERT(datetime,r.PREV_DATE,112), CONVERT(datetime,r.SHIP_PLAN_DATE,112)) as DIFF_DAYS
FROM ranked r
LEFT JOIN MWIPCUSDEF c ON r.CUSTOMER_CODE = c.CUSTOMER_CODE
WHERE r.PREV_DATE IS NOT NULL AND r.SHIP_PLAN_DATE != r.PREV_DATE
  AND LEN(r.PREV_DATE)=8 AND LEN(r.SHIP_PLAN_DATE)=8
ORDER BY r.IF_SQ DESC
```

### 설비 알람 (미확인)
```sql
SELECT TOP 10
    ALARM_HIST_ID, TRAN_TIME, FACTORY_CODE, ALARM_CODE, ALARM_LEVEL,
    DISPLAY_TITLE, DISPLAY_CONTENTS
FROM MADMALMHIS
WHERE ACK_FLAG = 0 AND ALARM_LEVEL IN ('WARNING', 'CRITICAL')
ORDER BY TRAN_TIME DESC
```

## 7. 알람 임계값
- 불량률: 5.0% 이상 → 알람 (0.5% 초과 주의, 1% 초과 경보)
- 달성률: 50.0% 미만 → 알람 (80% 미만 경보, 60% 미만 긴급)
- 재고 최소: 10,000개
- 유통기한 임박: 30일

## 8. MES 스케줄러 (기존 봇 패턴)
| 봇 | 스케줄 | 역할 |
|----|--------|------|
| 생산 브리핑 | 08:00, 12:00, 17:00 (평일) | 공장별 달성률/불량률 |
| 이상 알림 | 07:00~21:00 (2시간마다, 평일) | 불량급증/달성률저조/설비알람 |
| 납기 감시 | 07:30, 13:30 (평일) | 납기변경/자재미입고/생산미연동 |
| QC 긴급 | 07:00, 14:00 (평일) | 품질검사 불합격 |
| 경영진 브리핑 | 18:00 (평일) | 일일 경영 KPI 원페이지 |
| 주간 리포트 | 09:00 (월요일) | 주간 생산 종합 |

## 9. 수주/납기 분석 대시보드 패턴 (sales_dashboard.py / MES_납기분석)

### 거래처별 수주 변경이력 조회
```sql
SELECT f.FACTORY_CODE, f.ORDER_NO, f.SO_NO,
    f.ORD_QTY AS orig_qty, l.ORD_QTY AS new_qty,
    f.ORD_END_TIME AS orig_end, l.ORD_END_TIME AS new_end,
    l.CONFIRM_DATE, o.ORD_STATUS,
    CASE WHEN f.ORD_END_TIME<>l.ORD_END_TIME AND l.ORD_END_TIME<f.ORD_END_TIME THEN 1 ELSE 0 END AS deadline_forward,
    CASE WHEN f.ORD_END_TIME<>l.ORD_END_TIME AND l.ORD_END_TIME>f.ORD_END_TIME THEN 1 ELSE 0 END AS deadline_delay,
    CASE WHEN f.ORD_QTY<>l.ORD_QTY THEN 1 ELSE 0 END AS qty_change
FROM (SELECT *, ROW_NUMBER() OVER(PARTITION BY FACTORY_CODE, ORDER_NO ORDER BY IF_SQ ASC) AS rn
      FROM IWIPORDSTS WHERE SO_NO IS NOT NULL AND SO_NO<>'') f
JOIN (SELECT *, ROW_NUMBER() OVER(PARTITION BY FACTORY_CODE, ORDER_NO ORDER BY IF_SQ DESC) AS rn
      FROM IWIPORDSTS WHERE SO_NO IS NOT NULL AND SO_NO<>'') l
    ON f.FACTORY_CODE=l.FACTORY_CODE AND f.ORDER_NO=l.ORDER_NO
LEFT JOIN MWIPORDSTS o ON l.FACTORY_CODE=o.FACTORY_CODE AND l.ORDER_NO=o.ORDER_NO
WHERE f.rn=1 AND l.rn=1 AND l.CONFIRM_DATE>='20260101'
  AND (f.ORD_QTY<>l.ORD_QTY OR f.ORD_END_TIME<>l.ORD_END_TIME)
ORDER BY l.CONFIRM_DATE DESC
```

## 10. 2026 생산 KPI 목표
| KPI | 목표 | 측정방법 |
|-----|------|---------|
| 생산계획 준수율 | 95% | MES 주간 |
| Lot 불량률 | ↓ | MES/QMS 월간 |
| 스크랩율 | 15%↓ | MES 월간 |
| UPH 개선율 | 10%↑ | MES 월간 |
| OEE (제조2) | 75% | MES 월간 |
| 납기준수율 (생산1) | 95% | ERP 월간 |
| 긴급생산 비율 | ↓ | 생산지시서 주간 |
