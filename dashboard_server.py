from flask import Flask, render_template_string, jsonify
import pymssql
import json
from datetime import datetime

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
            if isinstance(v, datetime):
                r[k] = v.strftime('%Y-%m-%d %H:%M')
            elif v is None:
                r[k] = ''
    return rows

FACTORY = {'1100':'퍼플카운티','1200':'그린카운티','1300':'3공장'}

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/order_summary')
def order_summary():
    rows = query("""
        SELECT FACTORY_CODE,
            SUM(CASE WHEN ORD_STATUS='WAIT' THEN 1 ELSE 0 END) AS wait_cnt,
            SUM(CASE WHEN ORD_STATUS='WAIT' THEN ORD_QTY ELSE 0 END) AS wait_qty,
            SUM(CASE WHEN ORD_STATUS='CONFIRM' THEN 1 ELSE 0 END) AS cfm_cnt,
            SUM(CASE WHEN ORD_STATUS='CONFIRM' THEN ORD_QTY ELSE 0 END) AS cfm_qty,
            SUM(CASE WHEN ORD_STATUS='PROCESS' THEN 1 ELSE 0 END) AS proc_cnt,
            SUM(CASE WHEN ORD_STATUS='PROCESS' THEN ORD_QTY ELSE 0 END) AS proc_qty,
            SUM(CASE WHEN ORD_STATUS='CLOSE' THEN 1 ELSE 0 END) AS close_cnt,
            SUM(CASE WHEN ORD_STATUS='CLOSE' THEN ORD_QTY ELSE 0 END) AS close_qty
        FROM MWIPORDSTS WHERE ORD_STATUS NOT IN ('DELETE')
        GROUP BY FACTORY_CODE ORDER BY FACTORY_CODE
    """)
    for r in rows:
        r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
        for k in r:
            if isinstance(r[k], (int, float)) and r[k] != r[k]:
                r[k] = 0
    return jsonify(rows)

@app.route('/api/daily_production')
def daily_production():
    rows = query("""
        SELECT CONVERT(VARCHAR, TRAN_TIME, 23) AS day, FACTORY_CODE, SUM(QTY) AS qty
        FROM MWIPLOTHIS
        WHERE TRAN_CODE='CV' AND TRAN_TIME >= '2026-03-01' AND TRAN_TIME < '2026-03-30'
        GROUP BY CONVERT(VARCHAR, TRAN_TIME, 23), FACTORY_CODE
        ORDER BY CONVERT(VARCHAR, TRAN_TIME, 23)
    """)
    for r in rows:
        r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
    return jsonify(rows)

@app.route('/api/nonwork_summary')
def nonwork_summary():
    rows = query("""
        SELECT TOP 15 n.FACTORY_CODE, n.NONWORK_CODE,
            COUNT(*) AS cnt, SUM(n.NONWORK_SECOND) AS total_sec
        FROM MWIPNWKSTS n
        WHERE n.NONWORK_DATE >= '20260301'
        GROUP BY n.FACTORY_CODE, n.NONWORK_CODE
        ORDER BY SUM(n.NONWORK_SECOND) DESC
    """)
    nwk = {'E101':'작업준비','E102':'품목교체(호수)','E103':'품목교체(제품)',
           'E201':'충전부고장','E202':'캡핑부고장','E203':'컨베이어고장',
           'E206':'순간정비','E301':'자재불량대기','E303':'자재불출지연',
           'E401':'QC확인대기','E403':'내용물불량대기','E501':'벌크보충',
           'E505':'(미등록)E505','E506':'(미등록)E506','E601':'청소정리'}
    for r in rows:
        r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
        r['code_name'] = nwk.get(r['NONWORK_CODE'], r['NONWORK_CODE'])
        r['hours'] = round(int(r['total_sec']) / 3600, 1)
    return jsonify(rows)

@app.route('/api/so_risk')
def so_risk():
    rows = query("""
        SELECT TOP 30 i.SO_NO, i.CUST_PO_NO, i.CUSTOMER_CODE,
            COUNT(DISTINCT i.ORDER_NO) AS ord_cnt,
            SUM(i.ORD_QTY) AS total_qty,
            SUM(ISNULL(o.ORD_OUT_QTY,0)) AS total_out,
            SUM(i.ORD_QTY) - SUM(ISNULL(o.ORD_OUT_QTY,0)) AS remaining,
            MAX(i.ORD_END_TIME) AS deadline,
            CASE WHEN SUM(i.ORD_QTY)>0 THEN CAST(SUM(ISNULL(o.ORD_OUT_QTY,0))*100.0/SUM(i.ORD_QTY) AS DECIMAL(5,1)) ELSE 0 END AS pct
        FROM IWIPORDSTS i
        LEFT JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        WHERE i.SO_NO IS NOT NULL AND i.SO_NO <> ''
            AND i.CONFIRM_DATE >= '20260301'
        GROUP BY i.SO_NO, i.CUST_PO_NO, i.CUSTOMER_CODE
        HAVING SUM(ISNULL(o.ORD_OUT_QTY,0)) < SUM(i.ORD_QTY) * 0.98
            AND MAX(i.ORD_END_TIME) <= '20260405'
        ORDER BY MAX(i.ORD_END_TIME), SUM(i.ORD_QTY) DESC
    """)
    today = datetime.now().strftime('%Y%m%d')
    for r in rows:
        dl = str(r['deadline'])
        pct = float(r['pct'])
        if dl < today:
            r['risk'] = 'OVERDUE'
        elif dl <= '20260331' and pct < 50:
            r['risk'] = 'HIGH'
        elif dl <= '20260331':
            r['risk'] = 'MEDIUM'
        else:
            r['risk'] = 'LOW'
        r['deadline_fmt'] = f'{dl[:4]}-{dl[4:6]}-{dl[6:]}' if len(dl)==8 else dl
    return jsonify(rows)

@app.route('/api/customer_achieve')
def customer_achieve():
    rows = query("""
        SELECT TOP 20 i.CUSTOMER_CODE,
            COUNT(DISTINCT i.SO_NO) AS so_cnt,
            SUM(i.ORD_QTY) AS total_qty,
            SUM(ISNULL(o.ORD_OUT_QTY,0)) AS total_out,
            CASE WHEN SUM(i.ORD_QTY)>0 THEN CAST(SUM(ISNULL(o.ORD_OUT_QTY,0))*100.0/SUM(i.ORD_QTY) AS DECIMAL(5,1)) ELSE 0 END AS pct
        FROM IWIPORDSTS i
        LEFT JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        WHERE i.SO_NO IS NOT NULL AND i.SO_NO <> '' AND i.CONFIRM_DATE >= '20260301'
        GROUP BY i.CUSTOMER_CODE
        ORDER BY SUM(i.ORD_QTY) DESC
    """)
    return jsonify(rows)

@app.route('/api/customer_detail')
def customer_detail():
    cust = '20000052'
    so_list = query(f"""
        SELECT i.SO_NO, i.CUST_PO_NO,
            COUNT(DISTINCT i.ORDER_NO) AS ord_cnt,
            SUM(i.ORD_QTY) AS total_qty,
            SUM(ISNULL(o.ORD_OUT_QTY,0)) AS total_out,
            SUM(ISNULL(o.RCV_GOOD_QTY,0)) AS good_qty,
            SUM(ISNULL(o.RCV_LOSS_QTY,0)) AS loss_qty,
            MIN(i.ORD_START_TIME) AS start_dt,
            MAX(i.ORD_END_TIME) AS end_dt,
            SUM(CASE WHEN o.ORD_STATUS='CLOSE' THEN 1 ELSE 0 END) AS closed,
            SUM(CASE WHEN o.ORD_STATUS IN ('WAIT','CONFIRM','PROCESS') THEN 1 ELSE 0 END) AS active,
            CASE WHEN SUM(i.ORD_QTY)>0 THEN CAST(SUM(ISNULL(o.ORD_OUT_QTY,0))*100.0/SUM(i.ORD_QTY) AS DECIMAL(5,1)) ELSE 0 END AS pct
        FROM IWIPORDSTS i
        LEFT JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        WHERE i.CUSTOMER_CODE = '{cust}' AND i.CONFIRM_DATE >= '20260101'
        GROUP BY i.SO_NO, i.CUST_PO_NO
        ORDER BY MAX(i.ORD_END_TIME) DESC
    """)
    orders = query(f"""
        SELECT i.SO_NO, i.CUST_PO_NO, i.FACTORY_CODE, i.ORDER_NO,
            i.MAT_CODE, i.LINE_CODE, i.ORD_QTY, i.ORD_START_TIME, i.ORD_END_TIME,
            o.ORD_STATUS, ISNULL(o.ORD_OUT_QTY,0) AS out_qty,
            ISNULL(o.RCV_GOOD_QTY,0) AS good_qty, ISNULL(o.RCV_LOSS_QTY,0) AS loss_qty,
            CASE WHEN i.ORD_QTY>0 THEN CAST(ISNULL(o.ORD_OUT_QTY,0)*100.0/i.ORD_QTY AS DECIMAL(5,1)) ELSE 0 END AS pct
        FROM IWIPORDSTS i
        LEFT JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        WHERE i.CUSTOMER_CODE = '{cust}' AND i.CONFIRM_DATE >= '20260101'
            AND o.ORD_STATUS IS NOT NULL
        ORDER BY i.SO_NO, i.ORD_START_TIME
    """)
    for r in orders:
        r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
    for r in so_list:
        d1, d2 = str(r.get('start_dt','')), str(r.get('end_dt',''))
        r['start_fmt'] = f'{d1[:4]}-{d1[4:6]}-{d1[6:]}' if len(d1)==8 else d1
        r['end_fmt'] = f'{d2[:4]}-{d2[4:6]}-{d2[6:]}' if len(d2)==8 else d2
    return jsonify({'so_list': so_list, 'orders': orders, 'customer': cust})

@app.route('/api/order_progress')
def order_progress():
    cust = '20000052'
    rows = query(f"""
        SELECT i.SO_NO, i.CUST_PO_NO, o.ORDER_NO, o.FACTORY_CODE,
            o.MAT_CODE, o.FLOW_CODE, o.ORD_QTY, o.ORD_STATUS,
            ISNULL(o.ORD_OUT_QTY,0) AS out_qty,
            ISNULL(o.RCV_GOOD_QTY,0) AS good_qty,
            ISNULL(o.RCV_LOSS_QTY,0) AS loss_qty,
            o.ORD_IN_QTY,
            CASE WHEN o.ORD_QTY>0 THEN CAST(ISNULL(o.ORD_OUT_QTY,0)*100.0/o.ORD_QTY AS DECIMAL(5,1)) ELSE 0 END AS pct,
            i.ORD_START_TIME AS start_dt, i.ORD_END_TIME AS end_dt,
            o.LINE_CODE
        FROM IWIPORDSTS i
        INNER JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        WHERE i.CUSTOMER_CODE = '{cust}' AND i.CONFIRM_DATE >= '20260101'
            AND o.ORD_STATUS IN ('WAIT','CONFIRM','PROCESS','PLAN')
        ORDER BY
            CASE o.ORD_STATUS WHEN 'PROCESS' THEN 1 WHEN 'CONFIRM' THEN 2 WHEN 'WAIT' THEN 3 WHEN 'PLAN' THEN 4 ELSE 5 END,
            CAST(ISNULL(o.ORD_OUT_QTY,0)*100.0/CASE WHEN o.ORD_QTY>0 THEN o.ORD_QTY ELSE 1 END AS DECIMAL(5,1)) DESC
    """)
    for r in rows:
        r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
        d2 = str(r.get('end_dt', ''))
        r['end_fmt'] = f'{d2[:4]}-{d2[4:6]}-{d2[6:]}' if len(d2) == 8 else d2
        pct = float(r['pct'])
        if r['ORD_STATUS'] == 'PROCESS':
            r['stage'] = 'PRODUCING'
            r['stage_label'] = '생산중'
        elif r['ORD_STATUS'] == 'CONFIRM' and pct > 0:
            r['stage'] = 'PARTIAL'
            r['stage_label'] = '일부생산'
        elif r['ORD_STATUS'] in ('CONFIRM', 'WAIT') and pct >= 95:
            r['stage'] = 'NEAR_DONE'
            r['stage_label'] = '거의완료'
        elif r['ORD_STATUS'] == 'CONFIRM':
            r['stage'] = 'READY'
            r['stage_label'] = '확정대기'
        elif r['ORD_STATUS'] == 'WAIT' and pct > 0:
            r['stage'] = 'PARTIAL'
            r['stage_label'] = '일부생산'
        elif r['ORD_STATUS'] == 'WAIT':
            r['stage'] = 'WAITING'
            r['stage_label'] = '대기'
        else:
            r['stage'] = 'PLAN'
            r['stage_label'] = '계획'
    return jsonify(rows)

@app.route('/api/line_production')
def line_production():
    rows = query("""
        SELECT TOP 20 l.FACTORY_CODE, l.LINE_CODE, l.LINE_DESC, l.LINE_TYPE,
            SUM(h.QTY) AS total_qty,
            COUNT(DISTINCT CONVERT(VARCHAR, h.TRAN_TIME, 112)) AS work_days
        FROM MWIPLOTHIS h
        JOIN MWIPLINDEF l ON h.FACTORY_CODE=l.FACTORY_CODE AND h.LINE_CODE=l.LINE_CODE
        WHERE h.TRAN_CODE='CV' AND h.TRAN_TIME >= '2026-03-01' AND h.TRAN_TIME < '2026-03-30'
        GROUP BY l.FACTORY_CODE, l.LINE_CODE, l.LINE_DESC, l.LINE_TYPE
        ORDER BY SUM(h.QTY) DESC
    """)
    for r in rows:
        r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
        r['daily_avg'] = round(int(r['total_qty']) / max(int(r['work_days']),1))
    return jsonify(rows)

@app.route('/api/production_by_process')
def production_by_process():
    rows = query("""
        SELECT l.FACTORY_CODE, l.LINE_TYPE,
            CONVERT(VARCHAR, h.TRAN_TIME, 23) AS day,
            SUM(h.QTY) AS qty, COUNT(DISTINCT h.LOT_ID) AS lot_cnt
        FROM MWIPLOTHIS h
        JOIN MWIPLINDEF l ON h.FACTORY_CODE=l.FACTORY_CODE AND h.LINE_CODE=l.LINE_CODE
        WHERE h.TRAN_CODE='CV' AND h.TRAN_TIME >= '2026-03-01' AND h.TRAN_TIME < '2026-03-30'
        GROUP BY l.FACTORY_CODE, l.LINE_TYPE, CONVERT(VARCHAR, h.TRAN_TIME, 23)
        ORDER BY CONVERT(VARCHAR, h.TRAN_TIME, 23), l.FACTORY_CODE, l.LINE_TYPE
    """)
    for r in rows:
        r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
    return jsonify(rows)

@app.route('/api/process_summary')
def process_summary():
    rows = query("""
        SELECT l.FACTORY_CODE, l.LINE_TYPE,
            SUM(h.QTY) AS total_qty,
            COUNT(DISTINCT h.LOT_ID) AS lot_cnt,
            COUNT(DISTINCT CONVERT(VARCHAR, h.TRAN_TIME, 112)) AS work_days
        FROM MWIPLOTHIS h
        JOIN MWIPLINDEF l ON h.FACTORY_CODE=l.FACTORY_CODE AND h.LINE_CODE=l.LINE_CODE
        WHERE h.TRAN_CODE='CV' AND h.TRAN_TIME >= '2026-03-01' AND h.TRAN_TIME < '2026-03-30'
        GROUP BY l.FACTORY_CODE, l.LINE_TYPE
        ORDER BY l.FACTORY_CODE, SUM(h.QTY) DESC
    """)
    for r in rows:
        r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
        r['daily_avg'] = round(int(r['total_qty']) / max(int(r['work_days']),1))
    return jsonify(rows)

HTML = '''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MES 실시간 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI','맑은 고딕',sans-serif; background:#0f172a; color:#e2e8f0; }
.header { background:linear-gradient(135deg,#1e293b,#334155); padding:16px 24px; display:flex; justify-content:space-between; align-items:center; border-bottom:2px solid #3b82f6; }
.header h1 { font-size:22px; color:#60a5fa; }
.header .time { color:#94a3b8; font-size:13px; }
.refresh-btn { background:#3b82f6; color:#fff; border:none; padding:8px 16px; border-radius:6px; cursor:pointer; font-size:13px; }
.refresh-btn:hover { background:#2563eb; }
.tabs { display:flex; background:#1e293b; padding:0 24px; gap:4px; border-bottom:1px solid #334155; }
.tab { padding:12px 20px; cursor:pointer; color:#94a3b8; border-bottom:3px solid transparent; font-size:14px; font-weight:500; transition:all .2s; }
.tab:hover { color:#e2e8f0; }
.tab.active { color:#60a5fa; border-bottom-color:#3b82f6; }
.content { padding:20px 24px; display:none; }
.content.active { display:block; }
.grid { display:grid; gap:16px; }
.grid-3 { grid-template-columns:repeat(3,1fr); }
.grid-2 { grid-template-columns:repeat(2,1fr); }
.card { background:#1e293b; border-radius:12px; padding:20px; border:1px solid #334155; }
.card h3 { font-size:14px; color:#94a3b8; margin-bottom:12px; font-weight:500; }
.kpi { display:flex; gap:16px; margin-bottom:20px; }
.kpi-box { flex:1; background:#1e293b; border-radius:12px; padding:20px; text-align:center; border:1px solid #334155; }
.kpi-box .label { font-size:12px; color:#94a3b8; margin-bottom:4px; }
.kpi-box .value { font-size:28px; font-weight:700; }
.kpi-box .sub { font-size:11px; color:#64748b; margin-top:4px; }
.purple .value { color:#a78bfa; }
.green .value { color:#34d399; }
.orange .value { color:#fb923c; }
.blue .value { color:#60a5fa; }
.red .value { color:#f87171; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { background:#334155; color:#94a3b8; padding:10px 12px; text-align:left; font-weight:500; position:sticky; top:0; }
td { padding:8px 12px; border-bottom:1px solid #1e293b; }
tr:hover td { background:#334155; }
.badge { padding:3px 10px; border-radius:12px; font-size:11px; font-weight:600; display:inline-block; }
.badge-overdue { background:#991b1b; color:#fca5a5; }
.badge-high { background:#92400e; color:#fbbf24; }
.badge-medium { background:#854d0e; color:#fde68a; }
.badge-low { background:#14532d; color:#86efac; }
.badge-close { background:#14532d; color:#86efac; }
.badge-wait { background:#854d0e; color:#fde68a; }
.badge-confirm { background:#1e3a5f; color:#93c5fd; }
.badge-process { background:#14532d; color:#4ade80; }
.pbar { background:#334155; border-radius:4px; height:20px; overflow:hidden; position:relative; }
.pbar-fill { height:100%; border-radius:4px; transition:width .5s; }
.pbar-text { position:absolute; top:0; left:0; right:0; text-align:center; font-size:11px; line-height:20px; color:#fff; font-weight:600; }
.chart-container { height:300px; position:relative; }
.scroll-table { max-height:500px; overflow-y:auto; }
.num { text-align:right; font-variant-numeric:tabular-nums; }
.filter-btn { background:#334155; color:#94a3b8; border:1px solid #475569; padding:6px 14px; border-radius:6px; cursor:pointer; font-size:12px; transition:all .2s; }
.filter-btn:hover { background:#475569; color:#e2e8f0; }
.filter-btn.active { background:#3b82f6; color:#fff; border-color:#3b82f6; }
.pipeline { display:flex; align-items:center; gap:2px; }
.pipe-step { padding:4px 10px; font-size:10px; font-weight:600; border-radius:3px; white-space:nowrap; }
.pipe-step.done { background:#14532d; color:#4ade80; }
.pipe-step.active { background:#1e3a5f; color:#60a5fa; animation:pulse 1.5s infinite; }
.pipe-step.pending { background:#1e293b; color:#475569; }
.pipe-arrow { color:#475569; font-size:12px; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.6} }
.stage-badge { padding:4px 12px; border-radius:12px; font-size:11px; font-weight:600; }
.stage-producing { background:#1e3a5f; color:#60a5fa; }
.stage-partial { background:#854d0e; color:#fde68a; }
.stage-ready { background:#14532d; color:#86efac; }
.stage-waiting { background:#334155; color:#94a3b8; }
.stage-near_done { background:#14532d; color:#4ade80; }
.stage-plan { background:#1e293b; color:#64748b; }
@media (max-width:1024px) { .grid-3{grid-template-columns:1fr;} .grid-2{grid-template-columns:1fr;} .kpi{flex-wrap:wrap;} }
</style>
</head>
<body>
<div class="header">
    <h1>MES 실시간 대시보드</h1>
    <div style="display:flex;align-items:center;gap:16px;">
        <span class="time" id="updateTime"></span>
        <button class="refresh-btn" onclick="loadAll()">새로고침</button>
    </div>
</div>

<div class="tabs">
    <div class="tab active" onclick="switchTab(0)">생산 현황</div>
    <div class="tab" onclick="switchTab(1)">공정별 생산</div>
    <div class="tab" onclick="switchTab(2)">납기 리스크</div>
    <div class="tab" onclick="switchTab(3)">라인별 생산성</div>
    <div class="tab" onclick="switchTab(4)">비가동 분석</div>
    <div class="tab" onclick="switchTab(5)" style="color:#f472b6;">레어뷰티(20000052)</div>
</div>

<!-- Tab 0: 생산 현황 -->
<div class="content active" id="tab0">
    <div class="kpi" id="kpiArea"></div>
    <div class="grid grid-2" style="margin-top:16px;">
        <div class="card"><h3>일별 생산수량 추이 (3월)</h3><div class="chart-container"><canvas id="dailyChart"></canvas></div></div>
        <div class="card"><h3>거래처별 달성률 TOP 20</h3><div class="chart-container"><canvas id="custChart"></canvas></div></div>
    </div>
    <div class="card" style="margin-top:16px;"><h3>미완료 작업지시 (최근)</h3>
        <div class="scroll-table" id="orderTable"></div>
    </div>
</div>

<!-- Tab 1: 공정별 생산 -->
<div class="content" id="tab1">
    <div class="kpi" id="processKpi"></div>
    <div class="grid grid-2" style="margin-top:16px;">
        <div class="card"><h3>공장별 공정별 ���생산 (3월)</h3><div class="chart-container"><canvas id="processChart"></canvas></div></div>
        <div class="card"><h3>공정별 일별 생산 추이</h3><div class="chart-container"><canvas id="processDailyChart"></canvas></div></div>
    </div>
    <div class="card" style="margin-top:16px;"><h3>공장별 공정별 상세</h3>
        <div class="scroll-table" id="processTable"></div>
    </div>
</div>

<!-- Tab 2: 납기 리스크 -->
<div class="content" id="tab2">
    <div class="kpi" id="riskKpi"></div>
    <div class="card" style="margin-top:16px;"><h3>납기 리스크 수주 (달성률 98% 미만, 납기 4/5 이내)</h3>
        <div class="scroll-table" id="riskTable"></div>
    </div>
</div>

<!-- Tab 3: 라인별 생산성 -->
<div class="content" id="tab3">
    <div class="grid grid-2">
        <div class="card"><h3>라인별 총생산 TOP 20 (3월)</h3><div class="chart-container"><canvas id="lineChart"></canvas></div></div>
        <div class="card"><h3>라인별 일평균 생산</h3><div class="chart-container"><canvas id="lineAvgChart"></canvas></div></div>
    </div>
    <div class="card" style="margin-top:16px;"><h3>라인별 상세</h3>
        <div class="scroll-table" id="lineTable"></div>
    </div>
</div>

<!-- Tab 4: 비가동 분석 -->
<div class="content" id="tab4">
    <div class="grid grid-2">
        <div class="card"><h3>비가동 코드별 시간 TOP 15</h3><div class="chart-container"><canvas id="nwkChart"></canvas></div></div>
        <div class="card"><h3>비가동 상세</h3>
            <div class="scroll-table" id="nwkTable"></div>
        </div>
    </div>
</div>

<!-- Tab 5: 고객사(레어뷰티) -->
<div class="content" id="tab5">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
        <h2 style="color:#f472b6;font-size:20px;">Rare Beauty (레어뷰티) - 거래처 20000052</h2>
        <span style="color:#94a3b8;font-size:13px;">2026년 전체 수주 현황</span>
    </div>
    <div class="kpi" id="custKpi"></div>
    <div class="grid grid-2" style="margin-top:16px;">
        <div class="card"><h3>수주별 달성률</h3><div class="chart-container" style="height:400px;"><canvas id="custSoChart"></canvas></div></div>
        <div class="card"><h3>수주별 수량 (지시 vs 산출)</h3><div class="chart-container" style="height:400px;"><canvas id="custQtyChart"></canvas></div></div>
    </div>
    <div class="card" style="margin-top:16px;"><h3>진행현황 (미완료 작업지시)</h3>
        <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;" id="progressFilter">
            <button class="filter-btn active" onclick="filterProgress('ALL')">전체</button>
            <button class="filter-btn" onclick="filterProgress('PRODUCING')">생산중</button>
            <button class="filter-btn" onclick="filterProgress('PARTIAL')">일부생산</button>
            <button class="filter-btn" onclick="filterProgress('READY')">확정대기</button>
            <button class="filter-btn" onclick="filterProgress('WAITING')">대기</button>
        </div>
        <div class="scroll-table" style="max-height:600px;" id="progressTable"></div>
    </div>
    <div class="card" style="margin-top:16px;"><h3>수주(SO) 요약</h3>
        <div class="scroll-table" id="custSoTable"></div>
    </div>
    <div class="card" style="margin-top:16px;"><h3>작업지시 상세</h3>
        <div class="scroll-table" id="custOrdTable"></div>
    </div>
</div>

<script>
const FC = {'1100':'퍼플카운티','1200':'그린카운티','1300':'3공장'};
const COLORS = {퍼플카운티:'#a78bfa',그린카운티:'#34d399','3공장':'#fb923c'};
let charts = {};

function switchTab(n) {
    document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', i===n));
    document.querySelectorAll('.content').forEach((c,i) => c.classList.toggle('active', i===n));
}

function fmt(n) { return n ? Number(n).toLocaleString() : '0'; }
function pbarHtml(pct) {
    let c = pct >= 95 ? '#22c55e' : pct >= 70 ? '#eab308' : '#ef4444';
    return `<div class="pbar"><div class="pbar-fill" style="width:${Math.min(pct,100)}%;background:${c}"></div><div class="pbar-text">${pct}%</div></div>`;
}
function badgeHtml(status) {
    let map = {OVERDUE:'badge-overdue',HIGH:'badge-high',MEDIUM:'badge-medium',LOW:'badge-low',
               CLOSE:'badge-close',WAIT:'badge-wait',CONFIRM:'badge-confirm',PROCESS:'badge-process'};
    return `<span class="badge ${map[status]||''}">${status}</span>`;
}

async function loadAll() {
    document.getElementById('updateTime').textContent = '갱신: ' + new Date().toLocaleString('ko-KR');
    await Promise.all([loadOrderSummary(), loadDailyProd(), loadSoRisk(), loadCustomer(), loadLines(), loadNonwork(), loadProcess(), loadCustDetail(), loadProgress()]);
}

async function loadOrderSummary() {
    let data = await (await fetch('/api/order_summary')).json();
    let html = '';
    let totalWait=0, totalCfm=0, totalProc=0, totalClose=0;
    data.forEach(r => {
        totalWait += r.wait_cnt; totalCfm += r.cfm_cnt; totalProc += r.proc_cnt; totalClose += r.close_cnt;
    });
    html += `<div class="kpi-box orange"><div class="label">WAIT (대기)</div><div class="value">${fmt(totalWait)}</div><div class="sub">건</div></div>`;
    html += `<div class="kpi-box blue"><div class="label">CONFIRM (확정)</div><div class="value">${fmt(totalCfm)}</div><div class="sub">건</div></div>`;
    html += `<div class="kpi-box green"><div class="label">PROCESS (진행)</div><div class="value">${fmt(totalProc)}</div><div class="sub">건</div></div>`;
    html += `<div class="kpi-box purple"><div class="label">CLOSE (마감)</div><div class="value">${fmt(totalClose)}</div><div class="sub">건</div></div>`;
    document.getElementById('kpiArea').innerHTML = html;

    let tbl = `<table><thead><tr><th>공장</th><th class="num">WAIT</th><th class="num">WAIT수량</th><th class="num">CONFIRM</th><th class="num">CONFIRM수량</th><th class="num">PROCESS</th><th class="num">CLOSE</th></tr></thead><tbody>`;
    data.forEach(r => {
        tbl += `<tr><td>${r.factory_name}</td><td class="num">${fmt(r.wait_cnt)}</td><td class="num">${fmt(r.wait_qty)}</td><td class="num">${fmt(r.cfm_cnt)}</td><td class="num">${fmt(r.cfm_qty)}</td><td class="num">${fmt(r.proc_cnt)}</td><td class="num">${fmt(r.close_cnt)}</td></tr>`;
    });
    tbl += '</tbody></table>';
    document.getElementById('orderTable').innerHTML = tbl;
}

async function loadDailyProd() {
    let data = await (await fetch('/api/daily_production')).json();
    let days = [...new Set(data.map(r=>r.day))].sort();
    let datasets = {};
    data.forEach(r => {
        let fn = FC[r.FACTORY_CODE] || r.FACTORY_CODE;
        if(!datasets[fn]) datasets[fn] = {};
        datasets[fn][r.day] = r.qty;
    });
    if(charts.daily) charts.daily.destroy();
    charts.daily = new Chart(document.getElementById('dailyChart'), {
        type:'line',
        data: {
            labels: days.map(d=>d.substring(5)),
            datasets: Object.entries(datasets).map(([fn, vals]) => ({
                label: fn, data: days.map(d => vals[d]||0),
                borderColor: COLORS[fn]||'#60a5fa', backgroundColor: (COLORS[fn]||'#60a5fa')+'33',
                fill: true, tension: 0.3, pointRadius: 2
            }))
        },
        options: { responsive:true, maintainAspectRatio:false,
            scales:{ y:{ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}}, x:{ticks:{color:'#94a3b8',maxRotation:45},grid:{color:'#334155'}} },
            plugins:{legend:{labels:{color:'#e2e8f0'}}}
        }
    });
}

async function loadCustomer() {
    let data = await (await fetch('/api/customer_achieve')).json();
    if(charts.cust) charts.cust.destroy();
    charts.cust = new Chart(document.getElementById('custChart'), {
        type:'bar',
        data: {
            labels: data.map(r=>r.CUSTOMER_CODE),
            datasets: [
                { label:'지시수량', data:data.map(r=>r.total_qty), backgroundColor:'#334155' },
                { label:'산출수량', data:data.map(r=>r.total_out), backgroundColor:'#3b82f6' }
            ]
        },
        options: { responsive:true, maintainAspectRatio:false, indexAxis:'y',
            scales:{ x:{ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}}, y:{ticks:{color:'#94a3b8',font:{size:10}},grid:{color:'#334155'}} },
            plugins:{legend:{labels:{color:'#e2e8f0'}}}
        }
    });
}

async function loadSoRisk() {
    let data = await (await fetch('/api/so_risk')).json();
    let overdue = data.filter(r=>r.risk==='OVERDUE').length;
    let high = data.filter(r=>r.risk==='HIGH').length;
    let medium = data.filter(r=>r.risk==='MEDIUM').length;
    document.getElementById('riskKpi').innerHTML =
        `<div class="kpi-box red"><div class="label">OVERDUE (납기초과)</div><div class="value">${overdue}</div><div class="sub">건</div></div>` +
        `<div class="kpi-box orange"><div class="label">HIGH (긴급)</div><div class="value">${high}</div><div class="sub">건</div></div>` +
        `<div class="kpi-box blue"><div class="label">MEDIUM</div><div class="value">${medium}</div><div class="sub">건</div></div>` +
        `<div class="kpi-box green"><div class="label">총 리스크 수주</div><div class="value">${data.length}</div><div class="sub">건</div></div>`;

    let tbl = `<table><thead><tr><th>긴급도</th><th>수주번호</th><th>고객PO</th><th>거래처</th><th class="num">지시수량</th><th class="num">산출</th><th class="num">잔여</th><th>달성률</th><th>납기</th></tr></thead><tbody>`;
    data.forEach(r => {
        tbl += `<tr><td>${badgeHtml(r.risk)}</td><td>${r.SO_NO}</td><td>${(r.CUST_PO_NO||'').substring(0,30)}</td><td>${r.CUSTOMER_CODE||''}</td>`;
        tbl += `<td class="num">${fmt(r.total_qty)}</td><td class="num">${fmt(r.total_out)}</td><td class="num">${fmt(r.remaining)}</td>`;
        tbl += `<td>${pbarHtml(r.pct)}</td><td>${r.deadline_fmt}</td></tr>`;
    });
    tbl += '</tbody></table>';
    document.getElementById('riskTable').innerHTML = tbl;
}

async function loadLines() {
    let data = await (await fetch('/api/line_production')).json();
    if(charts.line) charts.line.destroy();
    charts.line = new Chart(document.getElementById('lineChart'), {
        type:'bar',
        data: {
            labels: data.map(r=>`${r.factory_name} ${r.LINE_CODE}`),
            datasets: [{ label:'총생산', data:data.map(r=>r.total_qty),
                backgroundColor: data.map(r=> COLORS[r.factory_name]||'#60a5fa') }]
        },
        options: { responsive:true, maintainAspectRatio:false, indexAxis:'y',
            scales:{ x:{ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}}, y:{ticks:{color:'#94a3b8',font:{size:10}},grid:{color:'#334155'}} },
            plugins:{legend:{display:false}}
        }
    });
    if(charts.lineAvg) charts.lineAvg.destroy();
    charts.lineAvg = new Chart(document.getElementById('lineAvgChart'), {
        type:'bar',
        data: {
            labels: data.map(r=>`${r.factory_name} ${r.LINE_CODE}`),
            datasets: [{ label:'일평균', data:data.map(r=>r.daily_avg),
                backgroundColor: data.map(r=> COLORS[r.factory_name]||'#60a5fa') }]
        },
        options: { responsive:true, maintainAspectRatio:false, indexAxis:'y',
            scales:{ x:{ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}}, y:{ticks:{color:'#94a3b8',font:{size:10}},grid:{color:'#334155'}} },
            plugins:{legend:{display:false}}
        }
    });

    let tbl = `<table><thead><tr><th>공장</th><th>라인</th><th>라인명</th><th>유형</th><th class="num">총생산</th><th class="num">가동일</th><th class="num">일평균</th></tr></thead><tbody>`;
    data.forEach(r => {
        tbl += `<tr><td>${r.factory_name}</td><td>${r.LINE_CODE}</td><td>${r.LINE_DESC||''}</td><td>${r.LINE_TYPE||''}</td>`;
        tbl += `<td class="num">${fmt(r.total_qty)}</td><td class="num">${r.work_days}</td><td class="num">${fmt(r.daily_avg)}</td></tr>`;
    });
    tbl += '</tbody></table>';
    document.getElementById('lineTable').innerHTML = tbl;
}

async function loadNonwork() {
    let data = await (await fetch('/api/nonwork_summary')).json();
    if(charts.nwk) charts.nwk.destroy();
    charts.nwk = new Chart(document.getElementById('nwkChart'), {
        type:'bar',
        data: {
            labels: data.map(r=>`${r.factory_name} ${r.code_name}`),
            datasets: [{ label:'비가동(시간)', data:data.map(r=>r.hours),
                backgroundColor: data.map(r=> r.NONWORK_CODE.startsWith('E2') ? '#ef4444' : '#60a5fa') }]
        },
        options: { responsive:true, maintainAspectRatio:false, indexAxis:'y',
            scales:{ x:{ticks:{color:'#94a3b8'},grid:{color:'#334155'}}, y:{ticks:{color:'#94a3b8',font:{size:10}},grid:{color:'#334155'}} },
            plugins:{legend:{display:false}}
        }
    });

    let tbl = `<table><thead><tr><th>공장</th><th>코드</th><th>코드명</th><th class="num">건수</th><th class="num">총시간(h)</th></tr></thead><tbody>`;
    data.forEach(r => {
        tbl += `<tr><td>${r.factory_name}</td><td>${r.NONWORK_CODE}</td><td>${r.code_name}</td>`;
        tbl += `<td class="num">${r.cnt}</td><td class="num">${r.hours}</td></tr>`;
    });
    tbl += '</tbody></table>';
    document.getElementById('nwkTable').innerHTML = tbl;
}

async function loadCustDetail() {
    let data = await (await fetch('/api/customer_detail')).json();
    let so = data.so_list, ord = data.orders;

    // KPI
    let totalQty=0, totalOut=0, totalGood=0, totalLoss=0, activeSo=0;
    so.forEach(r => {
        totalQty += Number(r.total_qty); totalOut += Number(r.total_out);
        totalGood += Number(r.good_qty); totalLoss += Number(r.loss_qty);
        if(Number(r.active) > 0) activeSo++;
    });
    let overallPct = totalQty > 0 ? (totalOut/totalQty*100).toFixed(1) : 0;
    let lossRate = totalOut > 0 ? (totalLoss/totalOut*100).toFixed(2) : 0;
    document.getElementById('custKpi').innerHTML =
        `<div class="kpi-box" style="border-color:#f472b6"><div class="label">총 수주</div><div class="value" style="color:#f472b6">${so.length}</div><div class="sub">건 (진행중 ${activeSo})</div></div>` +
        `<div class="kpi-box blue"><div class="label">총 지시수량</div><div class="value">${fmt(totalQty)}</div></div>` +
        `<div class="kpi-box green"><div class="label">총 산출수량</div><div class="value">${fmt(totalOut)}</div></div>` +
        `<div class="kpi-box purple"><div class="label">전체 달성률</div><div class="value">${overallPct}%</div></div>` +
        `<div class="kpi-box red"><div class="label">불량률</div><div class="value">${lossRate}%</div><div class="sub">${fmt(totalLoss)}개</div></div>`;

    // SO 달성률 차트
    let activeSos = so.filter(r => Number(r.total_qty) > 1000);
    if(charts.custSo) charts.custSo.destroy();
    charts.custSo = new Chart(document.getElementById('custSoChart'), {
        type:'bar',
        data: {
            labels: activeSos.map(r => (r.CUST_PO_NO||r.SO_NO).substring(0,25)),
            datasets: [{
                label:'달성률(%)', data: activeSos.map(r => Number(r.pct)),
                backgroundColor: activeSos.map(r => Number(r.pct)>=95?'#22c55e':Number(r.pct)>=70?'#eab308':'#ef4444')
            }]
        },
        options: { responsive:true, maintainAspectRatio:false, indexAxis:'y',
            scales:{ x:{max:120,ticks:{color:'#94a3b8',callback:v=>v+'%'},grid:{color:'#334155'}}, y:{ticks:{color:'#94a3b8',font:{size:9}},grid:{color:'#334155'}} },
            plugins:{legend:{display:false}}
        }
    });

    // SO 수량 차트
    if(charts.custQty) charts.custQty.destroy();
    charts.custQty = new Chart(document.getElementById('custQtyChart'), {
        type:'bar',
        data: {
            labels: activeSos.map(r => (r.CUST_PO_NO||r.SO_NO).substring(0,25)),
            datasets: [
                { label:'지시수량', data: activeSos.map(r=>Number(r.total_qty)), backgroundColor:'#334155' },
                { label:'산출수량', data: activeSos.map(r=>Number(r.total_out)), backgroundColor:'#f472b6' }
            ]
        },
        options: { responsive:true, maintainAspectRatio:false, indexAxis:'y',
            scales:{ x:{ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}}, y:{ticks:{color:'#94a3b8',font:{size:9}},grid:{color:'#334155'}} },
            plugins:{legend:{labels:{color:'#e2e8f0'}}}
        }
    });

    // SO 요약 테이블
    let tbl = `<table><thead><tr><th>수주번호</th><th>프로젝트/PO</th><th class="num">지시수량</th><th class="num">산출</th><th class="num">양품</th><th class="num">불량</th><th>달성률</th><th class="num">마감</th><th class="num">진행</th><th>시작일</th><th>납기</th></tr></thead><tbody>`;
    so.forEach(r => {
        let p = Number(r.pct);
        tbl += `<tr><td>${r.SO_NO}</td><td>${(r.CUST_PO_NO||'').substring(0,35)}</td>`;
        tbl += `<td class="num">${fmt(r.total_qty)}</td><td class="num">${fmt(r.total_out)}</td>`;
        tbl += `<td class="num">${fmt(r.good_qty)}</td><td class="num">${fmt(r.loss_qty)}</td>`;
        tbl += `<td>${pbarHtml(p)}</td>`;
        tbl += `<td class="num">${r.closed}</td><td class="num">${r.active}</td>`;
        tbl += `<td>${r.start_fmt}</td><td>${r.end_fmt}</td></tr>`;
    });
    tbl += '</tbody></table>';
    document.getElementById('custSoTable').innerHTML = tbl;

    // 지시 상세 테이블
    let tbl2 = `<table><thead><tr><th>수주</th><th>공장</th><th>지시번호</th><th>자재코드</th><th>라인</th><th class="num">지시수량</th><th class="num">산출</th><th class="num">양품</th><th class="num">불량</th><th>달성률</th><th>상태</th><th>시작</th><th>납기</th></tr></thead><tbody>`;
    ord.forEach(r => {
        let p = Number(r.pct);
        let st = r.ORD_STATUS||'';
        let d1 = String(r.ORD_START_TIME||''), d2 = String(r.ORD_END_TIME||'');
        let d1f = d1.length===8 ? d1.substring(4,6)+'/'+d1.substring(6) : d1;
        let d2f = d2.length===8 ? d2.substring(4,6)+'/'+d2.substring(6) : d2;
        tbl2 += `<tr><td>${r.SO_NO}</td><td>${r.factory_name}</td><td>${r.ORDER_NO}</td><td>${r.MAT_CODE}</td><td>${r.LINE_CODE}</td>`;
        tbl2 += `<td class="num">${fmt(r.ORD_QTY)}</td><td class="num">${fmt(r.out_qty)}</td>`;
        tbl2 += `<td class="num">${fmt(r.good_qty)}</td><td class="num">${fmt(r.loss_qty)}</td>`;
        tbl2 += `<td>${pbarHtml(p)}</td><td>${badgeHtml(st)}</td>`;
        tbl2 += `<td>${d1f}</td><td>${d2f}</td></tr>`;
    });
    tbl2 += '</tbody></table>';
    document.getElementById('custOrdTable').innerHTML = tbl2;
}

let progressData = [];
function filterProgress(stage) {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b.textContent === {ALL:'전체',PRODUCING:'생산중',PARTIAL:'일부생산',READY:'확정대기',WAITING:'대기'}[stage]));
    renderProgress(stage === 'ALL' ? progressData : progressData.filter(r => r.stage === stage));
}

function pipelineHtml(status, pct) {
    const steps = [
        {id:'PLAN', label:'계획'},
        {id:'WAIT', label:'대기'},
        {id:'CONFIRM', label:'확정'},
        {id:'PROCESS', label:'생산'},
        {id:'OUTPUT', label:'산출'}
    ];
    const statusOrder = {PLAN:0, WAIT:1, CONFIRM:2, PROCESS:3, CLOSE:4};
    const currentIdx = statusOrder[status] ?? -1;
    const hasOutput = pct > 0;
    let html = '<div class="pipeline">';
    steps.forEach((s, i) => {
        let cls = 'pending';
        if(i < currentIdx) cls = 'done';
        else if(i === currentIdx) cls = 'active';
        if(s.id === 'OUTPUT' && hasOutput) cls = pct >= 95 ? 'done' : 'active';
        if(i > 0) html += '<span class="pipe-arrow">▸</span>';
        html += `<span class="pipe-step ${cls}">${s.label}</span>`;
    });
    html += '</div>';
    return html;
}

function renderProgress(data) {
    let tbl = `<table><thead><tr><th>수주</th><th>지시번호</th><th>공장</th><th>자재</th><th class="num">지시수량</th><th class="num">산출</th><th>달성률</th><th>진행단계</th><th>파이프라인</th><th>납기</th></tr></thead><tbody>`;
    data.forEach(r => {
        let p = Number(r.pct);
        tbl += `<tr><td>${r.SO_NO}</td><td>${r.ORDER_NO}</td><td>${r.factory_name}</td><td>${r.MAT_CODE}</td>`;
        tbl += `<td class="num">${fmt(r.ORD_QTY)}</td><td class="num">${fmt(r.out_qty)}</td>`;
        tbl += `<td style="min-width:100px">${pbarHtml(p)}</td>`;
        tbl += `<td><span class="stage-badge stage-${r.stage.toLowerCase()}">${r.stage_label}</span></td>`;
        tbl += `<td>${pipelineHtml(r.ORD_STATUS, p)}</td>`;
        tbl += `<td>${r.end_fmt}</td></tr>`;
    });
    tbl += '</tbody></table>';
    document.getElementById('progressTable').innerHTML = tbl;
}

async function loadProgress() {
    progressData = await (await fetch('/api/order_progress')).json();
    renderProgress(progressData);
    // update progress KPI counts in filter buttons
    let counts = {ALL:progressData.length, PRODUCING:0, PARTIAL:0, READY:0, WAITING:0, NEAR_DONE:0, PLAN:0};
    progressData.forEach(r => { if(counts[r.stage] !== undefined) counts[r.stage]++; });
    let btns = document.querySelectorAll('.filter-btn');
    let labels = {ALL:`전체 (${counts.ALL})`, PRODUCING:`생산중 (${counts.PRODUCING})`, PARTIAL:`일부생산 (${counts.PARTIAL})`, READY:`확정대기 (${counts.READY})`, WAITING:`대기 (${counts.WAITING})`};
    btns.forEach(b => {
        let key = Object.keys(labels).find(k => b.textContent.startsWith({ALL:'전체',PRODUCING:'생산중',PARTIAL:'일부생산',READY:'확정대기',WAITING:'대기'}[k]));
        if(key) b.textContent = labels[key];
    });
}

const PROC_COLORS = {BULK:'#a78bfa',FILLING:'#60a5fa',TABLET:'#f472b6',PACKING:'#34d399',BONDING:'#fb923c'};
const PROC_NAMES = {BULK:'제조(벌크)',FILLING:'충진',TABLET:'타정',PACKING:'포장',BONDING:'본딩'};

async function loadProcess() {
    let [summary, daily] = await Promise.all([
        (await fetch('/api/process_summary')).json(),
        (await fetch('/api/production_by_process')).json()
    ]);

    // KPI - 공정별 총합
    let byType = {};
    summary.forEach(r => {
        if(!byType[r.LINE_TYPE]) byType[r.LINE_TYPE] = {qty:0,lots:0};
        byType[r.LINE_TYPE].qty += Number(r.total_qty);
        byType[r.LINE_TYPE].lots += Number(r.lot_cnt);
    });
    let khtml = '';
    ['BULK','FILLING','TABLET','PACKING','BONDING'].forEach(t => {
        if(byType[t]) {
            let col = PROC_COLORS[t].replace('#','');
            khtml += `<div class="kpi-box" style="border-color:${PROC_COLORS[t]}"><div class="label">${PROC_NAMES[t]||t}</div><div class="value" style="color:${PROC_COLORS[t]}">${fmt(byType[t].qty)}</div><div class="sub">${fmt(byType[t].lots)} LOT</div></div>`;
        }
    });
    document.getElementById('processKpi').innerHTML = khtml;

    // 공장별 공정별 stacked bar
    let factories = [...new Set(summary.map(r=>r.factory_name))];
    let types = [...new Set(summary.map(r=>r.LINE_TYPE))];
    if(charts.proc) charts.proc.destroy();
    charts.proc = new Chart(document.getElementById('processChart'), {
        type:'bar',
        data: {
            labels: factories,
            datasets: types.map(t => ({
                label: PROC_NAMES[t]||t,
                data: factories.map(f => {
                    let found = summary.find(r=>r.factory_name===f && r.LINE_TYPE===t);
                    return found ? Number(found.total_qty) : 0;
                }),
                backgroundColor: PROC_COLORS[t]||'#64748b'
            }))
        },
        options: { responsive:true, maintainAspectRatio:false,
            scales:{ y:{stacked:true,ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}}, x:{stacked:true,ticks:{color:'#94a3b8'},grid:{color:'#334155'}} },
            plugins:{legend:{labels:{color:'#e2e8f0'}}}
        }
    });

    // 일별 공정별 추이 (전체 공장 합산)
    let days = [...new Set(daily.map(r=>r.day))].sort();
    let dailyByType = {};
    daily.forEach(r => {
        if(!dailyByType[r.LINE_TYPE]) dailyByType[r.LINE_TYPE] = {};
        dailyByType[r.LINE_TYPE][r.day] = (dailyByType[r.LINE_TYPE][r.day]||0) + Number(r.qty);
    });
    if(charts.procDaily) charts.procDaily.destroy();
    charts.procDaily = new Chart(document.getElementById('processDailyChart'), {
        type:'line',
        data: {
            labels: days.map(d=>d.substring(5)),
            datasets: Object.entries(dailyByType).map(([t, vals]) => ({
                label: PROC_NAMES[t]||t, data: days.map(d => vals[d]||0),
                borderColor: PROC_COLORS[t]||'#64748b', backgroundColor: (PROC_COLORS[t]||'#64748b')+'33',
                fill: true, tension: 0.3, pointRadius: 1
            }))
        },
        options: { responsive:true, maintainAspectRatio:false,
            scales:{ y:{stacked:true,ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}}, x:{ticks:{color:'#94a3b8',maxRotation:45},grid:{color:'#334155'}} },
            plugins:{legend:{labels:{color:'#e2e8f0'}}}
        }
    });

    // 테이블
    let tbl = `<table><thead><tr><th>공장</th><th>공정</th><th class="num">총생산수량</th><th class="num">LOT수</th><th class="num">가동일수</th><th class="num">일평균</th></tr></thead><tbody>`;
    summary.forEach(r => {
        tbl += `<tr><td>${r.factory_name}</td><td><span style="color:${PROC_COLORS[r.LINE_TYPE]||'#fff'}">${PROC_NAMES[r.LINE_TYPE]||r.LINE_TYPE}</span></td>`;
        tbl += `<td class="num">${fmt(r.total_qty)}</td><td class="num">${fmt(r.lot_cnt)}</td><td class="num">${r.work_days}</td><td class="num">${fmt(r.daily_avg)}</td></tr>`;
    });
    tbl += '</tbody></table>';
    document.getElementById('processTable').innerHTML = tbl;
}

loadAll();
setInterval(loadAll, 60000);
</script>
</body>
</html>'''

if __name__ == '__main__':
    print('Dashboard: http://localhost:5000')
    app.run(host='0.0.0.0', port=5000, debug=False)
