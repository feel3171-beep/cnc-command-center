from flask import Flask, render_template_string, jsonify, request
import pymssql, json
from datetime import datetime, timedelta

app = Flask(__name__)
DB = dict(server='192.161.0.16', user='mestmp', password='cncmgr123!', database='MES', charset='utf8')

def query(sql):
    conn = pymssql.connect(**DB)
    cur = conn.cursor(as_dict=True)
    cur.execute(sql)
    rows = cur.fetchall()
    conn.close()
    for r in rows:
        for k, v in r.items():
            if isinstance(v, datetime): r[k] = v.strftime('%Y-%m-%d %H:%M')
            elif v is None: r[k] = ''
    return rows

FACTORY = {'1100':'퍼플카운티','1200':'그린카운티','1300':'3공장'}

@app.route('/')
def index():
    return render_template_string(HTML)

# ── 일별 현황 (오늘 기준) ──
@app.route('/api/today_production')
def today_production():
    today = datetime.now().strftime('%Y-%m-%d')
    rows = query(f"""
        SELECT l.FACTORY_CODE, l.LINE_TYPE, l.LINE_CODE, l.LINE_DESC,
            SUM(h.QTY) AS qty, COUNT(DISTINCT h.LOT_ID) AS lot_cnt,
            MIN(h.TRAN_TIME) AS first_time, MAX(h.TRAN_TIME) AS last_time
        FROM MWIPLOTHIS h
        INNER JOIN MWIPLINDEF l ON h.FACTORY_CODE=l.FACTORY_CODE AND h.LINE_CODE=l.LINE_CODE
        WHERE h.TRAN_CODE='CV' AND CONVERT(VARCHAR, h.TRAN_TIME, 23)='{today}'
        GROUP BY l.FACTORY_CODE, l.LINE_TYPE, l.LINE_CODE, l.LINE_DESC
        ORDER BY l.FACTORY_CODE, l.LINE_TYPE, SUM(h.QTY) DESC
    """)
    for r in rows: r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
    return jsonify(rows)

@app.route('/api/today_hourly')
def today_hourly():
    today = datetime.now().strftime('%Y-%m-%d')
    rows = query(f"""
        SELECT l.FACTORY_CODE, l.LINE_TYPE,
            DATEPART(HOUR, h.TRAN_TIME) AS hr,
            SUM(h.QTY) AS qty
        FROM MWIPLOTHIS h
        INNER JOIN MWIPLINDEF l ON h.FACTORY_CODE=l.FACTORY_CODE AND h.LINE_CODE=l.LINE_CODE
        WHERE h.TRAN_CODE='CV' AND CONVERT(VARCHAR, h.TRAN_TIME, 23)='{today}'
        GROUP BY l.FACTORY_CODE, l.LINE_TYPE, DATEPART(HOUR, h.TRAN_TIME)
        ORDER BY DATEPART(HOUR, h.TRAN_TIME)
    """)
    for r in rows: r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
    return jsonify(rows)

@app.route('/api/today_cumulative')
def today_cumulative():
    rows = query("""
        SELECT l.FACTORY_CODE, l.LINE_TYPE,
            SUM(h.QTY) AS month_qty,
            COUNT(DISTINCT CONVERT(VARCHAR, h.TRAN_TIME, 112)) AS work_days
        FROM MWIPLOTHIS h
        INNER JOIN MWIPLINDEF l ON h.FACTORY_CODE=l.FACTORY_CODE AND h.LINE_CODE=l.LINE_CODE
        WHERE h.TRAN_CODE='CV' AND h.TRAN_TIME >= DATEADD(DAY, 1-DAY(GETDATE()), CAST(GETDATE() AS DATE))
            AND h.TRAN_TIME < DATEADD(DAY, 1, CAST(GETDATE() AS DATE))
        GROUP BY l.FACTORY_CODE, l.LINE_TYPE
        ORDER BY l.FACTORY_CODE, l.LINE_TYPE
    """)
    for r in rows: r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
    return jsonify(rows)

# ── 일별 추이 ──
@app.route('/api/daily_trend')
def daily_trend():
    rows = query("""
        SELECT CONVERT(VARCHAR, h.TRAN_TIME, 23) AS day,
            l.FACTORY_CODE, l.LINE_TYPE,
            SUM(h.QTY) AS qty, COUNT(DISTINCT h.LOT_ID) AS lot_cnt
        FROM MWIPLOTHIS h
        INNER JOIN MWIPLINDEF l ON h.FACTORY_CODE=l.FACTORY_CODE AND h.LINE_CODE=l.LINE_CODE
        WHERE h.TRAN_CODE='CV'
            AND h.TRAN_TIME >= DATEADD(DAY, 1-DAY(GETDATE()), CAST(GETDATE() AS DATE))
            AND h.TRAN_TIME < DATEADD(DAY, 1, CAST(GETDATE() AS DATE))
        GROUP BY CONVERT(VARCHAR, h.TRAN_TIME, 23), l.FACTORY_CODE, l.LINE_TYPE
        ORDER BY CONVERT(VARCHAR, h.TRAN_TIME, 23)
    """)
    for r in rows: r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
    return jsonify(rows)

@app.route('/api/daily_by_line')
def daily_by_line():
    rows = query("""
        SELECT TOP 500 CONVERT(VARCHAR, h.TRAN_TIME, 23) AS day,
            l.FACTORY_CODE, l.LINE_CODE, l.LINE_DESC, l.LINE_TYPE,
            SUM(h.QTY) AS qty
        FROM MWIPLOTHIS h
        INNER JOIN MWIPLINDEF l ON h.FACTORY_CODE=l.FACTORY_CODE AND h.LINE_CODE=l.LINE_CODE
        WHERE h.TRAN_CODE='CV'
            AND h.TRAN_TIME >= DATEADD(DAY, 1-DAY(GETDATE()), CAST(GETDATE() AS DATE))
            AND h.TRAN_TIME < DATEADD(DAY, 1, CAST(GETDATE() AS DATE))
        GROUP BY CONVERT(VARCHAR, h.TRAN_TIME, 23), l.FACTORY_CODE, l.LINE_CODE, l.LINE_DESC, l.LINE_TYPE
        ORDER BY CONVERT(VARCHAR, h.TRAN_TIME, 23), l.FACTORY_CODE, l.LINE_CODE
    """)
    for r in rows: r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
    return jsonify(rows)

# ── 주별 분석 ──
@app.route('/api/weekly_trend')
def weekly_trend():
    rows = query("""
        SELECT DATEPART(ISO_WEEK, h.TRAN_TIME) AS wk,
            MIN(CONVERT(VARCHAR, h.TRAN_TIME, 23)) AS wk_start,
            l.FACTORY_CODE, l.LINE_TYPE,
            SUM(h.QTY) AS qty, COUNT(DISTINCT h.LOT_ID) AS lot_cnt,
            COUNT(DISTINCT CONVERT(VARCHAR, h.TRAN_TIME, 112)) AS work_days
        FROM MWIPLOTHIS h
        INNER JOIN MWIPLINDEF l ON h.FACTORY_CODE=l.FACTORY_CODE AND h.LINE_CODE=l.LINE_CODE
        WHERE h.TRAN_CODE='CV' AND h.TRAN_TIME >= '2026-01-01'
        GROUP BY DATEPART(ISO_WEEK, h.TRAN_TIME), l.FACTORY_CODE, l.LINE_TYPE
        ORDER BY DATEPART(ISO_WEEK, h.TRAN_TIME), l.FACTORY_CODE
    """)
    for r in rows: r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
    return jsonify(rows)

# ── 월별 분석 ──
@app.route('/api/monthly_trend')
def monthly_trend():
    rows = query("""
        SELECT CONVERT(VARCHAR(7), h.TRAN_TIME, 120) AS month,
            l.FACTORY_CODE, l.LINE_TYPE,
            SUM(h.QTY) AS qty, COUNT(DISTINCT h.LOT_ID) AS lot_cnt,
            COUNT(DISTINCT CONVERT(VARCHAR, h.TRAN_TIME, 112)) AS work_days
        FROM MWIPLOTHIS h
        INNER JOIN MWIPLINDEF l ON h.FACTORY_CODE=l.FACTORY_CODE AND h.LINE_CODE=l.LINE_CODE
        WHERE h.TRAN_CODE='CV' AND h.TRAN_TIME >= '2025-01-01'
        GROUP BY CONVERT(VARCHAR(7), h.TRAN_TIME, 120), l.FACTORY_CODE, l.LINE_TYPE
        ORDER BY CONVERT(VARCHAR(7), h.TRAN_TIME, 120), l.FACTORY_CODE
    """)
    for r in rows: r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
    return jsonify(rows)

# ── 이슈현황 ──
@app.route('/api/nonwork_today')
def nonwork_today():
    rows = query("""
        SELECT TOP 30 n.FACTORY_CODE, n.LINE_CODE, n.NONWORK_CODE,
            l.LINE_DESC, l.LINE_TYPE,
            COUNT(*) AS cnt, SUM(n.NONWORK_SECOND) AS total_sec,
            MAX(n.NONWORK_DATE) AS last_date
        FROM MWIPNWKSTS n
        INNER JOIN MWIPLINDEF l ON n.FACTORY_CODE=l.FACTORY_CODE AND n.LINE_CODE=l.LINE_CODE
        WHERE n.NONWORK_DATE >= CONVERT(VARCHAR, GETDATE(), 112)
        GROUP BY n.FACTORY_CODE, n.LINE_CODE, n.NONWORK_CODE, l.LINE_DESC, l.LINE_TYPE
        ORDER BY SUM(n.NONWORK_SECOND) DESC
    """)
    nwk = {'E101':'작업준비','E102':'품목교체(호수)','E103':'품목교체(제품)',
           'E201':'충전부고장','E202':'캡핑부고장','E203':'컨베이어고장',
           'E206':'순간정비','E301':'자재불량대기','E303':'자재불출지연',
           'E401':'QC확인대기','E403':'내용물불량대기','E501':'벌크보충',
           'E505':'(미등록)','E506':'(미등록)','E601':'청소정리'}
    for r in rows:
        r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
        r['code_name'] = nwk.get(r['NONWORK_CODE'], r['NONWORK_CODE'])
        r['hours'] = round(int(r['total_sec']) / 3600, 1)
        r['is_equip'] = r['NONWORK_CODE'].startswith('E2')
        r['is_material'] = r['NONWORK_CODE'].startswith('E3')
    return jsonify(rows)

@app.route('/api/nonwork_monthly')
def nonwork_monthly():
    rows = query("""
        SELECT TOP 30 n.FACTORY_CODE, n.NONWORK_CODE,
            COUNT(*) AS cnt, SUM(n.NONWORK_SECOND) AS total_sec,
            COUNT(DISTINCT n.LINE_CODE) AS line_cnt
        FROM MWIPNWKSTS n
        WHERE n.NONWORK_DATE >= CONVERT(VARCHAR(6), GETDATE(), 112) + '01'
        GROUP BY n.FACTORY_CODE, n.NONWORK_CODE
        ORDER BY SUM(n.NONWORK_SECOND) DESC
    """)
    nwk = {'E101':'작업준비','E102':'품목교체(호수)','E103':'품목교체(제품)',
           'E201':'충전부고장','E202':'캡핑부고장','E203':'컨베이어고장',
           'E206':'순간정비','E301':'자재불량대기','E303':'자재불출지연',
           'E401':'QC확인대기','E403':'내용물불량대기','E501':'벌크보충',
           'E505':'(미등록)','E506':'(미등록)','E601':'청소정리'}
    for r in rows:
        r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
        r['code_name'] = nwk.get(r['NONWORK_CODE'], r['NONWORK_CODE'])
        r['hours'] = round(int(r['total_sec']) / 3600, 1)
    return jsonify(rows)

@app.route('/api/low_productivity')
def low_productivity():
    rows = query("""
        SELECT l.FACTORY_CODE, l.LINE_CODE, l.LINE_DESC, l.LINE_TYPE,
            SUM(h.QTY) AS total_qty,
            COUNT(DISTINCT CONVERT(VARCHAR, h.TRAN_TIME, 112)) AS work_days,
            CASE WHEN COUNT(DISTINCT CONVERT(VARCHAR, h.TRAN_TIME, 112)) > 0
                THEN SUM(h.QTY) / COUNT(DISTINCT CONVERT(VARCHAR, h.TRAN_TIME, 112))
                ELSE 0 END AS daily_avg
        FROM MWIPLOTHIS h
        INNER JOIN MWIPLINDEF l ON h.FACTORY_CODE=l.FACTORY_CODE AND h.LINE_CODE=l.LINE_CODE
        WHERE h.TRAN_CODE='CV'
            AND h.TRAN_TIME >= DATEADD(DAY, 1-DAY(GETDATE()), CAST(GETDATE() AS DATE))
            AND h.TRAN_TIME < DATEADD(DAY, 1, CAST(GETDATE() AS DATE))
        GROUP BY l.FACTORY_CODE, l.LINE_CODE, l.LINE_DESC, l.LINE_TYPE
        HAVING COUNT(DISTINCT CONVERT(VARCHAR, h.TRAN_TIME, 112)) >= 3
        ORDER BY CASE WHEN COUNT(DISTINCT CONVERT(VARCHAR, h.TRAN_TIME, 112)) > 0
            THEN SUM(h.QTY) / COUNT(DISTINCT CONVERT(VARCHAR, h.TRAN_TIME, 112))
            ELSE 0 END ASC
    """)
    for r in rows:
        r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
        r['daily_avg'] = round(float(r['daily_avg']))
    return jsonify(rows)

# ── 계획 변경 감지 ──
@app.route('/api/plan_changes')
def plan_changes():
    rows = query("""
        SELECT
            f.FACTORY_CODE, f.ORDER_NO, f.SO_NO, l.CUSTOMER_CODE,
            v.VENDOR_DESC AS cust_name,
            f.ORD_QTY AS orig_qty, l.ORD_QTY AS new_qty,
            f.ORD_END_TIME AS orig_end, l.ORD_END_TIME AS new_end,
            f.ORD_START_TIME AS orig_start, l.ORD_START_TIME AS new_start,
            l.CONFIRM_DATE,
            o.ORD_STATUS,
            CASE WHEN f.ORD_END_TIME<>l.ORD_END_TIME AND l.ORD_END_TIME<f.ORD_END_TIME THEN 1 ELSE 0 END AS deadline_forward,
            CASE WHEN f.ORD_END_TIME<>l.ORD_END_TIME AND l.ORD_END_TIME>f.ORD_END_TIME THEN 1 ELSE 0 END AS deadline_delay,
            CASE WHEN f.ORD_QTY<>l.ORD_QTY AND l.ORD_QTY>f.ORD_QTY THEN 1 ELSE 0 END AS qty_increase,
            CASE WHEN f.ORD_QTY<>l.ORD_QTY AND l.ORD_QTY<f.ORD_QTY THEN 1 ELSE 0 END AS qty_decrease,
            CASE WHEN f.ORD_START_TIME<>l.ORD_START_TIME THEN 1 ELSE 0 END AS start_change
        FROM (SELECT *, ROW_NUMBER() OVER(PARTITION BY FACTORY_CODE, ORDER_NO ORDER BY IF_SQ ASC) AS rn
              FROM IWIPORDSTS WHERE SO_NO IS NOT NULL AND SO_NO<>'') f
        JOIN (SELECT *, ROW_NUMBER() OVER(PARTITION BY FACTORY_CODE, ORDER_NO ORDER BY IF_SQ DESC) AS rn
              FROM IWIPORDSTS WHERE SO_NO IS NOT NULL AND SO_NO<>'') l
            ON f.FACTORY_CODE=l.FACTORY_CODE AND f.ORDER_NO=l.ORDER_NO
        LEFT JOIN MWIPORDSTS o ON l.FACTORY_CODE=o.FACTORY_CODE AND l.ORDER_NO=o.ORDER_NO
        LEFT JOIN MWIPVENDEF v ON l.CUSTOMER_CODE=v.VENDOR_CODE AND l.FACTORY_CODE=v.FACTORY_CODE
        WHERE f.rn=1 AND l.rn=1
            AND l.CONFIRM_DATE>='20260101'
            AND (f.ORD_QTY<>l.ORD_QTY OR f.ORD_END_TIME<>l.ORD_END_TIME OR f.ORD_START_TIME<>l.ORD_START_TIME)
        ORDER BY l.CONFIRM_DATE DESC
    """)
    return jsonify(rows)

@app.route('/api/urgent_orders')
def urgent_orders():
    rows = query("""
        SELECT i.FACTORY_CODE, i.ORDER_NO, i.SO_NO, i.CUSTOMER_CODE,
            v.VENDOR_DESC AS cust_name,
            i.CONFIRM_DATE, i.ORD_END_TIME, i.ORD_START_TIME, i.ORD_QTY,
            o.ORD_STATUS,
            DATEDIFF(DAY, i.CONFIRM_DATE, i.ORD_END_TIME) AS notice_days
        FROM (SELECT *, ROW_NUMBER() OVER(PARTITION BY FACTORY_CODE, ORDER_NO ORDER BY IF_SQ DESC) AS _rn
              FROM IWIPORDSTS WHERE SO_NO IS NOT NULL AND SO_NO<>'') i
        LEFT JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        LEFT JOIN MWIPVENDEF v ON i.CUSTOMER_CODE=v.VENDOR_CODE AND i.FACTORY_CODE=v.FACTORY_CODE
        WHERE i._rn=1 AND i.CONFIRM_DATE>='20260101'
            AND DATEDIFF(DAY, i.CONFIRM_DATE, i.ORD_END_TIME)<=3
            AND o.ORD_STATUS IN ('PLAN','WAIT','CONFIRM','PROCESS')
        ORDER BY i.CONFIRM_DATE DESC
    """)
    return jsonify(rows)

# ── HTML ──
HTML = r'''<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>MES 생산 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI','맑은 고딕',sans-serif;background:#0f172a;color:#e2e8f0}
.header{background:linear-gradient(135deg,#1e293b,#334155);padding:16px 24px;display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #22c55e}
.header h1{font-size:22px;color:#4ade80}
.header .sub{color:#94a3b8;font-size:13px;margin-left:12px}
.header .time{color:#94a3b8;font-size:13px}
.refresh-btn{background:#22c55e;color:#000;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600}
.tabs{display:flex;background:#1e293b;padding:0 24px;gap:4px;border-bottom:1px solid #334155}
.tab{padding:12px 20px;cursor:pointer;color:#94a3b8;border-bottom:3px solid transparent;font-size:14px;font-weight:500;transition:all .2s}
.tab:hover{color:#e2e8f0}.tab.active{color:#4ade80;border-bottom-color:#22c55e}
.content{padding:20px 24px;display:none}.content.active{display:block}
.grid{display:grid;gap:16px}.grid-3{grid-template-columns:repeat(3,1fr)}.grid-2{grid-template-columns:repeat(2,1fr)}
.card{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155}
.card h3{font-size:14px;color:#94a3b8;margin-bottom:12px;font-weight:500}
.kpi{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap}
.kpi-box{flex:1;min-width:140px;background:#1e293b;border-radius:12px;padding:16px;text-align:center;border:1px solid #334155;cursor:pointer;transition:all .2s}
.kpi-box:hover{background:#334155;transform:translateY(-2px)}
.kpi-box .label{font-size:11px;color:#94a3b8;margin-bottom:4px}
.kpi-box .value{font-size:26px;font-weight:700}
.kpi-box .sub{font-size:11px;color:#64748b;margin-top:4px}
.kpi-modal-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.7);z-index:1000;justify-content:center;align-items:flex-start;padding:40px 0}
.kpi-modal{background:#0f172a;border:1px solid #334155;border-radius:16px;padding:24px;max-width:1000px;width:90%;max-height:85vh;overflow-y:auto;position:relative}
.kpi-modal h3{color:#e2e8f0;margin:0 0 16px;font-size:18px}
.kpi-modal h4{color:#94a3b8;margin:20px 0 8px;font-size:14px}
.kpi-modal .close-btn{position:absolute;top:12px;right:16px;color:#94a3b8;font-size:28px;cursor:pointer;line-height:1;background:none;border:none}
.kpi-modal .close-btn:hover{color:#e2e8f0}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#334155;color:#94a3b8;padding:10px 12px;text-align:left;font-weight:500;position:sticky;top:0}
td{padding:8px 12px;border-bottom:1px solid #1e293b}
tr:hover td{background:#334155}
.num{text-align:right;font-variant-numeric:tabular-nums}
.badge{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;display:inline-block}
.badge-bulk{background:#312e81;color:#a78bfa}.badge-filling{background:#1e3a5f;color:#60a5fa}
.badge-tablet{background:#831843;color:#f472b6}.badge-packing{background:#14532d;color:#34d399}
.badge-bonding{background:#78350f;color:#fb923c}
.badge-equip{background:#991b1b;color:#fca5a5}.badge-material{background:#92400e;color:#fbbf24}
.chart-container{height:300px;position:relative}
.scroll-table{max-height:500px;overflow-y:auto}
.pbar{background:#334155;border-radius:4px;height:18px;overflow:hidden;position:relative}
.pbar-fill{height:100%;border-radius:4px;transition:width .5s}
.pbar-text{position:absolute;top:0;left:0;right:0;text-align:center;font-size:10px;line-height:18px;color:#fff;font-weight:600}
.alert-row{border-left:3px solid #ef4444}
@media(max-width:1024px){.grid-3{grid-template-columns:1fr}.grid-2{grid-template-columns:1fr}.kpi{flex-wrap:wrap}}
</style></head><body>

<div class="header">
    <div style="display:flex;align-items:center"><h1>MES 생산 대시보드</h1><span class="sub">실시간 생산현황 모니터링</span></div>
    <div style="display:flex;align-items:center;gap:16px">
        <span class="time" id="updateTime"></span>
        <button class="refresh-btn" onclick="loadAll()">새로고침</button>
    </div>
</div>

<div class="tabs">
    <div class="tab active" onclick="switchTab(0)">일별 현황</div>
    <div class="tab" onclick="switchTab(1)">일별 추이</div>
    <div class="tab" onclick="switchTab(2)">주별 분석</div>
    <div class="tab" onclick="switchTab(3)">월별 분석</div>
    <div class="tab" onclick="switchTab(4)" style="color:#f87171">이슈 현황</div>
    <div class="tab" onclick="switchTab(5)" style="color:#fbbf24">계획 변경 <span id="changeBadge" style="background:#ef4444;color:#fff;border-radius:10px;padding:1px 7px;font-size:11px;margin-left:4px;display:none">0</span></div>
</div>

<!-- Tab 0: 일별 현황 -->
<div class="content active" id="tab0">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="color:#a78bfa;font-size:12px;font-weight:600">생산</span><div style="flex:1;height:1px;background:#a78bfa33"></div></div>
    <div class="kpi" id="todayKpiManu"></div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="color:#34d399;font-size:12px;font-weight:600">포장</span><div style="flex:1;height:1px;background:#34d39933"></div></div>
    <div class="kpi" id="todayKpiPack"></div>
    <div class="grid grid-2" style="margin-top:12px">
        <div class="card"><h3>시간대별 생산추이 (오늘)</h3><div class="chart-container"><canvas id="hourlyChart"></canvas></div></div>
        <div class="card"><h3>공장 x 공정별 누계 (이번달)</h3><div class="chart-container"><canvas id="cumulChart"></canvas></div></div>
    </div>
    <div class="card" style="margin-top:16px"><h3>오늘 라인별 생산 상세 (생산+포장)</h3>
        <div class="scroll-table" id="todayTable"></div>
    </div>
    <div style="display:flex;align-items:center;gap:8px;margin-top:24px;margin-bottom:4px"><span style="color:#f59e0b;font-size:12px;font-weight:600">벌크(내용물)</span><div style="flex:1;height:1px;background:#f59e0b33"></div></div>
    <div class="kpi" id="todayKpiBulk"></div>
    <div class="card" style="margin-top:12px"><h3>오늘 벌크 라인별 상세</h3>
        <div class="scroll-table" id="todayBulkTable"></div>
    </div>
</div>

<!-- Tab 1: 일별 추이 -->
<div class="content" id="tab1">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="color:#a78bfa;font-size:12px;font-weight:600">생산</span><div style="flex:1;height:1px;background:#a78bfa33"></div></div>
    <div class="kpi" id="dailyKpiManu"></div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="color:#34d399;font-size:12px;font-weight:600">포장</span><div style="flex:1;height:1px;background:#34d39933"></div></div>
    <div class="kpi" id="dailyKpiPack"></div>
    <div class="grid grid-2" style="margin-top:12px">
        <div class="card"><h3>일별 공장별 생산추이</h3><div class="chart-container"><canvas id="dailyFactChart"></canvas></div></div>
        <div class="card"><h3>일별 공정별 생산추이</h3><div class="chart-container"><canvas id="dailyProcChart"></canvas></div></div>
    </div>
    <div class="card" style="margin-top:16px"><h3>일별 라인별 상세</h3>
        <div class="scroll-table" style="max-height:600px" id="dailyLineTable"></div>
    </div>
</div>

<!-- Tab 2: 주별 분석 -->
<div class="content" id="tab2">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="color:#a78bfa;font-size:12px;font-weight:600">생산</span><div style="flex:1;height:1px;background:#a78bfa33"></div></div>
    <div class="kpi" id="weeklyKpiManu"></div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="color:#34d399;font-size:12px;font-weight:600">포장</span><div style="flex:1;height:1px;background:#34d39933"></div></div>
    <div class="kpi" id="weeklyKpiPack"></div>
    <div class="grid grid-2" style="margin-top:12px">
        <div class="card"><h3>주차별 공장별 생산추이 (2026)</h3><div class="chart-container" style="height:350px"><canvas id="weeklyFactChart"></canvas></div></div>
        <div class="card"><h3>주차별 공정별 생산추이</h3><div class="chart-container" style="height:350px"><canvas id="weeklyProcChart"></canvas></div></div>
    </div>
    <div class="card" style="margin-top:16px"><h3>주차별 상세</h3>
        <div class="scroll-table" id="weeklyTable"></div>
    </div>
</div>

<!-- Tab 3: 월별 분석 -->
<div class="content" id="tab3">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="color:#a78bfa;font-size:12px;font-weight:600">생산</span><div style="flex:1;height:1px;background:#a78bfa33"></div></div>
    <div class="kpi" id="monthlyKpiManu"></div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="color:#34d399;font-size:12px;font-weight:600">포장</span><div style="flex:1;height:1px;background:#34d39933"></div></div>
    <div class="kpi" id="monthlyKpiPack"></div>
    <div class="grid grid-2" style="margin-top:12px">
        <div class="card"><h3>월별 공장별 생산추이</h3><div class="chart-container" style="height:350px"><canvas id="monthlyFactChart"></canvas></div></div>
        <div class="card"><h3>월별 공정별 생산추이</h3><div class="chart-container" style="height:350px"><canvas id="monthlyProcChart"></canvas></div></div>
    </div>
    <div class="card" style="margin-top:16px"><h3>월별 상세</h3>
        <div class="scroll-table" id="monthlyTable"></div>
    </div>
</div>

<!-- Tab 4: 이슈 현황 -->
<div class="content" id="tab4">
    <div class="kpi" id="issueKpi"></div>
    <div class="grid grid-2" style="margin-top:12px">
        <div class="card"><h3>오늘 비가동 현황</h3>
            <div class="scroll-table" id="nwkTodayTable"></div>
        </div>
        <div class="card"><h3>이번달 비가동 누적</h3>
            <div class="chart-container"><canvas id="nwkMonthChart"></canvas></div>
        </div>
    </div>
    <div class="card" style="margin-top:16px"><h3>생산성 낮은 라인 (이번달 일평균 기준)</h3>
        <div class="scroll-table" id="lowProdTable"></div>
    </div>
</div>

<!-- Tab 5: 계획 변경 -->
<div class="content" id="tab5">
    <div class="kpi" id="changeKpi"></div>
    <div style="margin-bottom:12px">
        <button class="phase-btn active" onclick="filterChange('ALL')" id="chgAll" style="font-size:13px;padding:7px 16px">전체</button>
        <button class="phase-btn" onclick="filterChange('DEADLINE')" id="chgDeadline" style="font-size:13px;padding:7px 16px">납기변경</button>
        <button class="phase-btn" onclick="filterChange('QTY')" id="chgQty" style="font-size:13px;padding:7px 16px">수량변경</button>
        <button class="phase-btn" onclick="filterChange('START')" id="chgStart" style="font-size:13px;padding:7px 16px">착수일변경</button>
        <button class="phase-btn" onclick="filterChange('URGENT')" id="chgUrgent" style="font-size:13px;padding:7px 16px;color:#ef4444">긴급수주</button>
    </div>
    <div class="card"><h3>계획 변경 내역</h3>
        <div class="scroll-table" style="max-height:600px" id="changeTable"></div>
    </div>
    <div class="grid grid-2" style="margin-top:16px">
        <div class="card"><h3>거래처별 변경 빈도</h3>
            <div class="chart-container" style="height:350px"><canvas id="changeCustChart"></canvas></div>
        </div>
        <div class="card"><h3>변경 유형 분포</h3>
            <div class="chart-container" style="height:350px"><canvas id="changeTypeChart"></canvas></div>
        </div>
    </div>
</div>

<script>
const FC={'1100':'퍼플카운티','1200':'그린카운티','1300':'3공장'};
const FCOLORS={퍼플카운티:'#a78bfa',그린카운티:'#34d399','3공장':'#fb923c'};
const PCOLORS={BULK:'#a78bfa',FILLING:'#60a5fa',TABLET:'#f472b6',PACKING:'#34d399',BONDING:'#fb923c'};
const PNAMES={BULK:'벌크',FILLING:'충전',TABLET:'타정',PACKING:'포장',BONDING:'본딩'};
const IS_PROD=t=>t==='FILLING'||t==='BONDING';
const IS_PACK=t=>t==='PACKING';
const IS_BULK=t=>t==='BULK';
let charts={};
let _todayProd=[],_dailyTrend=[],_weeklyData=[],_monthlyData=[];
let _nwkToday=[],_lowProd=[];

function switchTab(n){
    document.querySelectorAll('.tab').forEach((t,i)=>t.classList.toggle('active',i===n));
    document.querySelectorAll('.content').forEach((c,i)=>c.classList.toggle('active',i===n));
}
function fmt(n){return n?Number(n).toLocaleString():'0'}
function typeBadge(t){return `<span class="badge badge-${(t||'').toLowerCase()}">${PNAMES[t]||t}</span>`}

async function loadAll(){
    document.getElementById('updateTime').textContent='갱신: '+new Date().toLocaleString('ko-KR');
    await Promise.all([loadToday(),loadDaily(),loadWeekly(),loadMonthly(),loadIssues(),loadPlanChanges()]);
}

// ── Tab 0: 일별 현황 ──
async function loadToday(){
    let [prod,hourly,cumul]=await Promise.all([
        (await fetch('/api/today_production')).json(),
        (await fetch('/api/today_hourly')).json(),
        (await fetch('/api/today_cumulative')).json()
    ]);

    _todayProd=prod;
    // KPI - 생산(충전+본딩) / 포장 / 벌크(별도)
    let prodByF={},packByF={},bulkByF={},prodTotal=0,packTotal=0,bulkTotal=0;
    let fillByF={},bondByF={};
    prod.forEach(r=>{
        let q=Number(r.qty),f=r.factory_name;
        if(IS_PROD(r.LINE_TYPE)){prodTotal+=q;prodByF[f]=(prodByF[f]||0)+q;
            if(r.LINE_TYPE==='FILLING'){fillByF[f]=(fillByF[f]||0)+q}
            else{bondByF[f]=(bondByF[f]||0)+q}
        }
        else if(IS_PACK(r.LINE_TYPE)){packTotal+=q;packByF[f]=(packByF[f]||0)+q}
        else if(IS_BULK(r.LINE_TYPE)){bulkTotal+=q;bulkByF[f]=(bulkByF[f]||0)+q}
    });
    // 생산 KPI (전체 + 공장별)
    let mhtml=`<div class="kpi-box" style="border-color:#a78bfa" onclick="showProdDetail('today','manu')"><div class="label">오늘 생산 합계 (충전+본딩)</div><div class="value" style="color:#a78bfa">${fmt(prodTotal)}</div></div>`;
    ['퍼플카운티','그린카운티','3공장'].forEach(f=>{
        let q=prodByF[f]||0;if(q===0&&!prodByF[f])return;
        let fill=fillByF[f]||0,bond=bondByF[f]||0;
        let sub=bond>0?`충전 ${fmt(fill)} / 본딩 ${fmt(bond)}`:`충전 ${fmt(fill)}`;
        mhtml+=`<div class="kpi-box" style="border-color:${FCOLORS[f]||'#60a5fa'}" onclick="showProdDetail('today','factory_manu','${f}')"><div class="label">${f}</div><div class="value" style="color:${FCOLORS[f]||'#60a5fa'}">${fmt(q)}</div><div class="sub">${sub}</div></div>`;
    });
    // 포장 KPI
    let phtml=`<div class="kpi-box" style="border-color:#34d399" onclick="showProdDetail('today','pack')"><div class="label">오늘 포장 합계</div><div class="value" style="color:#34d399">${fmt(packTotal)}</div></div>`;
    ['퍼플카운티','그린카운티','3공장'].forEach(f=>{
        let q=packByF[f]||0;if(q===0)return;
        phtml+=`<div class="kpi-box" style="border-color:${FCOLORS[f]||'#60a5fa'}" onclick="showProdDetail('today','factory_pack','${f}')"><div class="label">${f}</div><div class="value" style="color:${FCOLORS[f]||'#60a5fa'}">${fmt(q)}</div></div>`;
    });
    document.getElementById('todayKpiManu').innerHTML=mhtml;
    document.getElementById('todayKpiPack').innerHTML=phtml;
    // 벌크 KPI
    let bhtml=`<div class="kpi-box" style="border-color:#f59e0b" onclick="showProdDetail('today','bulk')"><div class="label">오늘 벌크(내용물) 합계</div><div class="value" style="color:#f59e0b">${fmt(bulkTotal)}</div></div>`;
    ['퍼플카운티','그린카운티','3공장'].forEach(f=>{
        let q=bulkByF[f]||0;if(q===0)return;
        bhtml+=`<div class="kpi-box" style="border-color:${FCOLORS[f]||'#60a5fa'}"><div class="label">${f}</div><div class="value" style="color:${FCOLORS[f]||'#60a5fa'}">${fmt(q)}</div></div>`;
    });
    document.getElementById('todayKpiBulk').innerHTML=bhtml;

    // Hourly chart (벌크 완전 제외)
    let hourlyNoBulk=hourly.filter(r=>r.LINE_TYPE!=='BULK');
    let hrs=[...new Set(hourlyNoBulk.map(r=>r.hr))].sort((a,b)=>a-b);
    let hrByType={};
    hourlyNoBulk.forEach(r=>{
        if(!hrByType[r.LINE_TYPE])hrByType[r.LINE_TYPE]={};
        hrByType[r.LINE_TYPE][r.hr]=(hrByType[r.LINE_TYPE][r.hr]||0)+Number(r.qty);
    });
    if(charts.hourly)charts.hourly.destroy();
    charts.hourly=new Chart(document.getElementById('hourlyChart'),{type:'bar',
        data:{labels:hrs.map(h=>h+':00'),
            datasets:Object.entries(hrByType).map(([t,v])=>({label:PNAMES[t]||t,data:hrs.map(h=>v[h]||0),backgroundColor:PCOLORS[t]||'#64748b'}))},
        options:{responsive:true,maintainAspectRatio:false,
            scales:{y:{stacked:true,ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}},x:{stacked:true,ticks:{color:'#94a3b8'},grid:{color:'#334155'}}},
            plugins:{legend:{labels:{color:'#e2e8f0'}}}}
    });

    // Cumulative chart (벌크 완전 제외)
    let cumulNoBulk=cumul.filter(r=>r.LINE_TYPE!=='BULK');
    let cFactories=[...new Set(cumulNoBulk.map(r=>r.factory_name))];
    let cTypes=[...new Set(cumulNoBulk.map(r=>r.LINE_TYPE))];
    if(charts.cumul)charts.cumul.destroy();
    charts.cumul=new Chart(document.getElementById('cumulChart'),{type:'bar',
        data:{labels:cFactories,
            datasets:cTypes.map(t=>({label:PNAMES[t]||t,
                data:cFactories.map(f=>{let found=cumulNoBulk.find(r=>r.factory_name===f&&r.LINE_TYPE===t);return found?Number(found.month_qty):0}),
                backgroundColor:PCOLORS[t]||'#64748b'}))},
        options:{responsive:true,maintainAspectRatio:false,
            scales:{y:{stacked:true,ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}},x:{stacked:true,ticks:{color:'#94a3b8'},grid:{color:'#334155'}}},
            plugins:{legend:{labels:{color:'#e2e8f0'}}}}
    });

    // Table (생산+포장 — 벌크 제외)
    let tbl=`<table><thead><tr><th>공장</th><th>공정</th><th>라인</th><th>라인명</th><th class="num">생산수량</th><th class="num">LOT</th><th>최초생산</th><th>최근생산</th></tr></thead><tbody>`;
    prod.filter(r=>!IS_BULK(r.LINE_TYPE)).forEach(r=>{
        tbl+=`<tr><td>${r.factory_name}</td><td>${typeBadge(r.LINE_TYPE)}</td><td>${r.LINE_CODE}</td><td>${r.LINE_DESC||''}</td>`;
        tbl+=`<td class="num">${fmt(r.qty)}</td><td class="num">${r.lot_cnt}</td><td>${r.first_time}</td><td>${r.last_time}</td></tr>`;
    });
    tbl+='</tbody></table>';
    document.getElementById('todayTable').innerHTML=tbl;

    // Bulk Table (벌크 전용)
    let btbl=`<table><thead><tr><th>공장</th><th>라인</th><th>라인명</th><th class="num">생산수량</th><th class="num">LOT</th><th>최초생산</th><th>최근생산</th></tr></thead><tbody>`;
    prod.filter(r=>IS_BULK(r.LINE_TYPE)).forEach(r=>{
        btbl+=`<tr><td>${r.factory_name}</td><td>${r.LINE_CODE}</td><td>${r.LINE_DESC||''}</td>`;
        btbl+=`<td class="num">${fmt(r.qty)}</td><td class="num">${r.lot_cnt}</td><td>${r.first_time}</td><td>${r.last_time}</td></tr>`;
    });
    btbl+='</tbody></table>';
    document.getElementById('todayBulkTable').innerHTML=btbl;
}

// ── Tab 1: 일별 추이 ──
async function loadDaily(){
    let [trend,byLine]=await Promise.all([
        (await fetch('/api/daily_trend')).json(),
        (await fetch('/api/daily_by_line')).json()
    ]);

    _dailyTrend=trend;
    // KPI - 생산(충전+본딩)/포장 분리 — 벌크 제외
    let days=[...new Set(trend.map(r=>r.day))];
    let prodByF={},packByF={},prodTotal=0,packTotal=0;
    let fillByF2={},bondByF2={};
    trend.forEach(r=>{
        let q=Number(r.qty),f=r.factory_name;
        if(IS_PROD(r.LINE_TYPE)){prodTotal+=q;prodByF[f]=(prodByF[f]||0)+q;
            if(r.LINE_TYPE==='FILLING'){fillByF2[f]=(fillByF2[f]||0)+q}
            else{bondByF2[f]=(bondByF2[f]||0)+q}
        }
        else if(IS_PACK(r.LINE_TYPE)){packTotal+=q;packByF[f]=(packByF[f]||0)+q}
    });
    let prodAvg=days.length>0?Math.round(prodTotal/days.length):0;
    let packAvg=days.length>0?Math.round(packTotal/days.length):0;
    let mhtml=`<div class="kpi-box" style="border-color:#a78bfa" onclick="showProdDetail('daily','manu')"><div class="label">이번달 생산 (충전+본딩)</div><div class="value" style="color:#a78bfa">${fmt(prodTotal)}</div><div class="sub">가동 ${days.length}일 / 일평균 ${fmt(prodAvg)}</div></div>`;
    ['퍼플카운티','그린카운티','3공장'].forEach(f=>{
        let q=prodByF[f]||0;if(q===0)return;
        let avg=days.length>0?Math.round(q/days.length):0;
        let fill=fillByF2[f]||0,bond=bondByF2[f]||0;
        let sub=bond>0?`충전 ${fmt(fill)} / 본딩 ${fmt(bond)} / 일평균 ${fmt(avg)}`:`일평균 ${fmt(avg)}`;
        mhtml+=`<div class="kpi-box" style="border-color:${FCOLORS[f]||'#60a5fa'}" onclick="showProdDetail('daily','factory_manu','${f}')"><div class="label">${f}</div><div class="value" style="color:${FCOLORS[f]||'#60a5fa'}">${fmt(q)}</div><div class="sub">${sub}</div></div>`;
    });
    let phtml=`<div class="kpi-box" style="border-color:#34d399" onclick="showProdDetail('daily','pack')"><div class="label">이번달 포장</div><div class="value" style="color:#34d399">${fmt(packTotal)}</div><div class="sub">가동 ${days.length}일 / 일평균 ${fmt(packAvg)}</div></div>`;
    ['퍼플카운티','그린카운티','3공장'].forEach(f=>{
        let q=packByF[f]||0;if(q===0)return;
        let avg=days.length>0?Math.round(q/days.length):0;
        phtml+=`<div class="kpi-box" style="border-color:${FCOLORS[f]||'#60a5fa'}" onclick="showProdDetail('daily','factory_pack','${f}')"><div class="label">${f}</div><div class="value" style="color:${FCOLORS[f]||'#60a5fa'}">${fmt(q)}</div><div class="sub">일평균 ${fmt(avg)}</div></div>`;
    });
    document.getElementById('dailyKpiManu').innerHTML=mhtml;
    document.getElementById('dailyKpiPack').innerHTML=phtml;

    // Factory trend
    days.sort();
    let byFact={};
    trend.forEach(r=>{
        let fn=r.factory_name;
        if(!byFact[fn])byFact[fn]={};
        byFact[fn][r.day]=(byFact[fn][r.day]||0)+Number(r.qty);
    });
    if(charts.dailyFact)charts.dailyFact.destroy();
    charts.dailyFact=new Chart(document.getElementById('dailyFactChart'),{type:'line',
        data:{labels:days.map(d=>d.substring(5)),
            datasets:Object.entries(byFact).map(([fn,v])=>({label:fn,data:days.map(d=>v[d]||0),
                borderColor:FCOLORS[fn]||'#60a5fa',backgroundColor:(FCOLORS[fn]||'#60a5fa')+'33',fill:true,tension:.3,pointRadius:2}))},
        options:{responsive:true,maintainAspectRatio:false,
            scales:{y:{ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}},x:{ticks:{color:'#94a3b8',maxRotation:45},grid:{color:'#334155'}}},
            plugins:{legend:{labels:{color:'#e2e8f0'}}}}
    });

    // Process trend
    let byProc={};
    trend.forEach(r=>{
        if(!byProc[r.LINE_TYPE])byProc[r.LINE_TYPE]={};
        byProc[r.LINE_TYPE][r.day]=(byProc[r.LINE_TYPE][r.day]||0)+Number(r.qty);
    });
    if(charts.dailyProc)charts.dailyProc.destroy();
    charts.dailyProc=new Chart(document.getElementById('dailyProcChart'),{type:'line',
        data:{labels:days.map(d=>d.substring(5)),
            datasets:Object.entries(byProc).map(([t,v])=>({label:PNAMES[t]||t,data:days.map(d=>v[d]||0),
                borderColor:PCOLORS[t]||'#64748b',backgroundColor:(PCOLORS[t]||'#64748b')+'33',fill:true,tension:.3,pointRadius:2}))},
        options:{responsive:true,maintainAspectRatio:false,
            scales:{y:{stacked:true,ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}},x:{ticks:{color:'#94a3b8',maxRotation:45},grid:{color:'#334155'}}},
            plugins:{legend:{labels:{color:'#e2e8f0'}}}}
    });

    // Line table
    let tbl=`<table><thead><tr><th>날짜</th><th>공장</th><th>공정</th><th>라인</th><th>라인명</th><th class="num">생산수량</th></tr></thead><tbody>`;
    byLine.forEach(r=>{
        tbl+=`<tr><td>${r.day.substring(5)}</td><td>${r.factory_name}</td><td>${typeBadge(r.LINE_TYPE)}</td><td>${r.LINE_CODE}</td><td>${r.LINE_DESC||''}</td><td class="num">${fmt(r.qty)}</td></tr>`;
    });
    tbl+='</tbody></table>';
    document.getElementById('dailyLineTable').innerHTML=tbl;
}

// ── Tab 2: 주별 ──
async function loadWeekly(){
    let data=await(await fetch('/api/weekly_trend')).json();
    _weeklyData=data;
    let weeks=[...new Set(data.map(r=>r.wk))].sort((a,b)=>a-b);
    let wkLabel={};data.forEach(r=>{wkLabel[r.wk]=r.wk_start||('W'+r.wk)});

    // KPI - 이번주 vs 지난주 생산(충진)/포장 분리
    let curWk=weeks.length>0?weeks[weeks.length-1]:0;
    let prevWk=weeks.length>1?weeks[weeks.length-2]:0;
    let curProd=0,curPack=0,prevProd=0,prevPack=0;
    let curProdF={},curPackF={};
    data.forEach(r=>{
        let q=Number(r.qty),f=r.factory_name;
        if(r.wk===curWk){
            if(r.LINE_TYPE==='FILLING'){curProd+=q;curProdF[f]=(curProdF[f]||0)+q}
            else if(r.LINE_TYPE==='PACKING'){curPack+=q;curPackF[f]=(curPackF[f]||0)+q}
        }
        if(r.wk===prevWk){
            if(r.LINE_TYPE==='FILLING') prevProd+=q;
            else if(r.LINE_TYPE==='PACKING') prevPack+=q;
        }
    });
    let prodChg=prevProd>0?((curProd-prevProd)/prevProd*100).toFixed(1):'-';
    let packChg=prevPack>0?((curPack-prevPack)/prevPack*100).toFixed(1):'-';
    let wkpi=`<div class="kpi-box" style="border-color:#a78bfa" onclick="showProdDetail('weekly','manu')"><div class="label">이번주(W${curWk}) 생산</div><div class="value" style="color:#a78bfa">${fmt(curProd)}</div><div class="sub">전주대비 ${prodChg>0?'+':''}${prodChg}%</div></div>`;
    Object.entries(curProdF).forEach(([f,q])=>{wkpi+=`<div class="kpi-box" style="border-color:${FCOLORS[f]||'#60a5fa'}" onclick="showProdDetail('weekly','factory_manu','${f}')"><div class="label">${f}</div><div class="value" style="color:${FCOLORS[f]||'#60a5fa'}">${fmt(q)}</div></div>`});
    document.getElementById('weeklyKpiManu').innerHTML=wkpi;
    let wkpiP=`<div class="kpi-box" style="border-color:#34d399" onclick="showProdDetail('weekly','pack')"><div class="label">이번주(W${curWk}) 포장</div><div class="value" style="color:#34d399">${fmt(curPack)}</div><div class="sub">전주대비 ${packChg>0?'+':''}${packChg}%</div></div>`;
    Object.entries(curPackF).forEach(([f,q])=>{wkpiP+=`<div class="kpi-box" style="border-color:${FCOLORS[f]||'#60a5fa'}" onclick="showProdDetail('weekly','factory_pack','${f}')"><div class="label">${f}</div><div class="value" style="color:${FCOLORS[f]||'#60a5fa'}">${fmt(q)}</div></div>`});
    document.getElementById('weeklyKpiPack').innerHTML=wkpiP;

    let byFact={};
    data.forEach(r=>{
        let fn=r.factory_name;
        if(!byFact[fn])byFact[fn]={};
        byFact[fn][r.wk]=(byFact[fn][r.wk]||0)+Number(r.qty);
    });
    if(charts.weeklyFact)charts.weeklyFact.destroy();
    charts.weeklyFact=new Chart(document.getElementById('weeklyFactChart'),{type:'bar',
        data:{labels:weeks.map(w=>'W'+w),
            datasets:Object.entries(byFact).map(([fn,v])=>({label:fn,data:weeks.map(w=>v[w]||0),backgroundColor:FCOLORS[fn]||'#60a5fa'}))},
        options:{responsive:true,maintainAspectRatio:false,
            scales:{y:{ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}},x:{ticks:{color:'#94a3b8'},grid:{color:'#334155'}}},
            plugins:{legend:{labels:{color:'#e2e8f0'}}}}
    });

    let byProc={};
    data.forEach(r=>{
        if(!byProc[r.LINE_TYPE])byProc[r.LINE_TYPE]={};
        byProc[r.LINE_TYPE][r.wk]=(byProc[r.LINE_TYPE][r.wk]||0)+Number(r.qty);
    });
    if(charts.weeklyProc)charts.weeklyProc.destroy();
    charts.weeklyProc=new Chart(document.getElementById('weeklyProcChart'),{type:'bar',
        data:{labels:weeks.map(w=>'W'+w),
            datasets:Object.entries(byProc).map(([t,v])=>({label:PNAMES[t]||t,data:weeks.map(w=>v[w]||0),backgroundColor:PCOLORS[t]||'#64748b'}))},
        options:{responsive:true,maintainAspectRatio:false,
            scales:{y:{stacked:true,ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}},x:{stacked:true,ticks:{color:'#94a3b8'},grid:{color:'#334155'}}},
            plugins:{legend:{labels:{color:'#e2e8f0'}}}}
    });

    // Table
    let tbl=`<table><thead><tr><th>주차</th><th>시작일</th><th>공장</th><th>공정</th><th class="num">생산수량</th><th class="num">LOT수</th><th class="num">가동일</th><th class="num">일평균</th></tr></thead><tbody>`;
    data.forEach(r=>{
        let avg=r.work_days>0?Math.round(Number(r.qty)/Number(r.work_days)):0;
        tbl+=`<tr><td>W${r.wk}</td><td>${(wkLabel[r.wk]||'').substring(5)}</td><td>${r.factory_name}</td><td>${typeBadge(r.LINE_TYPE)}</td>`;
        tbl+=`<td class="num">${fmt(r.qty)}</td><td class="num">${fmt(r.lot_cnt)}</td><td class="num">${r.work_days}</td><td class="num">${fmt(avg)}</td></tr>`;
    });
    tbl+='</tbody></table>';
    document.getElementById('weeklyTable').innerHTML=tbl;
}

// ── Tab 3: 월별 ──
async function loadMonthly(){
    let data=await(await fetch('/api/monthly_trend')).json();
    _monthlyData=data;
    let months=[...new Set(data.map(r=>r.month))].sort();

    // KPI - 이번달 제조/포장 분리
    let curMonth=months.length>0?months[months.length-1]:'';
    let prevMonth=months.length>1?months[months.length-2]:'';
    let curProd=0,curPack=0,prevProd=0,prevPack=0;
    let curProdF={},curPackF={};
    data.forEach(r=>{
        let q=Number(r.qty),f=r.factory_name;
        if(r.month===curMonth){
            if(r.LINE_TYPE==='FILLING'){curProd+=q;curProdF[f]=(curProdF[f]||0)+q}
            else if(r.LINE_TYPE==='PACKING'){curPack+=q;curPackF[f]=(curPackF[f]||0)+q}
        }
        if(r.month===prevMonth){
            if(r.LINE_TYPE==='FILLING') prevProd+=q;
            else if(r.LINE_TYPE==='PACKING') prevPack+=q;
        }
    });
    let prodChg=prevProd>0?((curProd-prevProd)/prevProd*100).toFixed(1):'-';
    let packChg=prevPack>0?((curPack-prevPack)/prevPack*100).toFixed(1):'-';
    let mkpi=`<div class="kpi-box" style="border-color:#a78bfa" onclick="showProdDetail('monthly','manu')"><div class="label">${curMonth} 생산</div><div class="value" style="color:#a78bfa">${fmt(curProd)}</div><div class="sub">전월대비 ${prodChg>0?'+':''}${prodChg}%</div></div>`;
    Object.entries(curProdF).forEach(([f,q])=>{mkpi+=`<div class="kpi-box" style="border-color:${FCOLORS[f]||'#60a5fa'}" onclick="showProdDetail('monthly','factory_manu','${f}')"><div class="label">${f}</div><div class="value" style="color:${FCOLORS[f]||'#60a5fa'}">${fmt(q)}</div></div>`});
    document.getElementById('monthlyKpiManu').innerHTML=mkpi;
    let mkpiP=`<div class="kpi-box" style="border-color:#34d399" onclick="showProdDetail('monthly','pack')"><div class="label">${curMonth} 포장</div><div class="value" style="color:#34d399">${fmt(curPack)}</div><div class="sub">전월대비 ${packChg>0?'+':''}${packChg}%</div></div>`;
    Object.entries(curPackF).forEach(([f,q])=>{mkpiP+=`<div class="kpi-box" style="border-color:${FCOLORS[f]||'#60a5fa'}" onclick="showProdDetail('monthly','factory_pack','${f}')"><div class="label">${f}</div><div class="value" style="color:${FCOLORS[f]||'#60a5fa'}">${fmt(q)}</div></div>`});
    document.getElementById('monthlyKpiPack').innerHTML=mkpiP;

    let byFact={};
    data.forEach(r=>{
        let fn=r.factory_name;
        if(!byFact[fn])byFact[fn]={};
        byFact[fn][r.month]=(byFact[fn][r.month]||0)+Number(r.qty);
    });
    if(charts.monthlyFact)charts.monthlyFact.destroy();
    charts.monthlyFact=new Chart(document.getElementById('monthlyFactChart'),{type:'bar',
        data:{labels:months,
            datasets:Object.entries(byFact).map(([fn,v])=>({label:fn,data:months.map(m=>v[m]||0),backgroundColor:FCOLORS[fn]||'#60a5fa'}))},
        options:{responsive:true,maintainAspectRatio:false,
            scales:{y:{ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}},x:{ticks:{color:'#94a3b8'},grid:{color:'#334155'}}},
            plugins:{legend:{labels:{color:'#e2e8f0'}}}}
    });

    let byProc={};
    data.forEach(r=>{
        if(!byProc[r.LINE_TYPE])byProc[r.LINE_TYPE]={};
        byProc[r.LINE_TYPE][r.month]=(byProc[r.LINE_TYPE][r.month]||0)+Number(r.qty);
    });
    if(charts.monthlyProc)charts.monthlyProc.destroy();
    charts.monthlyProc=new Chart(document.getElementById('monthlyProcChart'),{type:'bar',
        data:{labels:months,
            datasets:Object.entries(byProc).map(([t,v])=>({label:PNAMES[t]||t,data:months.map(m=>v[m]||0),backgroundColor:PCOLORS[t]||'#64748b'}))},
        options:{responsive:true,maintainAspectRatio:false,
            scales:{y:{stacked:true,ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}},x:{stacked:true,ticks:{color:'#94a3b8'},grid:{color:'#334155'}}},
            plugins:{legend:{labels:{color:'#e2e8f0'}}}}
    });

    // Table
    let tbl=`<table><thead><tr><th>월</th><th>공장</th><th>공정</th><th class="num">생산수량</th><th class="num">LOT수</th><th class="num">가동일</th><th class="num">일평균</th></tr></thead><tbody>`;
    data.forEach(r=>{
        let avg=r.work_days>0?Math.round(Number(r.qty)/Number(r.work_days)):0;
        tbl+=`<tr><td>${r.month}</td><td>${r.factory_name}</td><td>${typeBadge(r.LINE_TYPE)}</td>`;
        tbl+=`<td class="num">${fmt(r.qty)}</td><td class="num">${fmt(r.lot_cnt)}</td><td class="num">${r.work_days}</td><td class="num">${fmt(avg)}</td></tr>`;
    });
    tbl+='</tbody></table>';
    document.getElementById('monthlyTable').innerHTML=tbl;
}

// ── Tab 4: 이슈 ──
async function loadIssues(){
    let [nwkToday,nwkMonth,lowProd]=await Promise.all([
        (await fetch('/api/nonwork_today')).json(),
        (await fetch('/api/nonwork_monthly')).json(),
        (await fetch('/api/low_productivity')).json()
    ]);

    _nwkToday=nwkToday;_lowProd=lowProd;
    let totalHrsToday=nwkToday.reduce((s,r)=>s+r.hours,0);
    let equipCnt=nwkToday.filter(r=>r.is_equip).length;
    let matCnt=nwkToday.filter(r=>r.is_material).length;
    document.getElementById('issueKpi').innerHTML=
        `<div class="kpi-box" style="border-color:#f87171" onclick="showProdDetail('issue','all')"><div class="label">오늘 비가동 총시간</div><div class="value" style="color:#f87171">${totalHrsToday.toFixed(1)}h</div></div>`+
        `<div class="kpi-box" style="border-color:#ef4444" onclick="showProdDetail('issue','equip')"><div class="label">설비고장 건수</div><div class="value" style="color:#ef4444">${equipCnt}</div></div>`+
        `<div class="kpi-box" style="border-color:#fbbf24" onclick="showProdDetail('issue','material')"><div class="label">자재이슈 건수</div><div class="value" style="color:#fbbf24">${matCnt}</div></div>`+
        `<div class="kpi-box" style="border-color:#94a3b8" onclick="showProdDetail('issue','lowprod')"><div class="label">저생산성 라인</div><div class="value" style="color:#94a3b8">${lowProd.length}</div></div>`;

    // Today nonwork table
    let tbl=`<table><thead><tr><th>공장</th><th>라인</th><th>라인명</th><th>유형</th><th>비가동코드</th><th class="num">건수</th><th class="num">시간(h)</th></tr></thead><tbody>`;
    nwkToday.forEach(r=>{
        let cls=r.is_equip?'alert-row':r.is_material?'alert-row':'';
        let badge=r.is_equip?'<span class="badge badge-equip">설비</span>':r.is_material?'<span class="badge badge-material">자재</span>':'';
        tbl+=`<tr class="${cls}"><td>${r.factory_name}</td><td>${r.LINE_CODE}</td><td>${r.LINE_DESC||''}</td><td>${badge} ${typeBadge(r.LINE_TYPE)}</td>`;
        tbl+=`<td>${r.NONWORK_CODE} ${r.code_name}</td><td class="num">${r.cnt}</td><td class="num">${r.hours}</td></tr>`;
    });
    tbl+='</tbody></table>';
    document.getElementById('nwkTodayTable').innerHTML=tbl;

    // Monthly nonwork chart
    if(charts.nwkMonth)charts.nwkMonth.destroy();
    let top10=nwkMonth.slice(0,10);
    charts.nwkMonth=new Chart(document.getElementById('nwkMonthChart'),{type:'bar',
        data:{labels:top10.map(r=>`${r.factory_name} ${r.code_name}`),
            datasets:[{label:'비가동(h)',data:top10.map(r=>r.hours),
                backgroundColor:top10.map(r=>r.NONWORK_CODE.startsWith('E2')?'#ef4444':r.NONWORK_CODE.startsWith('E3')?'#fbbf24':'#60a5fa')}]},
        options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',
            scales:{x:{ticks:{color:'#94a3b8'},grid:{color:'#334155'}},y:{ticks:{color:'#94a3b8',font:{size:10}},grid:{color:'#334155'}}},
            plugins:{legend:{display:false}}}
    });

    // Low productivity table
    let tbl2=`<table><thead><tr><th>공장</th><th>라인</th><th>라인명</th><th>공정</th><th class="num">총생산</th><th class="num">가동일</th><th class="num">일평균</th></tr></thead><tbody>`;
    lowProd.slice(0,15).forEach(r=>{
        tbl2+=`<tr><td>${r.factory_name}</td><td>${r.LINE_CODE}</td><td>${r.LINE_DESC||''}</td><td>${typeBadge(r.LINE_TYPE)}</td>`;
        tbl2+=`<td class="num">${fmt(r.total_qty)}</td><td class="num">${r.work_days}</td><td class="num">${fmt(r.daily_avg)}</td></tr>`;
    });
    tbl2+='</tbody></table>';
    document.getElementById('lowProdTable').innerHTML=tbl2;
}

// ── Tab 5: 계획 변경 ──
let _planChanges=[],_urgentOrders=[],_changeFilter='ALL';

async function loadPlanChanges(){
    try{
        let [changes,urgent]=await Promise.all([
            (await fetch('/api/plan_changes')).json(),
            (await fetch('/api/urgent_orders')).json()
        ]);
        _planChanges=changes;_urgentOrders=urgent;

        // KPI
        let deadlineFwd=changes.filter(r=>r.deadline_forward).length;
        let deadlineDly=changes.filter(r=>r.deadline_delay).length;
        let qtyUp=changes.filter(r=>r.qty_increase).length;
        let qtyDn=changes.filter(r=>r.qty_decrease).length;
        let startChg=changes.filter(r=>r.start_change).length;
        let totalChg=changes.length;

        document.getElementById('changeKpi').innerHTML=
            `<div class="kpi-box" style="border-color:#ef4444" onclick="filterChange('DEADLINE')"><div class="label">납기 앞당김</div><div class="value" style="color:#ef4444">${deadlineFwd}</div><div class="sub">긴급 대응 필요</div></div>`+
            `<div class="kpi-box" style="border-color:#fb923c" onclick="filterChange('DEADLINE')"><div class="label">납기 연장</div><div class="value" style="color:#fb923c">${deadlineDly}</div></div>`+
            `<div class="kpi-box" style="border-color:#fbbf24" onclick="filterChange('QTY')"><div class="label">수량 증가</div><div class="value" style="color:#fbbf24">${qtyUp}</div></div>`+
            `<div class="kpi-box" style="border-color:#94a3b8" onclick="filterChange('QTY')"><div class="label">수량 감소</div><div class="value" style="color:#94a3b8">${qtyDn}</div></div>`+
            `<div class="kpi-box" style="border-color:#a78bfa" onclick="filterChange('START')"><div class="label">착수일 변경</div><div class="value" style="color:#a78bfa">${startChg}</div></div>`+
            `<div class="kpi-box" style="border-color:#f87171" onclick="filterChange('URGENT')"><div class="label">긴급수주(3일이내)</div><div class="value" style="color:#f87171">${urgent.length}</div></div>`;

        // Badge on tab
        let badge=document.getElementById('changeBadge');
        let alertCnt=deadlineFwd+urgent.length;
        if(alertCnt>0){badge.textContent=alertCnt;badge.style.display='inline'}
        else badge.style.display='none';

        renderChangeTable('ALL');
        renderChangeCharts(changes);
    }catch(e){console.log('plan_changes error:',e)}
}

function filterChange(type){
    _changeFilter=type;
    document.querySelectorAll('#tab5 .phase-btn').forEach(b=>b.classList.remove('active'));
    let id={ALL:'chgAll',DEADLINE:'chgDeadline',QTY:'chgQty',START:'chgStart',URGENT:'chgUrgent'}[type];
    if(id)document.getElementById(id).classList.add('active');
    renderChangeTable(type);
}

function renderChangeTable(type){
    let data;
    if(type==='URGENT'){
        // 긴급수주 테이블
        let tbl=`<table><thead><tr><th>공장</th><th>주문번호</th><th>수주번호</th><th>거래처</th><th class="num">수량</th><th>확정일</th><th>납기일</th><th class="num">여유(일)</th><th>상태</th></tr></thead><tbody>`;
        _urgentOrders.forEach(r=>{
            let nd=Number(r.notice_days);
            let cls=nd<=1?'color:#ef4444':nd<=2?'color:#fb923c':'color:#fbbf24';
            tbl+=`<tr><td>${FC[r.FACTORY_CODE]||r.FACTORY_CODE}</td><td>${r.ORDER_NO}</td><td>${r.SO_NO}</td>`;
            tbl+=`<td>${r.cust_name||r.CUSTOMER_CODE}</td><td class="num">${fmt(r.ORD_QTY)}</td>`;
            tbl+=`<td>${r.CONFIRM_DATE}</td><td>${r.ORD_END_TIME}</td>`;
            tbl+=`<td class="num" style="${cls};font-weight:700">${nd}일</td>`;
            tbl+=`<td><span class="badge badge-${(r.ORD_STATUS||'').toLowerCase()}">${r.ORD_STATUS}</span></td></tr>`;
        });
        tbl+=`</tbody></table>`;
        document.getElementById('changeTable').innerHTML=tbl;
        return;
    }
    data=[..._planChanges];
    if(type==='DEADLINE') data=data.filter(r=>r.deadline_forward||r.deadline_delay);
    if(type==='QTY') data=data.filter(r=>r.qty_increase||r.qty_decrease);
    if(type==='START') data=data.filter(r=>r.start_change);

    let tbl=`<table><thead><tr><th>공장</th><th>주문번호</th><th>수주번호</th><th>거래처</th><th>변경유형</th><th>변경 전</th><th>변경 후</th><th>상태</th></tr></thead><tbody>`;
    data.forEach(r=>{
        let types=[];
        if(r.deadline_forward) types.push('<span style="color:#ef4444">납기앞당김</span>');
        if(r.deadline_delay) types.push('<span style="color:#fb923c">납기연장</span>');
        if(r.qty_increase) types.push('<span style="color:#fbbf24">수량증가</span>');
        if(r.qty_decrease) types.push('<span style="color:#94a3b8">수량감소</span>');
        if(r.start_change) types.push('<span style="color:#a78bfa">착수일변경</span>');

        let before=[],after=[];
        if(r.orig_end!==r.new_end){before.push('납기:'+r.orig_end);after.push('납기:'+r.new_end)}
        if(r.orig_qty!==r.new_qty){before.push('수량:'+fmt(r.orig_qty));after.push('수량:'+fmt(r.new_qty))}
        if(r.orig_start!==r.new_start){before.push('착수:'+r.orig_start);after.push('착수:'+r.new_start)}

        tbl+=`<tr><td>${FC[r.FACTORY_CODE]||r.FACTORY_CODE}</td><td>${r.ORDER_NO}</td><td>${r.SO_NO}</td>`;
        tbl+=`<td>${r.cust_name||r.CUSTOMER_CODE}</td><td>${types.join(' ')}</td>`;
        tbl+=`<td style="color:#94a3b8">${before.join('<br>')}</td><td style="font-weight:600">${after.join('<br>')}</td>`;
        tbl+=`<td><span class="badge badge-${(r.ORD_STATUS||'').toLowerCase()}">${r.ORD_STATUS}</span></td></tr>`;
    });
    tbl+=`</tbody></table>`;
    document.getElementById('changeTable').innerHTML=tbl;
}

function renderChangeCharts(data){
    // 거래처별 변경 빈도
    let custCnt={};
    data.forEach(r=>{let k=r.cust_name||r.CUSTOMER_CODE;custCnt[k]=(custCnt[k]||0)+1});
    let custTop=Object.entries(custCnt).sort((a,b)=>b[1]-a[1]).slice(0,15);
    if(charts.changeCust)charts.changeCust.destroy();
    charts.changeCust=new Chart(document.getElementById('changeCustChart'),{type:'bar',
        data:{labels:custTop.map(c=>c[0].substring(0,20)),datasets:[{label:'변경 건수',data:custTop.map(c=>c[1]),
            backgroundColor:custTop.map((_,i)=>i<3?'#ef4444':i<7?'#fb923c':'#60a5fa')}]},
        options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',
            scales:{x:{ticks:{color:'#94a3b8'},grid:{color:'#334155'}},y:{ticks:{color:'#94a3b8',font:{size:10}},grid:{color:'#334155'}}},
            plugins:{legend:{display:false}}}
    });

    // 변경 유형 분포
    let typeCnt={납기앞당김:0,납기연장:0,수량증가:0,수량감소:0,착수일변경:0};
    data.forEach(r=>{
        if(r.deadline_forward)typeCnt['납기앞당김']++;
        if(r.deadline_delay)typeCnt['납기연장']++;
        if(r.qty_increase)typeCnt['수량증가']++;
        if(r.qty_decrease)typeCnt['수량감소']++;
        if(r.start_change)typeCnt['착수일변경']++;
    });
    let typeLabels=Object.keys(typeCnt),typeVals=Object.values(typeCnt);
    let typeColors=['#ef4444','#fb923c','#fbbf24','#94a3b8','#a78bfa'];
    if(charts.changeType)charts.changeType.destroy();
    charts.changeType=new Chart(document.getElementById('changeTypeChart'),{type:'doughnut',
        data:{labels:typeLabels,datasets:[{data:typeVals,backgroundColor:typeColors}]},
        options:{responsive:true,maintainAspectRatio:false,
            plugins:{legend:{position:'right',labels:{color:'#e2e8f0',font:{size:12}}}}}
    });
}

// ── KPI 상세 모달 ──
function showProdDetail(tab,filterType,filterKey){
    let html='';
    if(tab==='today'){
        let data=_todayProd;
        let title=filterType==='manu'?'오늘 생산 상세':filterType==='pack'?'오늘 포장 상세':filterType==='factory_manu'?filterKey+' 생산 상세':filterType==='factory_pack'?filterKey+' 포장 상세':filterType==='factory'?filterKey+' 상세':'상세';
        if(filterType==='manu') data=data.filter(r=>r.LINE_TYPE==='FILLING');
        if(filterType==='pack') data=data.filter(r=>r.LINE_TYPE==='PACKING');
        if(filterType==='factory_manu') data=data.filter(r=>r.factory_name===filterKey&&r.LINE_TYPE==='FILLING');
        if(filterType==='factory_pack') data=data.filter(r=>r.factory_name===filterKey&&r.LINE_TYPE==='PACKING');
        if(filterType==='factory') data=data.filter(r=>r.factory_name===filterKey);
        if(filterType==='process') data=data.filter(r=>r.LINE_TYPE===filterKey);
        // Factory × Process matrix
        html+=`<h3>${title}</h3>`;
        html+=buildMatrix(data,'factory_name','LINE_TYPE','qty');
        // Line detail
        html+=`<h4>라인별 상세</h4><div class="scroll-table" style="max-height:400px"><table><thead><tr><th>공장</th><th>공정</th><th>라인</th><th>라인명</th><th class="num">생산수량</th><th class="num">LOT</th><th>최초</th><th>최근</th></tr></thead><tbody>`;
        data.sort((a,b)=>Number(b.qty)-Number(a.qty)).forEach(r=>{
            html+=`<tr><td>${r.factory_name}</td><td>${typeBadge(r.LINE_TYPE)}</td><td>${r.LINE_CODE}</td><td>${r.LINE_DESC||''}</td><td class="num">${fmt(r.qty)}</td><td class="num">${r.lot_cnt}</td><td>${r.first_time||''}</td><td>${r.last_time||''}</td></tr>`;
        });
        html+=`</tbody></table></div>`;
    } else if(tab==='daily'){
        let data=_dailyTrend;
        let title=filterType==='manu'?'이번달 생산 상세':filterType==='pack'?'이번달 포장 상세':filterType==='factory_manu'?filterKey+' 생산 상세':filterType==='factory_pack'?filterKey+' 포장 상세':'이번달 상세';
        if(filterType==='manu') data=data.filter(r=>r.LINE_TYPE==='FILLING');
        if(filterType==='pack') data=data.filter(r=>r.LINE_TYPE==='PACKING');
        if(filterType==='factory_manu') data=data.filter(r=>r.factory_name===filterKey&&r.LINE_TYPE==='FILLING');
        if(filterType==='factory_pack') data=data.filter(r=>r.factory_name===filterKey&&r.LINE_TYPE==='PACKING');
        if(filterType==='factory') data=data.filter(r=>r.factory_name===filterKey);
        if(filterType==='process') data=data.filter(r=>r.LINE_TYPE===filterKey);
        html+=`<h3>${title}</h3>`;
        html+=buildMatrix(data,'factory_name','LINE_TYPE','qty');
        // Daily breakdown
        let days=[...new Set(data.map(r=>r.day))].sort();
        html+=`<h4>일별 추이</h4><div class="scroll-table" style="max-height:400px"><table><thead><tr><th>날짜</th><th>공장</th><th>공정</th><th class="num">생산수량</th><th class="num">LOT수</th></tr></thead><tbody>`;
        data.sort((a,b)=>a.day<b.day?1:-1).forEach(r=>{
            html+=`<tr><td>${(r.day||'').substring(5)}</td><td>${r.factory_name}</td><td>${typeBadge(r.LINE_TYPE)}</td><td class="num">${fmt(r.qty)}</td><td class="num">${fmt(r.lot_cnt)}</td></tr>`;
        });
        html+=`</tbody></table></div>`;
    } else if(tab==='weekly'){
        let data=_weeklyData;
        let weeks=[...new Set(data.map(r=>r.wk))].sort((a,b)=>a-b);
        let curWk=weeks.length>0?weeks[weeks.length-1]:0;
        let title=filterType==='manu'?`W${curWk} 생산 상세`:filterType==='pack'?`W${curWk} 포장 상세`:filterType==='factory_manu'?`${filterKey} W${curWk} 생산`:filterType==='factory_pack'?`${filterKey} W${curWk} 포장`:`W${curWk} 상세`;
        let curData=data.filter(r=>r.wk===curWk);
        if(filterType==='manu') curData=curData.filter(r=>r.LINE_TYPE==='FILLING');
        if(filterType==='pack') curData=curData.filter(r=>r.LINE_TYPE==='PACKING');
        if(filterType==='factory_manu') curData=curData.filter(r=>r.factory_name===filterKey&&r.LINE_TYPE==='FILLING');
        if(filterType==='factory_pack') curData=curData.filter(r=>r.factory_name===filterKey&&r.LINE_TYPE==='PACKING');
        if(filterType==='factory') curData=curData.filter(r=>r.factory_name===filterKey);
        if(filterType==='process') curData=curData.filter(r=>r.LINE_TYPE===filterKey);
        html+=`<h3>${title}</h3>`;
        html+=buildMatrix(curData,'factory_name','LINE_TYPE','qty');
        // Week-over-week
        html+=`<h4>주차별 추이</h4><div class="scroll-table" style="max-height:400px"><table><thead><tr><th>주차</th><th>공장</th><th>공정</th><th class="num">생산수량</th><th class="num">가동일</th><th class="num">일평균</th></tr></thead><tbody>`;
        let filtered=filterType==='manu'?data.filter(r=>r.LINE_TYPE==='FILLING'):filterType==='pack'?data.filter(r=>r.LINE_TYPE==='PACKING'):filterType==='factory_manu'?data.filter(r=>r.factory_name===filterKey&&r.LINE_TYPE==='FILLING'):filterType==='factory_pack'?data.filter(r=>r.factory_name===filterKey&&r.LINE_TYPE==='PACKING'):filterType==='factory'?data.filter(r=>r.factory_name===filterKey):filterType==='process'?data.filter(r=>r.LINE_TYPE===filterKey):data;
        filtered.sort((a,b)=>b.wk-a.wk).forEach(r=>{
            let avg=r.work_days>0?Math.round(Number(r.qty)/Number(r.work_days)):0;
            html+=`<tr><td>W${r.wk}</td><td>${r.factory_name}</td><td>${typeBadge(r.LINE_TYPE)}</td><td class="num">${fmt(r.qty)}</td><td class="num">${r.work_days}</td><td class="num">${fmt(avg)}</td></tr>`;
        });
        html+=`</tbody></table></div>`;
    } else if(tab==='monthly'){
        let data=_monthlyData;
        let months=[...new Set(data.map(r=>r.month))].sort();
        let curM=months.length>0?months[months.length-1]:'';
        let title=filterType==='manu'?`${curM} 생산 상세`:filterType==='pack'?`${curM} 포장 상세`:filterType==='factory_manu'?`${filterKey} ${curM} 생산`:filterType==='factory_pack'?`${filterKey} ${curM} 포장`:`${curM} 상세`;
        let curData=data.filter(r=>r.month===curM);
        if(filterType==='manu') curData=curData.filter(r=>r.LINE_TYPE==='FILLING');
        if(filterType==='pack') curData=curData.filter(r=>r.LINE_TYPE==='PACKING');
        if(filterType==='factory_manu') curData=curData.filter(r=>r.factory_name===filterKey&&r.LINE_TYPE==='FILLING');
        if(filterType==='factory_pack') curData=curData.filter(r=>r.factory_name===filterKey&&r.LINE_TYPE==='PACKING');
        if(filterType==='factory') curData=curData.filter(r=>r.factory_name===filterKey);
        if(filterType==='process') curData=curData.filter(r=>r.LINE_TYPE===filterKey);
        html+=`<h3>${title}</h3>`;
        html+=buildMatrix(curData,'factory_name','LINE_TYPE','qty');
        html+=`<h4>월별 추이</h4><div class="scroll-table" style="max-height:400px"><table><thead><tr><th>월</th><th>공장</th><th>공정</th><th class="num">생산수량</th><th class="num">가동일</th><th class="num">일평균</th></tr></thead><tbody>`;
        let filtered=filterType==='manu'?data.filter(r=>r.LINE_TYPE==='FILLING'):filterType==='pack'?data.filter(r=>r.LINE_TYPE==='PACKING'):filterType==='factory_manu'?data.filter(r=>r.factory_name===filterKey&&r.LINE_TYPE==='FILLING'):filterType==='factory_pack'?data.filter(r=>r.factory_name===filterKey&&r.LINE_TYPE==='PACKING'):filterType==='factory'?data.filter(r=>r.factory_name===filterKey):filterType==='process'?data.filter(r=>r.LINE_TYPE===filterKey):data;
        filtered.sort((a,b)=>b.month>a.month?1:-1).forEach(r=>{
            let avg=r.work_days>0?Math.round(Number(r.qty)/Number(r.work_days)):0;
            html+=`<tr><td>${r.month}</td><td>${r.factory_name}</td><td>${typeBadge(r.LINE_TYPE)}</td><td class="num">${fmt(r.qty)}</td><td class="num">${r.work_days}</td><td class="num">${fmt(avg)}</td></tr>`;
        });
        html+=`</tbody></table></div>`;
    } else if(tab==='issue'){
        if(filterType==='lowprod'){
            html+=`<h3>저생산성 라인 상세</h3><table><thead><tr><th>공장</th><th>라인</th><th>라인명</th><th>공정</th><th class="num">총생산</th><th class="num">가동일</th><th class="num">일평균</th></tr></thead><tbody>`;
            _lowProd.forEach(r=>{
                html+=`<tr><td>${r.factory_name}</td><td>${r.LINE_CODE}</td><td>${r.LINE_DESC||''}</td><td>${typeBadge(r.LINE_TYPE)}</td><td class="num">${fmt(r.total_qty)}</td><td class="num">${r.work_days}</td><td class="num">${fmt(r.daily_avg)}</td></tr>`;
            });
            html+=`</tbody></table>`;
        } else {
            let data=_nwkToday;
            let title=filterType==='equip'?'설비고장 상세':filterType==='material'?'자재이슈 상세':'비가동 전체 상세';
            if(filterType==='equip') data=data.filter(r=>r.is_equip);
            if(filterType==='material') data=data.filter(r=>r.is_material);
            // Factory summary
            let byF={};data.forEach(r=>{if(!byF[r.factory_name])byF[r.factory_name]={cnt:0,hrs:0};byF[r.factory_name].cnt+=Number(r.cnt);byF[r.factory_name].hrs+=r.hours});
            html+=`<h3>${title}</h3><h4>공장별 요약</h4><table><thead><tr><th>공장</th><th class="num">건수</th><th class="num">시간(h)</th></tr></thead><tbody>`;
            Object.entries(byF).forEach(([f,v])=>{html+=`<tr><td>${f}</td><td class="num">${v.cnt}</td><td class="num">${v.hrs.toFixed(1)}</td></tr>`});
            html+=`</tbody></table>`;
            html+=`<h4>상세 목록</h4><table><thead><tr><th>공장</th><th>라인</th><th>라인명</th><th>공정</th><th>비가동코드</th><th class="num">건수</th><th class="num">시간(h)</th></tr></thead><tbody>`;
            data.forEach(r=>{
                html+=`<tr><td>${r.factory_name}</td><td>${r.LINE_CODE}</td><td>${r.LINE_DESC||''}</td><td>${typeBadge(r.LINE_TYPE)}</td><td>${r.NONWORK_CODE} ${r.code_name}</td><td class="num">${r.cnt}</td><td class="num">${r.hours.toFixed(1)}</td></tr>`;
            });
            html+=`</tbody></table>`;
        }
    }
    document.getElementById('kpiModalBody').innerHTML=html;
    document.getElementById('kpiModal').style.display='flex';
}

function buildMatrix(data,rowKey,colKey,valKey){
    let rows=new Set(),cols=new Set(),m={};
    data.forEach(r=>{
        let rk=r[rowKey],ck=r[colKey],v=Number(r[valKey]);
        rows.add(rk);cols.add(ck);
        if(!m[rk])m[rk]={};m[rk][ck]=(m[rk][ck]||0)+v;
    });
    let colArr=[...cols],rowArr=[...rows];
    let html=`<table><thead><tr><th>공장 \\ 공정</th>`;
    colArr.forEach(c=>{html+=`<th class="num">${PNAMES[c]||c}</th>`});
    html+=`<th class="num" style="font-weight:700">합계</th></tr></thead><tbody>`;
    let colTotals={};
    rowArr.forEach(rk=>{
        let rowTotal=0;
        html+=`<tr><td>${rk}</td>`;
        colArr.forEach(ck=>{
            let v=m[rk]?.[ck]||0;rowTotal+=v;colTotals[ck]=(colTotals[ck]||0)+v;
            html+=`<td class="num">${fmt(v)}</td>`;
        });
        html+=`<td class="num" style="font-weight:700">${fmt(rowTotal)}</td></tr>`;
    });
    let grandTotal=0;
    html+=`<tr style="font-weight:700;border-top:2px solid #64748b"><td>합계</td>`;
    colArr.forEach(ck=>{let v=colTotals[ck]||0;grandTotal+=v;html+=`<td class="num">${fmt(v)}</td>`});
    html+=`<td class="num">${fmt(grandTotal)}</td></tr></tbody></table>`;
    return html;
}

loadAll();
setInterval(loadAll,60000);
</script>
<div class="kpi-modal-overlay" id="kpiModal" onclick="if(event.target===this)this.style.display='none'">
<div class="kpi-modal">
<button class="close-btn" onclick="document.getElementById('kpiModal').style.display='none'">&times;</button>
<div id="kpiModalBody"></div>
</div></div>
</body></html>'''

if __name__ == '__main__':
    print('Production Dashboard: http://localhost:5001')
    app.run(host='0.0.0.0', port=5001, debug=False)
