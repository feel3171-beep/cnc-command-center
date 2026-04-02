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

# IWIPORDSTS는 인터페이스 로그 → ORDER_NO당 최신 IF_SQ만 사용
LATEST_I = """(SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER(PARTITION BY FACTORY_CODE, ORDER_NO ORDER BY IF_SQ DESC) AS _rn
    FROM IWIPORDSTS WHERE SO_NO IS NOT NULL AND SO_NO <> ''
) _t WHERE _rn=1)"""

# 26년 확정 + 이월 진행중 (CONFIRM_DATE 무관하게 아직 활성인 건 포함)
# 완료 판단: CLOSE 또는 산출률>=95%
DATE_OR_ACTIVE = "(i.CONFIRM_DATE >= '20260101' OR (o.ORD_STATUS IN ('PLAN','WAIT','CONFIRM','PROCESS') AND (o.ORD_QTY=0 OR o.ORD_OUT_QTY < o.ORD_QTY*0.95)))"

@app.route('/')
def index():
    return render_template_string(HTML)

# ── 거래처별 변경이력 ──
@app.route('/api/customer_changes/<cust_code>')
def customer_changes(cust_code):
    rows = query(f"""
        SELECT
            f.FACTORY_CODE, f.ORDER_NO, f.SO_NO,
            f.ORD_QTY AS orig_qty, l.ORD_QTY AS new_qty,
            f.ORD_END_TIME AS orig_end, l.ORD_END_TIME AS new_end,
            f.ORD_START_TIME AS orig_start, l.ORD_START_TIME AS new_start,
            l.CONFIRM_DATE,
            o.ORD_STATUS,
            CASE WHEN f.ORD_END_TIME<>l.ORD_END_TIME AND l.ORD_END_TIME<f.ORD_END_TIME THEN 1 ELSE 0 END AS deadline_forward,
            CASE WHEN f.ORD_END_TIME<>l.ORD_END_TIME AND l.ORD_END_TIME>f.ORD_END_TIME THEN 1 ELSE 0 END AS deadline_delay,
            CASE WHEN f.ORD_QTY<>l.ORD_QTY THEN 1 ELSE 0 END AS qty_change,
            CASE WHEN f.ORD_START_TIME<>l.ORD_START_TIME THEN 1 ELSE 0 END AS start_change
        FROM (SELECT *, ROW_NUMBER() OVER(PARTITION BY FACTORY_CODE, ORDER_NO ORDER BY IF_SQ ASC) AS rn
              FROM IWIPORDSTS WHERE SO_NO IS NOT NULL AND SO_NO<>'' AND CUSTOMER_CODE='{cust_code}') f
        JOIN (SELECT *, ROW_NUMBER() OVER(PARTITION BY FACTORY_CODE, ORDER_NO ORDER BY IF_SQ DESC) AS rn
              FROM IWIPORDSTS WHERE SO_NO IS NOT NULL AND SO_NO<>'' AND CUSTOMER_CODE='{cust_code}') l
            ON f.FACTORY_CODE=l.FACTORY_CODE AND f.ORDER_NO=l.ORDER_NO
        LEFT JOIN MWIPORDSTS o ON l.FACTORY_CODE=o.FACTORY_CODE AND l.ORDER_NO=o.ORDER_NO
        WHERE f.rn=1 AND l.rn=1
            AND l.CONFIRM_DATE>='20260101'
            AND (f.ORD_QTY<>l.ORD_QTY OR f.ORD_END_TIME<>l.ORD_END_TIME OR f.ORD_START_TIME<>l.ORD_START_TIME)
        ORDER BY l.CONFIRM_DATE DESC
    """)
    return jsonify(rows)

# ── KPI 공장별 요약 ──
@app.route('/api/kpi_factory')
def kpi_factory():
    month = request.args.get('month', '')
    if month and len(month) == 7:
        ym = month.replace('-', '')
        date_filter = f"AND (i.CONFIRM_DATE >= '{ym}01' AND i.CONFIRM_DATE < '{ym}32')"
    else:
        date_filter = f"AND {DATE_OR_ACTIVE}"
    rows = query(f"""
        SELECT i.FACTORY_CODE,
            COUNT(DISTINCT i.CUSTOMER_CODE) AS cust_cnt,
            COUNT(DISTINCT i.SO_NO) AS so_cnt,
            SUM(i.ORD_QTY) AS so_qty,
            SUM(ISNULL(o.ORD_QTY,0)) AS ord_qty,
            SUM(ISNULL(o.ORD_OUT_QTY,0)) AS total_out,
            CASE WHEN SUM(i.ORD_QTY)>0 THEN CAST(SUM(ISNULL(o.ORD_OUT_QTY,0))*100.0/SUM(i.ORD_QTY) AS DECIMAL(5,1)) ELSE 0 END AS pct,
            SUM(CASE WHEN o.ORD_STATUS='CLOSE' OR (o.ORD_QTY>0 AND o.ORD_OUT_QTY>=o.ORD_QTY*0.95) THEN 1 ELSE 0 END) AS closed_cnt,
            SUM(CASE WHEN o.ORD_STATUS IN ('WAIT','CONFIRM','PROCESS') AND (o.ORD_QTY=0 OR o.ORD_OUT_QTY<o.ORD_QTY*0.95) THEN 1 ELSE 0 END) AS active_cnt
        FROM {LATEST_I} i
        INNER JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        WHERE 1=1 {date_filter}
        GROUP BY i.FACTORY_CODE
        ORDER BY i.FACTORY_CODE
    """)
    return jsonify(rows)

# ── 거래처 목록 (with 이름) ──
@app.route('/api/customers')
def customers():
    month = request.args.get('month', '')  # '' = 누계, '2026-01' etc
    if month and len(month) == 7:
        ym = month.replace('-', '')
        date_filter = f"AND (i.CONFIRM_DATE >= '{ym}01' AND i.CONFIRM_DATE < '{ym}32')"
    else:
        date_filter = f"AND {DATE_OR_ACTIVE}"
    rows = query(f"""
        SELECT i.CUSTOMER_CODE,
            MIN(v.VENDOR_DESC) AS cust_name,
            COUNT(DISTINCT i.SO_NO) AS so_cnt,
            SUM(i.ORD_QTY) AS so_qty,
            SUM(ISNULL(o.ORD_QTY,0)) AS ord_qty,
            SUM(ISNULL(o.ORD_OUT_QTY,0)) AS total_out,
            CASE WHEN SUM(i.ORD_QTY)>0 THEN CAST(SUM(ISNULL(o.ORD_OUT_QTY,0))*100.0/SUM(i.ORD_QTY) AS DECIMAL(5,1)) ELSE 0 END AS pct,
            SUM(CASE WHEN o.ORD_STATUS='CLOSE' OR (o.ORD_QTY>0 AND o.ORD_OUT_QTY>=o.ORD_QTY*0.95) THEN 1 ELSE 0 END) AS closed_cnt,
            SUM(CASE WHEN o.ORD_STATUS IN ('WAIT','CONFIRM','PROCESS') AND (o.ORD_QTY=0 OR o.ORD_OUT_QTY<o.ORD_QTY*0.95) THEN 1 ELSE 0 END) AS active_cnt
        FROM {LATEST_I} i
        INNER JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        LEFT JOIN MWIPVENDEF v ON i.CUSTOMER_CODE=v.VENDOR_CODE AND i.FACTORY_CODE=v.FACTORY_CODE
        WHERE 1=1 {date_filter}
        GROUP BY i.CUSTOMER_CODE
        ORDER BY SUM(i.ORD_QTY) DESC
    """)
    return jsonify(rows)

# ── 납기 리스크 전체 ──
@app.route('/api/delivery_risk')
def delivery_risk():
    today = datetime.now().strftime('%Y%m%d')
    rows = query(f"""
        SELECT i.SO_NO, i.CUST_PO_NO, i.CUSTOMER_CODE,
            MIN(v.VENDOR_DESC) AS cust_name,
            COUNT(DISTINCT i.ORDER_NO) AS ord_cnt,
            SUM(i.ORD_QTY) AS so_qty,
            SUM(ISNULL(o.ORD_QTY,0)) AS ord_qty,
            SUM(ISNULL(o.ORD_OUT_QTY,0)) AS total_out,
            SUM(i.ORD_QTY)-SUM(ISNULL(o.ORD_OUT_QTY,0)) AS remaining,
            MAX(i.ORD_END_TIME) AS deadline,
            CASE WHEN SUM(i.ORD_QTY)>0 THEN CAST(SUM(ISNULL(o.ORD_OUT_QTY,0))*100.0/SUM(i.ORD_QTY) AS DECIMAL(5,1)) ELSE 0 END AS pct
        FROM {LATEST_I} i
        INNER JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        LEFT JOIN MWIPVENDEF v ON i.CUSTOMER_CODE=v.VENDOR_CODE AND i.FACTORY_CODE=v.FACTORY_CODE
        WHERE {DATE_OR_ACTIVE}
        GROUP BY i.SO_NO, i.CUST_PO_NO, i.CUSTOMER_CODE
        HAVING SUM(ISNULL(o.ORD_OUT_QTY,0)) < SUM(i.ORD_QTY)*0.98
        ORDER BY MAX(i.ORD_END_TIME), SUM(i.ORD_QTY) DESC
    """)
    for r in rows:
        dl = str(r['deadline'])
        pct = float(r['pct'])
        next_month = (datetime.now().replace(day=1) + timedelta(days=32)).replace(day=1).strftime('%Y%m%d')
        if dl < today and pct < 95:
            r['risk'] = 'OVERDUE'
        elif dl <= next_month and pct < 50:
            r['risk'] = 'HIGH'
        elif dl < today:
            r['risk'] = 'MEDIUM'
        elif pct < 30:
            r['risk'] = 'MEDIUM'
        else:
            r['risk'] = 'LOW'
        r['deadline_fmt'] = f'{dl[:4]}-{dl[4:6]}-{dl[6:]}' if len(dl) >= 8 else dl
    return jsonify(rows)

# ── 납기 준수율 (실제 완료일 기반) ──
@app.route('/api/delivery_compliance')
def delivery_compliance():
    today = datetime.now().strftime('%Y%m%d')
    rows = query(f"""
        SELECT i.CUSTOMER_CODE, MIN(v.VENDOR_DESC) AS cust_name,
            i.SO_NO, MAX(i.CUST_PO_NO) AS CUST_PO_NO,
            MAX(i.ORD_END_TIME) AS deadline,
            MIN(i.ORD_START_TIME) AS plan_start,
            MIN(i.CONFIRM_DATE) AS confirm_date,
            SUM(i.ORD_QTY) AS so_qty,
            SUM(ISNULL(o.ORD_OUT_QTY,0)) AS total_out,
            CASE WHEN SUM(i.ORD_QTY)>0 THEN CAST(SUM(ISNULL(o.ORD_OUT_QTY,0))*100.0/SUM(i.ORD_QTY) AS DECIMAL(5,1)) ELSE 0 END AS pct,
            COUNT(*) AS total_cnt,
            SUM(CASE WHEN o.ORD_STATUS='CLOSE' OR (o.ORD_QTY>0 AND o.ORD_OUT_QTY>=o.ORD_QTY*0.95) THEN 1 ELSE 0 END) AS closed_cnt,
            SUM(CASE WHEN o.ORD_STATUS IN ('PLAN','WAIT') AND (o.ORD_QTY=0 OR o.ORD_OUT_QTY<o.ORD_QTY*0.95) THEN 1 ELSE 0 END) AS idle_cnt,
            CONVERT(VARCHAR(8), MAX(CASE WHEN o.ORD_STATUS='CLOSE' OR (o.ORD_QTY>0 AND o.ORD_OUT_QTY>=o.ORD_QTY*0.95) THEN o.ORD_END_TIME END), 112) AS actual_done,
            CONVERT(VARCHAR(8), MIN(o.ORD_START_TIME), 112) AS actual_start
        FROM {LATEST_I} i
        INNER JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        LEFT JOIN MWIPVENDEF v ON i.CUSTOMER_CODE=v.VENDOR_CODE AND i.FACTORY_CODE=v.FACTORY_CODE
        WHERE {DATE_OR_ACTIVE}
        GROUP BY i.CUSTOMER_CODE, i.SO_NO
        ORDER BY i.CUSTOMER_CODE, MAX(i.ORD_END_TIME)
    """)
    for r in rows:
        dl = str(r.get('deadline','') or '')
        ps = str(r.get('plan_start','') or '')
        cd = str(r.get('confirm_date','') or '')
        ad = str(r.get('actual_done','') or '')
        ast = str(r.get('actual_start','') or '')
        pct = float(r['pct'])
        closed = int(r['closed_cnt'])
        total = int(r['total_cnt'])
        idle = int(r['idle_cnt'])
        # 확정→납기 여유일 (수주 후 납기까지 얼마나 여유가 있었나)
        notice_days = 0
        if len(cd)==8 and len(dl)==8:
            try: notice_days = (datetime.strptime(dl,'%Y%m%d') - datetime.strptime(cd,'%Y%m%d')).days
            except: pass
        # 착수지연일: 실제시작 - 계획시작
        start_delay = 0
        if len(ast)==8 and len(ps)==8:
            try: start_delay = (datetime.strptime(ast,'%Y%m%d') - datetime.strptime(ps,'%Y%m%d')).days
            except: pass
        r['notice_days'] = notice_days
        r['start_delay'] = start_delay
        # 분류 로직
        is_tight = notice_days <= 5  # 확정~납기 5일 이내 = 납기촉박
        is_late_start = start_delay >= 3  # 착수가 계획보다 3일 이상 지연
        if closed == total:
            if len(ad)==8 and len(dl)==8 and ad <= dl:
                r['compliance'] = 'ON_TIME'
                r['label'] = '납기준수'
            elif len(ad)==8 and len(dl)==8:
                late_days = 0
                try: late_days = (datetime.strptime(ad,'%Y%m%d') - datetime.strptime(dl,'%Y%m%d')).days
                except: pass
                r['late_days'] = late_days
                if is_tight:
                    r['compliance'] = 'LATE_TIGHT'
                    r['label'] = '지연(납기촉박)'
                elif is_late_start:
                    r['compliance'] = 'LATE_START'
                    r['label'] = '지연(착수지연)'
                else:
                    r['compliance'] = 'LATE_PROCESS'
                    r['label'] = '지연(생산지연)'
            else:
                r['compliance'] = 'ON_TIME'
                r['label'] = '납기준수'
        elif dl < today:
            if is_tight:
                r['compliance'] = 'OVERDUE_TIGHT'
                r['label'] = '초과(납기촉박)'
            elif is_late_start or idle > total * 0.5:
                r['compliance'] = 'OVERDUE_IDLE'
                r['label'] = '초과(착수지연)'
            else:
                r['compliance'] = 'OVERDUE_PROCESS'
                r['label'] = '초과(생산지연)'
        else:
            r['compliance'] = 'PENDING'
            r['label'] = '진행중'
        r['dl_fmt'] = f'{dl[:4]}-{dl[4:6]}-{dl[6:]}' if len(dl)==8 else dl
        r['ad_fmt'] = f'{ad[:4]}-{ad[4:6]}-{ad[6:]}' if len(ad)==8 else '-'
    # 거래처별 집계
    cmap = {}
    for r in rows:
        cc = r['CUSTOMER_CODE']
        if cc not in cmap:
            cmap[cc] = {'CUSTOMER_CODE':cc, 'cust_name':r['cust_name'],
                'total':0, 'on_time':0, 'late_tight':0, 'late_start':0, 'late_process':0,
                'overdue_tight':0, 'overdue_idle':0, 'overdue_process':0, 'pending':0}
        c = cmap[cc]
        c['total'] += 1
        cm = r['compliance']
        if cm=='ON_TIME': c['on_time']+=1
        elif cm=='LATE_TIGHT': c['late_tight']+=1
        elif cm=='LATE_START': c['late_start']+=1
        elif cm=='LATE_PROCESS': c['late_process']+=1
        elif cm=='OVERDUE_TIGHT': c['overdue_tight']+=1
        elif cm=='OVERDUE_IDLE': c['overdue_idle']+=1
        elif cm=='OVERDUE_PROCESS': c['overdue_process']+=1
        elif cm=='PENDING': c['pending']+=1
    custs = sorted(cmap.values(), key=lambda x: x['total'], reverse=True)
    for c in custs:
        done = c['on_time']+c['late_tight']+c['late_start']+c['late_process']+c['overdue_tight']+c['overdue_idle']+c['overdue_process']
        c['late_total'] = c['late_tight']+c['late_start']+c['late_process']+c['overdue_tight']+c['overdue_idle']+c['overdue_process']
        c['compliance_rate'] = round(c['on_time']/done*100,1) if done>0 else 100.0
        c['tight_cnt'] = c['late_tight']+c['overdue_tight']
        c['process_cnt'] = c['late_start']+c['late_process']+c['overdue_idle']+c['overdue_process']
    return jsonify({'customers': custs, 'details': rows})

# ── 고객사 상세 ──
@app.route('/api/customer_detail/<cust_code>')
def customer_detail(cust_code):
    today = datetime.now().strftime('%Y%m%d')
    info = query(f"""
        SELECT TOP 1 v.VENDOR_CODE, v.VENDOR_DESC
        FROM MWIPVENDEF v WHERE v.VENDOR_CODE='{cust_code}'
    """)
    so_list = query(f"""
        SELECT i.SO_NO, i.CUST_PO_NO,
            COUNT(DISTINCT i.ORDER_NO) AS ord_cnt,
            SUM(i.ORD_QTY) AS so_qty,
            SUM(ISNULL(o.ORD_QTY,0)) AS ord_qty,
            SUM(ISNULL(o.ORD_OUT_QTY,0)) AS total_out,
            SUM(ISNULL(o.RCV_GOOD_QTY,0)) AS good_qty,
            SUM(ISNULL(o.RCV_LOSS_QTY,0)) AS loss_qty,
            MIN(i.ORD_START_TIME) AS start_dt,
            MAX(i.ORD_END_TIME) AS end_dt,
            SUM(CASE WHEN o.ORD_STATUS='CLOSE' OR (o.ORD_QTY>0 AND o.ORD_OUT_QTY>=o.ORD_QTY*0.95) THEN 1 ELSE 0 END) AS closed,
            SUM(CASE WHEN o.ORD_STATUS IN ('WAIT','CONFIRM','PROCESS') AND (o.ORD_QTY=0 OR o.ORD_OUT_QTY<o.ORD_QTY*0.95) THEN 1 ELSE 0 END) AS active,
            CASE WHEN SUM(i.ORD_QTY)>0 THEN CAST(SUM(ISNULL(o.ORD_OUT_QTY,0))*100.0/SUM(i.ORD_QTY) AS DECIMAL(5,1)) ELSE 0 END AS pct
        FROM {LATEST_I} i
        INNER JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        WHERE i.CUSTOMER_CODE='{cust_code}' AND {DATE_OR_ACTIVE}
        GROUP BY i.SO_NO, i.CUST_PO_NO
        ORDER BY MAX(i.ORD_END_TIME) DESC
    """)
    for r in so_list:
        d1, d2 = str(r.get('start_dt','')), str(r.get('end_dt',''))
        r['start_fmt'] = f'{d1[:4]}-{d1[4:6]}-{d1[6:]}' if len(d1)==8 else d1
        r['end_fmt'] = f'{d2[:4]}-{d2[4:6]}-{d2[6:]}' if len(d2)==8 else d2
        pct = float(r['pct'])
        dl = str(r.get('end_dt',''))
        if dl < today and pct < 95: r['risk'] = 'OVERDUE'
        elif dl <= today and pct >= 95: r['risk'] = 'OK'
        elif pct >= 95: r['risk'] = 'OK'
        else: r['risk'] = 'ACTIVE'
    orders = query(f"""
        SELECT i.SO_NO, i.FACTORY_CODE, i.ORDER_NO,
            i.MAT_CODE, m.MAT_DESC, i.LINE_CODE,
            i.ORD_QTY AS so_qty,
            ISNULL(o.ORD_QTY,0) AS ord_qty,
            ISNULL(o.ORD_OUT_QTY,0) AS out_qty,
            ISNULL(o.RCV_GOOD_QTY,0) AS good_qty, ISNULL(o.RCV_LOSS_QTY,0) AS loss_qty,
            o.ORD_STATUS,
            CASE WHEN i.ORD_QTY>0 THEN CAST(ISNULL(o.ORD_OUT_QTY,0)*100.0/i.ORD_QTY AS DECIMAL(5,1)) ELSE 0 END AS pct,
            i.ORD_START_TIME AS start_dt, i.ORD_END_TIME AS end_dt
        FROM {LATEST_I} i
        INNER JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        LEFT JOIN MWIPMATDEF m ON o.MAT_CODE=m.MAT_CODE AND o.FACTORY_CODE=m.FACTORY_CODE
        WHERE i.CUSTOMER_CODE='{cust_code}' AND {DATE_OR_ACTIVE}
            AND o.ORD_STATUS IS NOT NULL
        ORDER BY i.SO_NO, i.ORD_START_TIME
    """)
    for r in orders:
        r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
    # ── 진행현황: SO별로 묶어서 각 ORDER의 파이프라인 단계 ──
    progress = query(f"""
        SELECT i.SO_NO, i.CUST_PO_NO, i.FACTORY_CODE, i.ORDER_NO,
            m.MAT_DESC, o.MAT_CODE, o.FLOW_CODE, l.LINE_TYPE, l.LINE_DESC,
            i.ORD_QTY AS so_qty,
            ISNULL(o.ORD_QTY,0) AS ord_qty,
            ISNULL(o.ORD_IN_QTY,0) AS in_qty,
            ISNULL(o.ORD_OUT_QTY,0) AS out_qty,
            ISNULL(o.RCV_GOOD_QTY,0) AS good_qty,
            ISNULL(o.RCV_LOSS_QTY,0) AS loss_qty,
            o.ORD_STATUS,
            CASE WHEN i.ORD_QTY>0 THEN CAST(ISNULL(o.ORD_OUT_QTY,0)*100.0/i.ORD_QTY AS DECIMAL(5,1)) ELSE 0 END AS pct,
            i.ORD_END_TIME AS end_dt, i.ORD_START_TIME AS start_dt, o.LINE_CODE
        FROM {LATEST_I} i
        INNER JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        LEFT JOIN MWIPMATDEF m ON o.MAT_CODE=m.MAT_CODE AND o.FACTORY_CODE=m.FACTORY_CODE
        LEFT JOIN MWIPLINDEF l ON o.LINE_CODE=l.LINE_CODE AND o.FACTORY_CODE=l.FACTORY_CODE
        WHERE i.CUSTOMER_CODE='{cust_code}' AND {DATE_OR_ACTIVE}
            AND o.ORD_STATUS IN ('PLAN','WAIT','CONFIRM','PROCESS')
            AND (o.ORD_QTY=0 OR o.ORD_OUT_QTY < o.ORD_QTY*0.95)
        ORDER BY
            CASE o.ORD_STATUS WHEN 'PROCESS' THEN 1 WHEN 'CONFIRM' THEN 2 WHEN 'WAIT' THEN 3 ELSE 4 END,
            ISNULL(o.ORD_OUT_QTY,0)*1.0/CASE WHEN i.ORD_QTY>0 THEN i.ORD_QTY ELSE 1 END DESC
    """)
    for r in progress:
        r['factory_name'] = FACTORY.get(r['FACTORY_CODE'], r['FACTORY_CODE'])
        d = str(r.get('end_dt', ''))
        r['end_fmt'] = f'{d[:4]}-{d[4:6]}-{d[6:]}' if len(d) == 8 else d
        s = str(r.get('start_dt', ''))
        r['start_fmt'] = f'{s[:4]}-{s[4:6]}-{s[6:]}' if len(s) == 8 else s
        pct = float(r['pct'])
        st = r['ORD_STATUS']
        in_q = float(r['in_qty'])
        out_q = float(r['out_qty'])
        if st == 'PROCESS':
            r['phase'] = 'PRODUCING'
            r['phase_label'] = '생산중'
        elif st == 'CONFIRM' and out_q > 0:
            r['phase'] = 'PARTIAL'
            r['phase_label'] = '일부산출'
        elif st == 'CONFIRM' and in_q > 0:
            r['phase'] = 'INPUTTED'
            r['phase_label'] = '투입완료'
        elif st == 'CONFIRM':
            r['phase'] = 'READY'
            r['phase_label'] = '확정(대기)'
        elif st == 'WAIT' and out_q > 0 and pct >= 95:
            r['phase'] = 'NEAR_DONE'
            r['phase_label'] = '거의완료'
        elif st == 'WAIT' and out_q > 0:
            r['phase'] = 'PARTIAL'
            r['phase_label'] = '일부산출'
        elif st == 'WAIT':
            r['phase'] = 'WAITING'
            r['phase_label'] = '대기'
        else:
            r['phase'] = 'PLAN'
            r['phase_label'] = '계획'

    return jsonify({'info': info[0] if info else {}, 'so_list': so_list, 'orders': orders, 'progress': progress})

# ── 이슈 모니터링 (납기위반, 잔량 큰 건, 불량률 높은 건) ──
@app.route('/api/issues')
def issues():
    today = datetime.now().strftime('%Y%m%d')
    # 납기초과 & 미완료
    overdue = query(f"""
        SELECT TOP 20 i.SO_NO, i.CUST_PO_NO, i.CUSTOMER_CODE,
            MIN(v.VENDOR_DESC) AS cust_name,
            SUM(i.ORD_QTY) AS so_qty,
            SUM(ISNULL(o.ORD_QTY,0)) AS ord_qty,
            SUM(ISNULL(o.ORD_OUT_QTY,0)) AS total_out,
            MAX(i.ORD_END_TIME) AS deadline,
            CASE WHEN SUM(i.ORD_QTY)>0 THEN CAST(SUM(ISNULL(o.ORD_OUT_QTY,0))*100.0/SUM(i.ORD_QTY) AS DECIMAL(5,1)) ELSE 0 END AS pct
        FROM {LATEST_I} i
        INNER JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        LEFT JOIN MWIPVENDEF v ON i.CUSTOMER_CODE=v.VENDOR_CODE AND i.FACTORY_CODE=v.FACTORY_CODE
        WHERE {DATE_OR_ACTIVE}
        GROUP BY i.SO_NO, i.CUST_PO_NO, i.CUSTOMER_CODE
        HAVING MAX(i.ORD_END_TIME) < '{today}'
            AND CAST(SUM(ISNULL(o.ORD_OUT_QTY,0))*100.0/CASE WHEN SUM(i.ORD_QTY)>0 THEN SUM(i.ORD_QTY) ELSE 1 END AS DECIMAL(5,1)) < 95
        ORDER BY SUM(i.ORD_QTY)-SUM(ISNULL(o.ORD_OUT_QTY,0)) DESC
    """)
    for r in overdue:
        dl = str(r['deadline'])
        r['deadline_fmt'] = f'{dl[:4]}-{dl[4:6]}-{dl[6:]}' if len(dl)>=8 else dl
        r['remaining'] = int(r['so_qty']) - int(r['total_out'])
        r['issue_type'] = 'OVERDUE'

    # 불량률 높은 수주
    defect = query(f"""
        SELECT TOP 15 i.SO_NO, i.CUST_PO_NO, i.CUSTOMER_CODE,
            MIN(v.VENDOR_DESC) AS cust_name,
            SUM(i.ORD_QTY) AS total_qty,
            SUM(ISNULL(o.ORD_OUT_QTY,0)) AS total_out,
            SUM(ISNULL(o.RCV_LOSS_QTY,0)) AS loss_qty,
            CASE WHEN SUM(ISNULL(o.ORD_OUT_QTY,0))>0
                THEN CAST(SUM(ISNULL(o.RCV_LOSS_QTY,0))*100.0/SUM(ISNULL(o.ORD_OUT_QTY,0)) AS DECIMAL(5,2))
                ELSE 0 END AS defect_rate
        FROM {LATEST_I} i
        INNER JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        LEFT JOIN MWIPVENDEF v ON i.CUSTOMER_CODE=v.VENDOR_CODE AND i.FACTORY_CODE=v.FACTORY_CODE
        WHERE {DATE_OR_ACTIVE}
        GROUP BY i.SO_NO, i.CUST_PO_NO, i.CUSTOMER_CODE
        HAVING SUM(ISNULL(o.ORD_OUT_QTY,0)) > 1000
            AND SUM(ISNULL(o.RCV_LOSS_QTY,0))*100.0/NULLIF(SUM(ISNULL(o.ORD_OUT_QTY,0)),0) > 2
        ORDER BY SUM(ISNULL(o.RCV_LOSS_QTY,0))*100.0/NULLIF(SUM(ISNULL(o.ORD_OUT_QTY,0)),0) DESC
    """)
    for r in defect: r['issue_type'] = 'HIGH_DEFECT'

    # 곧 납기인데 진행률 낮은 건
    atrisk = query(f"""
        SELECT TOP 20 i.SO_NO, i.CUST_PO_NO, i.CUSTOMER_CODE,
            MIN(v.VENDOR_DESC) AS cust_name,
            SUM(i.ORD_QTY) AS so_qty,
            SUM(ISNULL(o.ORD_QTY,0)) AS ord_qty,
            SUM(ISNULL(o.ORD_OUT_QTY,0)) AS total_out,
            MAX(i.ORD_END_TIME) AS deadline,
            CASE WHEN SUM(i.ORD_QTY)>0 THEN CAST(SUM(ISNULL(o.ORD_OUT_QTY,0))*100.0/SUM(i.ORD_QTY) AS DECIMAL(5,1)) ELSE 0 END AS pct
        FROM {LATEST_I} i
        INNER JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        LEFT JOIN MWIPVENDEF v ON i.CUSTOMER_CODE=v.VENDOR_CODE AND i.FACTORY_CODE=v.FACTORY_CODE
        WHERE {DATE_OR_ACTIVE}
        GROUP BY i.SO_NO, i.CUST_PO_NO, i.CUSTOMER_CODE
        HAVING MAX(i.ORD_END_TIME) >= '{today}'
            AND MAX(i.ORD_END_TIME) <= CONVERT(VARCHAR, DATEADD(DAY, 7, GETDATE()), 112)
            AND CAST(SUM(ISNULL(o.ORD_OUT_QTY,0))*100.0/CASE WHEN SUM(i.ORD_QTY)>0 THEN SUM(i.ORD_QTY) ELSE 1 END AS DECIMAL(5,1)) < 80
        ORDER BY MAX(i.ORD_END_TIME), SUM(i.ORD_QTY) DESC
    """)
    for r in atrisk:
        dl = str(r['deadline'])
        r['deadline_fmt'] = f'{dl[:4]}-{dl[4:6]}-{dl[6:]}' if len(dl)>=8 else dl
        r['remaining'] = int(r['so_qty']) - int(r['total_out'])
        r['issue_type'] = 'AT_RISK'

    return jsonify({'overdue': overdue, 'defect': defect, 'atrisk': atrisk})

CAT_CASE = """CASE
    WHEN m.MAT_DESC LIKE N'%블러시%' OR m.MAT_DESC LIKE N'%블러셔%' THEN 'BLUSH'
    WHEN m.MAT_DESC LIKE N'%립%' THEN 'LIP'
    WHEN m.MAT_DESC LIKE N'%파운데이션%' OR m.MAT_DESC LIKE N'%쿠션%' THEN 'FOUNDATION'
    WHEN m.MAT_DESC LIKE N'%세럼%' OR m.MAT_DESC LIKE N'%에센스%' THEN 'SERUM'
    WHEN m.MAT_DESC LIKE N'%크림%' OR m.MAT_DESC LIKE N'%로션%' THEN 'CREAM'
    WHEN m.MAT_DESC LIKE N'%마스카라%' OR m.MAT_DESC LIKE N'%아이%' THEN 'EYE'
    WHEN m.MAT_DESC LIKE N'%선%' OR m.MAT_DESC LIKE N'%UV%' THEN 'SUN'
    WHEN m.MAT_DESC LIKE N'%컨투어%' OR m.MAT_DESC LIKE N'%하이라이트%' THEN 'CONTOUR'
    WHEN m.MAT_DESC LIKE N'%브로우%' OR m.MAT_DESC LIKE N'%아이브로%' THEN 'BROW'
    ELSE 'ETC' END"""
CAT_NAME = {'BLUSH':'블러시/블러셔','LIP':'립 제품','FOUNDATION':'파운데이션/쿠션','SERUM':'세럼/에센스',
            'CREAM':'크림/로션','EYE':'아이 메이크업','SUN':'선케어','CONTOUR':'컨투어/하이라이터','BROW':'브로우','ETC':'기타'}

# ── 카테고리별 추이 ──
@app.route('/api/category_trend')
def category_trend():
    rows = query(f"""
        SELECT CONVERT(VARCHAR(7), o.ORD_START_TIME, 120) AS month,
            {CAT_CASE} AS category,
            SUM(o.ORD_QTY) AS qty, COUNT(DISTINCT i.SO_NO) AS so_cnt
        FROM MWIPORDSTS o
        INNER JOIN {LATEST_I} i ON o.ORDER_NO=i.ORDER_NO AND o.FACTORY_CODE=i.FACTORY_CODE
        INNER JOIN MWIPMATDEF m ON o.MAT_CODE=m.MAT_CODE AND o.FACTORY_CODE=m.FACTORY_CODE
        WHERE o.ORD_START_TIME IS NOT NULL
            AND o.ORD_START_TIME >= '2025-10-01'
        GROUP BY CONVERT(VARCHAR(7), o.ORD_START_TIME, 120), {CAT_CASE}
        ORDER BY CONVERT(VARCHAR(7), o.ORD_START_TIME, 120)
    """)
    for r in rows:
        r['category'] = CAT_NAME.get(r['category'], r['category'])
    return jsonify(rows)

# ── 거래처별 월별 수주 추이 ──
@app.route('/api/customer_monthly')
def customer_monthly():
    rows = query(f"""
        SELECT TOP 500 CONVERT(VARCHAR(7), o.ORD_START_TIME, 120) AS month,
            i.CUSTOMER_CODE, MIN(v.VENDOR_DESC) AS cust_name,
            SUM(i.ORD_QTY) AS qty, COUNT(DISTINCT i.SO_NO) AS so_cnt
        FROM {LATEST_I} i
        INNER JOIN MWIPORDSTS o ON i.FACTORY_CODE=o.FACTORY_CODE AND i.ORDER_NO=o.ORDER_NO
        LEFT JOIN MWIPVENDEF v ON i.CUSTOMER_CODE=v.VENDOR_CODE AND i.FACTORY_CODE=v.FACTORY_CODE
        WHERE o.ORD_START_TIME >= '2025-10-01'
        GROUP BY CONVERT(VARCHAR(7), o.ORD_START_TIME, 120), i.CUSTOMER_CODE
        HAVING SUM(i.ORD_QTY) > 10000
        ORDER BY CONVERT(VARCHAR(7), o.ORD_START_TIME, 120), SUM(i.ORD_QTY) DESC
    """)
    return jsonify(rows)

HTML = r'''<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>MES 영업 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI','맑은 고딕',sans-serif;background:#0f172a;color:#e2e8f0}
.header{background:linear-gradient(135deg,#1e293b,#334155);padding:16px 24px;display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #3b82f6}
.header h1{font-size:22px;color:#60a5fa}
.header .sub{color:#94a3b8;font-size:13px;margin-left:12px}
.header .time{color:#94a3b8;font-size:13px}
.refresh-btn{background:#3b82f6;color:#fff;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600}
.tabs{display:flex;background:#1e293b;padding:0 24px;gap:4px;border-bottom:1px solid #334155;flex-wrap:wrap}
.tab{padding:12px 20px;cursor:pointer;color:#94a3b8;border-bottom:3px solid transparent;font-size:14px;font-weight:500;transition:all .2s}
.tab:hover{color:#e2e8f0}.tab.active{color:#60a5fa;border-bottom-color:#3b82f6}
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
.badge-overdue{background:#991b1b;color:#fca5a5}
.badge-high{background:#92400e;color:#fbbf24}
.badge-medium{background:#854d0e;color:#fde68a}
.badge-low{background:#14532d;color:#86efac}
.badge-ok{background:#14532d;color:#86efac}
.badge-active{background:#1e3a5f;color:#93c5fd}
.badge-at_risk{background:#92400e;color:#fbbf24}
.badge-high_defect{background:#831843;color:#f472b6}
.badge-close{background:#14532d;color:#86efac}
.badge-wait{background:#854d0e;color:#fde68a}
.badge-confirm{background:#1e3a5f;color:#93c5fd}
.badge-process{background:#14532d;color:#4ade80}
.chart-container{height:300px;position:relative}
.scroll-table{max-height:500px;overflow-y:auto}
.pbar{background:#334155;border-radius:4px;height:20px;overflow:hidden;position:relative}
.pbar-fill{height:100%;border-radius:4px;transition:width .5s}
.pbar-text{position:absolute;top:0;left:0;right:0;text-align:center;font-size:11px;line-height:20px;color:#fff;font-weight:600}
.clickable{cursor:pointer;color:#60a5fa;text-decoration:underline}
.alert-card{border-left:3px solid #ef4444}
.warn-card{border-left:3px solid #fbbf24}
.cust-select{background:#1e293b;color:#e2e8f0;border:1px solid #475569;padding:8px 14px;border-radius:6px;font-size:14px;min-width:300px}
.phase-btn{background:#334155;color:#94a3b8;border:1px solid #475569;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:12px;transition:all .2s}
.phase-btn:hover{background:#475569;color:#e2e8f0}
.phase-btn.active{background:#3b82f6;color:#fff;border-color:#3b82f6}
.pipe{display:flex;align-items:center;gap:1px}
.pipe-s{padding:3px 8px;font-size:10px;font-weight:600;border-radius:3px;white-space:nowrap}
.pipe-s.done{background:#14532d;color:#4ade80}
.pipe-s.cur{background:#1e3a5f;color:#60a5fa;animation:blink 1.5s infinite}
.pipe-s.wait{background:#1e293b;color:#475569}
.pipe-a{color:#475569;font-size:10px}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.5}}
.ph{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;display:inline-block}
.ph-producing{background:#1e3a5f;color:#60a5fa}
.ph-partial{background:#854d0e;color:#fde68a}
.ph-inputted{background:#4c1d95;color:#c4b5fd}
.ph-ready{background:#14532d;color:#86efac}
.ph-waiting{background:#334155;color:#94a3b8}
.ph-near_done{background:#14532d;color:#4ade80}
.ph-plan{background:#1e293b;color:#64748b}
.stuck-marker{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;vertical-align:middle}
.summary-bar{display:flex;height:24px;border-radius:6px;overflow:hidden;margin-bottom:4px}
.summary-bar div{display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:600;color:#fff}
@media(max-width:1024px){.grid-3{grid-template-columns:1fr}.grid-2{grid-template-columns:1fr}.kpi{flex-wrap:wrap}}
</style></head><body>

<div class="header">
    <div style="display:flex;align-items:center"><h1>MES 영업 대시보드</h1><span class="sub">고객사 납기/수주 관리</span></div>
    <div style="display:flex;align-items:center;gap:16px">
        <span class="time" id="updateTime"></span>
        <button class="refresh-btn" onclick="loadAll()">새로고침</button>
    </div>
</div>

<div class="tabs">
    <div class="tab active" onclick="switchTab(0)">거래처 현황</div>
    <div class="tab" onclick="switchTab(1)">납기 관리</div>
    <div class="tab" onclick="switchTab(2)">고객사 상세</div>
    <div class="tab" onclick="switchTab(3)">카테고리별 추이</div>
    <div class="tab" onclick="switchTab(4)" style="color:#f87171">이슈 모니터링</div>
</div>

<!-- Tab 0: 거래처 현황 -->
<div class="content active" id="tab0">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;flex-wrap:wrap">
        <button class="phase-btn active" onclick="setCustPeriod('')" id="cpAll" style="font-size:13px;padding:7px 16px">26년 누계</button>
        <button class="phase-btn" onclick="setCustPeriod('2026-01')" id="cp01" style="font-size:13px;padding:7px 16px">1월</button>
        <button class="phase-btn" onclick="setCustPeriod('2026-02')" id="cp02" style="font-size:13px;padding:7px 16px">2월</button>
        <button class="phase-btn" onclick="setCustPeriod('2026-03')" id="cp03" style="font-size:13px;padding:7px 16px">3월</button>
        <button class="phase-btn" onclick="setCustPeriod('2026-04')" id="cp04" style="font-size:13px;padding:7px 16px">4월</button>
        <button class="phase-btn" onclick="setCustPeriod('2026-05')" id="cp05" style="font-size:13px;padding:7px 16px">5월</button>
        <button class="phase-btn" onclick="setCustPeriod('2026-06')" id="cp06" style="font-size:13px;padding:7px 16px">6월</button>
        <button class="phase-btn" onclick="setCustPeriod('2026-07')" id="cp07" style="font-size:13px;padding:7px 16px">7월</button>
        <button class="phase-btn" onclick="setCustPeriod('2026-08')" id="cp08" style="font-size:13px;padding:7px 16px">8월</button>
        <button class="phase-btn" onclick="setCustPeriod('2026-09')" id="cp09" style="font-size:13px;padding:7px 16px">9월</button>
        <button class="phase-btn" onclick="setCustPeriod('2026-10')" id="cp10" style="font-size:13px;padding:7px 16px">10월</button>
        <button class="phase-btn" onclick="setCustPeriod('2026-11')" id="cp11" style="font-size:13px;padding:7px 16px">11월</button>
        <button class="phase-btn" onclick="setCustPeriod('2026-12')" id="cp12" style="font-size:13px;padding:7px 16px">12월</button>
    </div>
    <div id="custPeriodLabel" style="color:#94a3b8;font-size:13px;margin-bottom:8px">조회기간: 2026년 누계</div>
    <div class="kpi" id="custKpi"></div>
    <div class="grid grid-2" style="margin-top:12px">
        <div class="card"><h3>거래처별 수주/지시/산출 수량 TOP 20</h3><div class="chart-container" style="height:400px"><canvas id="custQtyChart"></canvas></div></div>
        <div class="card"><h3>거래처별 달성률</h3><div class="chart-container" style="height:400px"><canvas id="custPctChart"></canvas></div></div>
    </div>
    <div class="card" style="margin-top:16px"><h3>거래처별 상세 현황</h3>
        <div class="scroll-table" id="custTable"></div>
    </div>
</div>

<!-- Tab 1: 납기 관리 -->
<div class="content" id="tab1">
    <div class="kpi" id="dlvKpi"></div>
    <!-- 납기 준수율 섹션 -->
    <div class="grid grid-2" style="margin-top:12px">
        <div class="card"><h3>거래처별 납기 준수율</h3><div class="chart-container" style="height:420px"><canvas id="complianceChart"></canvas></div></div>
        <div class="card"><h3>지연 원인 분석 <span style="font-size:11px;color:#64748b">(클릭하면 상세 필터)</span></h3>
            <div class="chart-container" style="height:320px"><canvas id="delayCauseChart"></canvas></div>
            <div style="margin-top:8px;padding:10px;background:#1e293b;border-radius:8px;font-size:11px;line-height:1.8;color:#94a3b8">
                <div><span style="color:#22c55e;font-weight:700">● 납기준수</span> — 실제 생산완료일 ≤ 납기일. 납기 내 정상 완료</div>
                <div><span style="color:#fbbf24;font-weight:700">● 납기촉박</span> — 수주확정일~납기일 여유 5일 이내. 일정이 촉박하거나 납기가 앞당겨진 경우</div>
                <div><span style="color:#f97316;font-weight:700">● 착수지연</span> — 실제 생산착수가 계획보다 3일 이상 늦음. 내부 프로세스 지연</div>
                <div><span style="color:#ef4444;font-weight:700">● 생산지연</span> — 착수는 정상이나 생산 과정에서 지연. 공정/품질 이슈</div>
                <div><span style="color:#475569;font-weight:700">● 진행중</span> — 아직 납기일 도래 전. 현재 생산 진행 중</div>
            </div>
        </div>
    </div>
    <div class="card" style="margin-top:16px"><h3>거래처별 납기 준수 현황</h3>
        <div class="scroll-table" style="max-height:400px" id="complianceTable"></div>
    </div>
    <div class="card" style="margin-top:16px;border-left:3px solid #ef4444"><h3 style="color:#ef4444">납기 지연 상세 (SO 단위)</h3>
        <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap" id="delayFilter">
            <button class="phase-btn active" onclick="filterDelay('ALL')">전체</button>
            <button class="phase-btn" onclick="filterDelay('TIGHT')">납기촉박</button>
            <button class="phase-btn" onclick="filterDelay('START')">착수지연</button>
            <button class="phase-btn" onclick="filterDelay('PROCESS')">생산지연</button>
        </div>
        <div class="scroll-table" style="max-height:500px" id="delayDetailTable"></div>
    </div>
    <div class="card" style="margin-top:16px"><h3>납기 리스크 수주 (달성률 98% 미만)</h3>
        <div class="scroll-table" style="max-height:700px" id="dlvRiskTable"></div>
    </div>
</div>

<!-- Tab 2: 고객사 상세 -->
<div class="content" id="tab2">
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px">
        <select class="cust-select" id="custSelect" onchange="loadCustDetail()">
            <option value="">거래처를 선택하세요</option>
        </select>
        <span id="custDetailName" style="font-size:18px;color:#60a5fa;font-weight:600"></span>
    </div>
    <!-- 미완료/완료 토글 -->
    <div style="display:flex;gap:8px;margin-bottom:16px">
        <button class="phase-btn active" id="btnOpen" onclick="toggleCompletionView('open')" style="font-size:14px;padding:8px 20px">미완료 수주</button>
        <button class="phase-btn" id="btnClosed" onclick="toggleCompletionView('closed')" style="font-size:14px;padding:8px 20px">완료 수주</button>
        <button class="phase-btn" id="btnChanges" onclick="toggleCompletionView('changes')" style="font-size:14px;padding:8px 20px;color:#fbbf24">계획 변경이력</button>
    </div>
    <!-- 미완료 영역 -->
    <div id="openView">
        <div class="kpi" id="cdKpi"></div>
        <div class="grid grid-2" style="margin-top:12px">
            <div class="card"><h3>미완료 수주별 달성률</h3><div class="chart-container" style="height:400px"><canvas id="cdSoChart"></canvas></div></div>
            <div class="card"><h3>미완료 수주별 수주/지시/산출</h3><div class="chart-container" style="height:400px"><canvas id="cdQtyChart"></canvas></div></div>
        </div>
        <div class="card" style="margin-top:16px;border-left:3px solid #60a5fa"><h3 style="color:#60a5fa">진행현황 - 미완료 건별 파이프라인</h3>
            <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap" id="phaseFilter">
                <button class="phase-btn active" onclick="filterPhase('ALL')">전체</button>
                <button class="phase-btn" onclick="filterPhase('PRODUCING')">생산중</button>
                <button class="phase-btn" onclick="filterPhase('PARTIAL')">일부산출</button>
                <button class="phase-btn" onclick="filterPhase('INPUTTED')">투입완료</button>
                <button class="phase-btn" onclick="filterPhase('READY')">확정대기</button>
                <button class="phase-btn" onclick="filterPhase('WAITING')">대기</button>
            </div>
            <div id="progressSummary" style="margin-bottom:12px"></div>
            <div class="scroll-table" style="max-height:700px" id="progressTable"></div>
        </div>
        <div class="card" style="margin-top:16px"><h3>미완료 수주 목록</h3>
            <div class="scroll-table" id="cdSoTable"></div>
        </div>
        <div class="card" style="margin-top:16px"><h3>미완료 작업지시 상세</h3>
            <div class="scroll-table" style="max-height:600px" id="cdOrdTable"></div>
        </div>
    </div>
    <!-- 완료 영역 -->
    <div id="closedView" style="display:none">
        <div class="kpi" id="cdKpiClosed"></div>
        <div class="card" style="margin-top:16px"><h3>완료 수주 목록</h3>
            <div class="scroll-table" style="max-height:600px" id="cdSoTableClosed"></div>
        </div>
        <div class="card" style="margin-top:16px"><h3>완료 작업지시 상세</h3>
            <div class="scroll-table" style="max-height:600px" id="cdOrdTableClosed"></div>
        </div>
    </div>
    <!-- 변경이력 영역 -->
    <div id="changesView" style="display:none">
        <div class="kpi" id="cdKpiChanges"></div>
        <div class="card" style="margin-top:16px"><h3>이 거래처의 계획 변경 내역</h3>
            <div class="scroll-table" style="max-height:600px" id="cdChangesTable"></div>
        </div>
    </div>
</div>

<!-- Tab 3: 카테고리별 추이 -->
<div class="content" id="tab3">
    <div class="grid grid-2">
        <div class="card"><h3>카테고리별 월별 수주추이</h3><div class="chart-container" style="height:400px"><canvas id="catChart"></canvas></div></div>
        <div class="card"><h3>거래처별 월별 수주추이 (주요)</h3><div class="chart-container" style="height:400px"><canvas id="custMonthChart"></canvas></div></div>
    </div>
    <div class="card" style="margin-top:16px"><h3>카테고리별 상세</h3>
        <div class="scroll-table" id="catTable"></div>
    </div>
</div>

<!-- Tab 4: 이슈 모니터링 -->
<div class="content" id="tab4">
    <div class="kpi" id="issueKpi"></div>
    <div class="grid grid-2" style="margin-top:12px">
        <div class="card alert-card"><h3 style="color:#f87171">납기초과 미완료 수주</h3>
            <div class="scroll-table" id="overdueTable"></div>
        </div>
        <div class="card warn-card"><h3 style="color:#fbbf24">7일 이내 납기 (달성률 80% 미만)</h3>
            <div class="scroll-table" id="atriskTable"></div>
        </div>
    </div>
    <div class="card" style="margin-top:16px"><h3 style="color:#f472b6">불량률 높은 수주 (2% 초과)</h3>
        <div class="scroll-table" id="defectTable"></div>
    </div>
</div>

<script>
let charts={}, allCustomers=[];
function switchTab(n){
    document.querySelectorAll('.tab').forEach((t,i)=>t.classList.toggle('active',i===n));
    document.querySelectorAll('.content').forEach((c,i)=>c.classList.toggle('active',i===n));
}
function fmt(n){return n?Number(n).toLocaleString():'0'}
function pbarHtml(pct){
    let p=Number(pct);
    let c=p>=95?'#22c55e':p>=70?'#eab308':'#ef4444';
    return `<div class="pbar"><div class="pbar-fill" style="width:${Math.min(p,100)}%;background:${c}"></div><div class="pbar-text">${p}%</div></div>`;
}
function badgeHtml(s){
    let map={OVERDUE:'badge-overdue',HIGH:'badge-high',MEDIUM:'badge-medium',LOW:'badge-low',OK:'badge-ok',ACTIVE:'badge-active',AT_RISK:'badge-at_risk',HIGH_DEFECT:'badge-high_defect',CLOSE:'badge-close',WAIT:'badge-wait',CONFIRM:'badge-confirm',PROCESS:'badge-process'};
    return `<span class="badge ${map[s]||''}">${s}</span>`;
}

async function loadAll(){
    document.getElementById('updateTime').textContent='갱신: '+new Date().toLocaleString('ko-KR');
    await Promise.all([loadCustomers(),loadDelivery(),loadCategory(),loadIssues()]);
}

// ── Tab 0 ──
let custPeriod='';
function setCustPeriod(m){
    custPeriod=m;
    document.querySelectorAll('#tab0 .phase-btn').forEach(b=>b.classList.remove('active'));
    if(m==='')document.getElementById('cpAll').classList.add('active');
    else{let mm=m.split('-')[1];let el=document.getElementById('cp'+mm);if(el)el.classList.add('active');}
    let label=m===''?'2026년 누계':`2026년 ${parseInt(m.split('-')[1])}월`;
    document.getElementById('custPeriodLabel').textContent='조회기간: '+label;
    loadCustomers();
}
async function loadCustomers(){
    let url='/api/customers'+(custPeriod?'?month='+custPeriod:'');
    let data=await(await fetch(url)).json();
    allCustomers=data;

    let totalSo=data.reduce((s,r)=>s+Number(r.so_cnt),0);
    let totalSoQty=data.reduce((s,r)=>s+Number(r.so_qty),0);
    let totalOrdQty=data.reduce((s,r)=>s+Number(r.ord_qty),0);
    let totalOut=data.reduce((s,r)=>s+Number(r.total_out),0);
    let overallPct=totalSoQty>0?(totalOut/totalSoQty*100).toFixed(1):0;
    document.getElementById('custKpi').innerHTML=
        `<div class="kpi-box" style="border-color:#60a5fa" onclick="showKpiDetail('cust_cnt')"><div class="label">총 거래처</div><div class="value" style="color:#60a5fa">${data.length}</div></div>`+
        `<div class="kpi-box" style="border-color:#a78bfa" onclick="showKpiDetail('so_cnt')"><div class="label">총 수주</div><div class="value" style="color:#a78bfa">${fmt(totalSo)}</div><div class="sub">건</div></div>`+
        `<div class="kpi-box" style="border-color:#fbbf24" onclick="showKpiDetail('so_qty')"><div class="label">수주수량</div><div class="value" style="color:#fbbf24">${fmt(totalSoQty)}</div></div>`+
        `<div class="kpi-box" style="border-color:#fb923c" onclick="showKpiDetail('ord_qty')"><div class="label">지시수량</div><div class="value" style="color:#fb923c">${fmt(totalOrdQty)}</div></div>`+
        `<div class="kpi-box" style="border-color:#4ade80" onclick="showKpiDetail('total_out')"><div class="label">산출수량</div><div class="value" style="color:#4ade80">${fmt(totalOut)}</div></div>`+
        `<div class="kpi-box" style="border-color:#f472b6" onclick="showKpiDetail('pct')"><div class="label">달성률(산출/수주)</div><div class="value" style="color:#f472b6">${overallPct}%</div></div>`;

    // Charts
    let top20=data.slice(0,20);
    let labels=top20.map(r=>(r.cust_name||r.CUSTOMER_CODE).substring(0,20));
    if(charts.custQty)charts.custQty.destroy();
    charts.custQty=new Chart(document.getElementById('custQtyChart'),{type:'bar',
        data:{labels,datasets:[
            {label:'수주수량',data:top20.map(r=>Number(r.so_qty)),backgroundColor:'#475569'},
            {label:'지시수량',data:top20.map(r=>Number(r.ord_qty)),backgroundColor:'#fb923c'},
            {label:'산출수량',data:top20.map(r=>Number(r.total_out)),backgroundColor:'#3b82f6'}
        ]},
        options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',
            scales:{x:{ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}},y:{ticks:{color:'#94a3b8',font:{size:10}},grid:{color:'#334155'}}},
            plugins:{legend:{labels:{color:'#e2e8f0'}}}}
    });
    if(charts.custPct)charts.custPct.destroy();
    charts.custPct=new Chart(document.getElementById('custPctChart'),{type:'bar',
        data:{labels,datasets:[{label:'달성률(%)',data:top20.map(r=>Number(r.pct)),
            backgroundColor:top20.map(r=>Number(r.pct)>=95?'#22c55e':Number(r.pct)>=70?'#eab308':'#ef4444')}]},
        options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',
            scales:{x:{max:120,ticks:{color:'#94a3b8',callback:v=>v+'%'},grid:{color:'#334155'}},y:{ticks:{color:'#94a3b8',font:{size:10}},grid:{color:'#334155'}}},
            plugins:{legend:{display:false}}}
    });

    // Table
    let tbl=`<table><thead><tr><th>거래처코드</th><th>거래처명</th><th class="num">수주건</th><th class="num">수주수량</th><th class="num">지시수량</th><th class="num">산출수량</th><th>달성률</th><th class="num">마감</th><th class="num">진행</th></tr></thead><tbody>`;
    data.forEach(r=>{
        tbl+=`<tr><td><span class="clickable" onclick="selectCust('${r.CUSTOMER_CODE}')">${r.CUSTOMER_CODE}</span></td>`;
        tbl+=`<td>${r.cust_name||''}</td><td class="num">${r.so_cnt}</td>`;
        tbl+=`<td class="num">${fmt(r.so_qty)}</td><td class="num">${fmt(r.ord_qty)}</td><td class="num">${fmt(r.total_out)}</td>`;
        tbl+=`<td>${pbarHtml(r.pct)}</td><td class="num">${r.closed_cnt}</td><td class="num">${r.active_cnt}</td></tr>`;
    });
    tbl+='</tbody></table>';
    document.getElementById('custTable').innerHTML=tbl;

    // Populate customer select
    let sel=document.getElementById('custSelect');
    let curVal=sel.value;
    sel.innerHTML='<option value="">거래처를 선택하세요</option>';
    data.forEach(r=>{
        sel.innerHTML+=`<option value="${r.CUSTOMER_CODE}">${r.CUSTOMER_CODE} - ${(r.cust_name||'').substring(0,30)} (${r.so_cnt}건)</option>`;
    });
    if(curVal) sel.value=curVal;
}

function selectCust(code){
    document.getElementById('custSelect').value=code;
    switchTab(2);
    loadCustDetail();
}

// ── Tab 1 ──
let allDelayDetails=[], allComplianceDetails=[];
function filterDelay(type){
    document.querySelectorAll('#delayFilter .phase-btn').forEach(b=>b.classList.remove('active'));
    if(event&&event.target)event.target.classList.add('active');
    let filtered=allDelayDetails;
    if(type==='TIGHT')filtered=allDelayDetails.filter(r=>r.compliance.includes('TIGHT'));
    else if(type==='START')filtered=allDelayDetails.filter(r=>r.compliance.includes('START')||r.compliance.includes('IDLE'));
    else if(type==='PROCESS')filtered=allDelayDetails.filter(r=>r.compliance.includes('PROCESS')&&!r.compliance.includes('IDLE'));
    renderDelayDetail(filtered);
}
function renderDelayDetail(data, mode){
    let causeColors={ON_TIME:'#22c55e',LATE_TIGHT:'#fbbf24',OVERDUE_TIGHT:'#fbbf24',LATE_START:'#f97316',OVERDUE_IDLE:'#f97316',LATE_PROCESS:'#ef4444',OVERDUE_PROCESS:'#ef4444',PENDING:'#475569'};
    let causeLabels={ON_TIME:'납기준수',LATE_TIGHT:'납기촉박',OVERDUE_TIGHT:'납기촉박',LATE_START:'착수지연',OVERDUE_IDLE:'착수지연',LATE_PROCESS:'생산지연',OVERDUE_PROCESS:'생산지연',PENDING:'진행중'};
    // 헤더 타이틀 변경
    let titleMap={ON_TIME:'납기준수 상세',PENDING:'진행중 상세'};
    let titleEl=document.querySelector('#delayDetailTable').closest('.card').querySelector('h3');
    if(titleEl)titleEl.innerHTML=mode&&titleMap[mode]?`<span style="color:${causeColors[mode]}">${titleMap[mode]} (${data.length}건)</span>`:`<span style="color:#ef4444">납기 지연 상세 (${data.length}건)</span>`;
    let tbl=`<table><thead><tr><th>원인</th><th>상태</th><th>수주</th><th>거래처</th><th>PO/프로젝트</th><th class="num">수주수량</th><th class="num">산출</th><th>달성률</th><th class="num">여유일</th><th class="num">착수지연</th><th>납기</th><th>완료일</th></tr></thead><tbody>`;
    data.forEach(r=>{
        let bg=causeColors[r.compliance]||'#64748b';
        let lb=causeLabels[r.compliance]||r.label;
        let isDone=r.compliance==='ON_TIME'||r.compliance.startsWith('LATE_');
        let isPending=r.compliance==='PENDING';
        let stBadge=isDone?'<span style="color:#4ade80;font-size:11px">완료</span>':isPending?'<span style="color:#60a5fa;font-size:11px">진행중</span>':'<span style="color:#ef4444;font-size:11px;font-weight:600">미완료</span>';
        tbl+=`<tr><td><span style="background:${bg}22;color:${bg};padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">${lb}</span></td>`;
        tbl+=`<td>${stBadge}</td><td style="font-size:11px">${r.SO_NO}</td>`;
        tbl+=`<td style="font-size:11px"><span class="clickable" onclick="selectCust('${r.CUSTOMER_CODE}')">${(r.cust_name||r.CUSTOMER_CODE).substring(0,15)}</span></td>`;
        tbl+=`<td style="font-size:11px">${(r.CUST_PO_NO||'').substring(0,30)}</td>`;
        tbl+=`<td class="num">${fmt(r.so_qty)}</td><td class="num">${fmt(r.total_out)}</td>`;
        tbl+=`<td style="min-width:80px">${pbarHtml(r.pct)}</td>`;
        tbl+=`<td class="num" style="color:${r.notice_days<=5?'#fbbf24':'#94a3b8'}">${r.notice_days}일</td>`;
        tbl+=`<td class="num" style="color:${r.start_delay>0?'#f97316':'#4ade80'}">${r.start_delay>0?'+'+r.start_delay+'일':'-'}</td>`;
        tbl+=`<td style="font-size:11px">${r.dl_fmt}</td><td style="font-size:11px">${r.ad_fmt}</td></tr>`;
    });
    tbl+='</tbody></table>';
    document.getElementById('delayDetailTable').innerHTML=data.length>0?tbl:'<div style="color:#64748b;text-align:center;padding:20px">해당 건이 없습니다</div>';
}

async function loadDelivery(){
    let [riskData, compData]=await Promise.all([
        (await fetch('/api/delivery_risk')).json(),
        (await fetch('/api/delivery_compliance')).json()
    ]);
    let custs=compData.customers, details=compData.details;

    // KPI - 전체 집계
    let totalSo=details.length;
    let onTime=details.filter(r=>r.compliance==='ON_TIME').length;
    let lateTight=details.filter(r=>r.compliance.includes('TIGHT')).length;
    let lateProcess=details.filter(r=>['LATE_START','LATE_PROCESS','OVERDUE_IDLE','OVERDUE_PROCESS'].includes(r.compliance)).length;
    let pending=details.filter(r=>r.compliance==='PENDING').length;
    let done=totalSo-pending;
    let compRate=done>0?(onTime/done*100).toFixed(1):'-';
    document.getElementById('dlvKpi').innerHTML=
        `<div class="kpi-box" style="border-color:#22c55e"><div class="label">납기준수율</div><div class="value" style="color:#22c55e;font-size:28px">${compRate}%</div><div class="sub">${onTime}/${done} 건</div></div>`+
        `<div class="kpi-box" style="border-color:#22c55e"><div class="label">납기준수</div><div class="value" style="color:#22c55e">${onTime}</div></div>`+
        `<div class="kpi-box" style="border-color:#fbbf24"><div class="label">지연(납기촉박)</div><div class="value" style="color:#fbbf24">${lateTight}</div><div class="sub">일정부족/앞당김</div></div>`+
        `<div class="kpi-box" style="border-color:#ef4444"><div class="label">지연(프로세스)</div><div class="value" style="color:#ef4444">${lateProcess}</div><div class="sub">착수/생산 지연</div></div>`+
        `<div class="kpi-box" style="border-color:#94a3b8"><div class="label">진행중</div><div class="value" style="color:#94a3b8">${pending}</div></div>`+
        `<div class="kpi-box" style="border-color:#60a5fa"><div class="label">전체 수주</div><div class="value" style="color:#60a5fa">${totalSo}</div></div>`;

    // 거래처별 준수율 차트 (납기 마감 3건 이상)
    let chartCusts=custs.filter(c=>(c.total-c.pending)>=2).slice(0,20);
    if(charts.compliance)charts.compliance.destroy();
    charts.compliance=new Chart(document.getElementById('complianceChart'),{type:'bar',
        data:{labels:chartCusts.map(c=>(c.cust_name||c.CUSTOMER_CODE).substring(0,18)),
            datasets:[
                {label:'준수',data:chartCusts.map(c=>c.on_time),backgroundColor:'#22c55e'},
                {label:'납기촉박',data:chartCusts.map(c=>c.tight_cnt),backgroundColor:'#fbbf24'},
                {label:'프로세스지연',data:chartCusts.map(c=>c.process_cnt),backgroundColor:'#ef4444'},
                {label:'진행중',data:chartCusts.map(c=>c.pending),backgroundColor:'#475569'}
            ]},
        options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',
            scales:{x:{stacked:true,ticks:{color:'#94a3b8'},grid:{color:'#334155'}},y:{stacked:true,ticks:{color:'#94a3b8',font:{size:10}},grid:{color:'#334155'}}},
            plugins:{legend:{labels:{color:'#e2e8f0',font:{size:10}}}}}
    });

    // 지연 원인 도넛 차트 (클릭 필터 연동)
    let startCntAll=details.filter(r=>['LATE_START','OVERDUE_IDLE'].includes(r.compliance)).length;
    let procCntAll=details.filter(r=>['LATE_PROCESS','OVERDUE_PROCESS'].includes(r.compliance)).length;
    let donutSegments=['ON_TIME','TIGHT','START','PROCESS','PENDING'];
    if(charts.delayCause)charts.delayCause.destroy();
    charts.delayCause=new Chart(document.getElementById('delayCauseChart'),{type:'doughnut',
        data:{labels:['납기준수','납기촉박(일정부족)','착수지연','생산지연','진행중'],
            datasets:[{data:[onTime,lateTight,startCntAll,procCntAll,pending],
                backgroundColor:['#22c55e','#fbbf24','#f97316','#ef4444','#475569'],
                borderColor:'#0f172a',borderWidth:2,hoverBorderColor:'#fff',hoverBorderWidth:3}]},
        options:{responsive:true,maintainAspectRatio:false,cursor:'pointer',
            onClick:(evt,elements)=>{
                if(elements.length>0){
                    let idx=elements[0].index;
                    let seg=donutSegments[idx];
                    // 버튼 active 초기화 & 필터 적용
                    document.querySelectorAll('#delayFilter .phase-btn').forEach(b=>b.classList.remove('active'));
                    if(seg==='ON_TIME'){
                        // 준수 건 보여주기 - 별도 처리
                        let onTimeData=details.filter(r=>r.compliance==='ON_TIME');
                        renderDelayDetail(onTimeData,'ON_TIME');
                    } else if(seg==='PENDING'){
                        let pendingData=details.filter(r=>r.compliance==='PENDING');
                        renderDelayDetail(pendingData,'PENDING');
                    } else {
                        let btn=document.querySelector('#delayFilter .phase-btn[onclick*=\"'+seg+'\"]');
                        if(btn){btn.classList.add('active');btn.click();}
                        else filterDelay(seg);
                    }
                    // 스크롤 이동
                    document.getElementById('delayDetailTable').scrollIntoView({behavior:'smooth',block:'start'});
                }
            },
            plugins:{legend:{position:'right',labels:{color:'#e2e8f0',font:{size:12},padding:16}},
                tooltip:{callbacks:{label:function(ctx){let v=ctx.raw;let t=ctx.dataset.data.reduce((a,b)=>a+b,0);let pct=(v/t*100).toFixed(1);return ` ${ctx.label}: ${v}건 (${pct}%)`;}}}
            }}
    });

    // 거래처별 테이블
    let ctbl=`<table><thead><tr><th>거래처</th><th>거래처명</th><th class="num">전체</th><th class="num">준수</th><th class="num">납기촉박</th><th class="num">착수지연</th><th class="num">생산지연</th><th class="num">진행중</th><th>준수율</th></tr></thead><tbody>`;
    custs.forEach(c=>{
        let done2=c.total-c.pending;
        let rate=done2>0?(c.on_time/done2*100).toFixed(1):'-';
        let rateColor=rate==='-'?'#94a3b8':rate>=90?'#22c55e':rate>=70?'#eab308':'#ef4444';
        ctbl+=`<tr><td><span class="clickable" onclick="selectCust('${c.CUSTOMER_CODE}')">${c.CUSTOMER_CODE}</span></td>`;
        ctbl+=`<td>${(c.cust_name||'').substring(0,20)}</td>`;
        ctbl+=`<td class="num">${c.total}</td><td class="num" style="color:#22c55e">${c.on_time}</td>`;
        ctbl+=`<td class="num" style="color:#fbbf24">${c.tight_cnt||0}</td>`;
        ctbl+=`<td class="num" style="color:#f97316">${c.late_start+c.overdue_idle}</td>`;
        ctbl+=`<td class="num" style="color:#ef4444">${c.late_process+c.overdue_process}</td>`;
        ctbl+=`<td class="num">${c.pending}</td>`;
        ctbl+=`<td style="min-width:100px"><div style="display:flex;align-items:center;gap:6px"><div style="flex:1;background:#1e293b;border-radius:4px;height:16px;position:relative"><div style="background:${rateColor};width:${Math.min(parseFloat(rate)||0,100)}%;height:100%;border-radius:4px"></div></div><span style="color:${rateColor};font-weight:600;font-size:12px;min-width:40px">${rate}%</span></div></td></tr>`;
    });
    ctbl+='</tbody></table>';
    document.getElementById('complianceTable').innerHTML=ctbl;

    // 전체 상세 저장 (도넛 클릭용)
    allComplianceDetails=details;
    // 지연 상세 (지연 건만)
    allDelayDetails=details.filter(r=>r.compliance!=='ON_TIME'&&r.compliance!=='PENDING');
    allDelayDetails.sort((a,b)=>{let p={OVERDUE_PROCESS:0,OVERDUE_IDLE:1,OVERDUE_TIGHT:2,LATE_PROCESS:3,LATE_START:4,LATE_TIGHT:5};return (p[a.compliance]||9)-(p[b.compliance]||9)});
    renderDelayDetail(allDelayDetails);
    // Update filter counts
    let tightCnt=allDelayDetails.filter(r=>r.compliance.includes('TIGHT')).length;
    let startCnt=allDelayDetails.filter(r=>r.compliance.includes('START')||r.compliance.includes('IDLE')).length;
    let procCnt=allDelayDetails.filter(r=>r.compliance.includes('PROCESS')&&!r.compliance.includes('IDLE')).length;
    let btns=document.querySelectorAll('#delayFilter .phase-btn');
    btns[0].textContent=`전체 (${allDelayDetails.length})`;
    btns[1].textContent=`납기촉박 (${tightCnt})`;
    btns[2].textContent=`착수지연 (${startCnt})`;
    btns[3].textContent=`생산지연 (${procCnt})`;

    // 기존 리스크 테이블
    let data=riskData;
    let tbl=`<table><thead><tr><th>리스크</th><th>수주번호</th><th>거래처</th><th>거래처명</th><th>프로젝트/PO</th><th class="num">수주수량</th><th class="num">지시수량</th><th class="num">산출</th><th class="num">잔여</th><th>달성률</th><th>납기</th></tr></thead><tbody>`;
    data.forEach(r=>{
        tbl+=`<tr><td>${badgeHtml(r.risk)}</td><td>${r.SO_NO}</td>`;
        tbl+=`<td><span class="clickable" onclick="selectCust('${r.CUSTOMER_CODE}')">${r.CUSTOMER_CODE}</span></td>`;
        tbl+=`<td>${(r.cust_name||'').substring(0,20)}</td><td>${(r.CUST_PO_NO||'').substring(0,35)}</td>`;
        tbl+=`<td class="num">${fmt(r.so_qty)}</td><td class="num">${fmt(r.ord_qty)}</td><td class="num">${fmt(r.total_out)}</td><td class="num">${fmt(r.remaining)}</td>`;
        tbl+=`<td style="min-width:100px">${pbarHtml(r.pct)}</td><td>${r.deadline_fmt}</td></tr>`;
    });
    tbl+='</tbody></table>';
    document.getElementById('dlvRiskTable').innerHTML=tbl;
}

// ── Tab 2 ──
function toggleCompletionView(view){
    document.getElementById('openView').style.display=view==='open'?'':'none';
    document.getElementById('closedView').style.display=view==='closed'?'':'none';
    document.getElementById('changesView').style.display=view==='changes'?'':'none';
    document.getElementById('btnOpen').classList.toggle('active',view==='open');
    document.getElementById('btnClosed').classList.toggle('active',view==='closed');
    document.getElementById('btnChanges').classList.toggle('active',view==='changes');
    if(view==='changes') loadCustChanges();
}

async function loadCustChanges(){
    let code=document.getElementById('custSelect').value;
    if(!code)return;
    try{
        let data=await(await fetch('/api/customer_changes/'+code)).json();
        let FNAME={'1100':'퍼플카운티','1200':'그린카운티','1300':'3공장'};
        let dlFwd=data.filter(r=>r.deadline_forward).length;
        let dlDly=data.filter(r=>r.deadline_delay).length;
        let qtyChg=data.filter(r=>r.qty_change).length;
        let startChg=data.filter(r=>r.start_change).length;

        document.getElementById('cdKpiChanges').innerHTML=
            `<div class="kpi-box" style="border-color:#fbbf24"><div class="label">총 변경</div><div class="value" style="color:#fbbf24">${data.length}</div><div class="sub">건</div></div>`+
            `<div class="kpi-box" style="border-color:#ef4444"><div class="label">납기 앞당김</div><div class="value" style="color:#ef4444">${dlFwd}</div></div>`+
            `<div class="kpi-box" style="border-color:#fb923c"><div class="label">납기 연장</div><div class="value" style="color:#fb923c">${dlDly}</div></div>`+
            `<div class="kpi-box" style="border-color:#a78bfa"><div class="label">수량 변경</div><div class="value" style="color:#a78bfa">${qtyChg}</div></div>`+
            `<div class="kpi-box" style="border-color:#60a5fa"><div class="label">착수일 변경</div><div class="value" style="color:#60a5fa">${startChg}</div></div>`;

        let tbl=`<table><thead><tr><th>공장</th><th>주문번호</th><th>수주번호</th><th>변경유형</th><th>변경 전</th><th>변경 후</th><th>확정일</th><th>상태</th></tr></thead><tbody>`;
        if(data.length===0) tbl+=`<tr><td colspan="8" style="text-align:center;color:#64748b;padding:30px">이 거래처의 계획 변경 이력이 없습니다</td></tr>`;
        data.forEach(r=>{
            let types=[];
            if(r.deadline_forward) types.push('<span style="color:#ef4444">납기앞당김</span>');
            if(r.deadline_delay) types.push('<span style="color:#fb923c">납기연장</span>');
            if(r.qty_change) types.push('<span style="color:#a78bfa">수량변경</span>');
            if(r.start_change) types.push('<span style="color:#60a5fa">착수일변경</span>');
            let before=[],after=[];
            if(r.orig_end!==r.new_end){before.push('납기:'+r.orig_end);after.push(r.new_end)}
            if(r.orig_qty!==r.new_qty){before.push('수량:'+fmt(r.orig_qty));after.push(fmt(r.new_qty))}
            if(r.orig_start!==r.new_start){before.push('착수:'+r.orig_start);after.push(r.new_start)}
            tbl+=`<tr><td>${FNAME[r.FACTORY_CODE]||r.FACTORY_CODE}</td><td>${r.ORDER_NO}</td><td>${r.SO_NO}</td>`;
            tbl+=`<td>${types.join(' ')}</td><td style="color:#94a3b8">${before.join(', ')}</td><td style="font-weight:600">${after.join(', ')}</td>`;
            tbl+=`<td>${r.CONFIRM_DATE}</td><td><span class="badge badge-${(r.ORD_STATUS||'').toLowerCase()}">${r.ORD_STATUS}</span></td></tr>`;
        });
        tbl+=`</tbody></table>`;
        document.getElementById('cdChangesTable').innerHTML=tbl;
    }catch(e){console.log('changes error:',e)}
}

async function loadCustDetail(){
    let code=document.getElementById('custSelect').value;
    if(!code)return;
    let data=await(await fetch('/api/customer_detail/'+code)).json();
    let info=data.info, so=data.so_list, ord=data.orders;

    document.getElementById('custDetailName').textContent=info.VENDOR_DESC||code;
    // Reset to 미완료 view
    toggleCompletionView('open');

    // Split SO: 미완료 = active>0 or pct<95, 완료 = active==0 and pct>=95
    let openSo=so.filter(r=>Number(r.active)>0 || Number(r.pct)<95);
    let closedSo=so.filter(r=>Number(r.active)===0 && Number(r.pct)>=95);
    let openSoNos=new Set(openSo.map(r=>r.SO_NO));
    let closedSoNos=new Set(closedSo.map(r=>r.SO_NO));
    let openOrd=ord.filter(r=>openSoNos.has(r.SO_NO));
    let closedOrd=ord.filter(r=>closedSoNos.has(r.SO_NO));

    // Update toggle button labels
    document.getElementById('btnOpen').textContent=`미완료 수주 (${openSo.length})`;
    document.getElementById('btnClosed').textContent=`완료 수주 (${closedSo.length})`;

    // ── 미완료 KPI ──
    let oSoQty=0,oOrdQty=0,oOut=0,oGood=0,oLoss=0;
    openSo.forEach(r=>{oSoQty+=Number(r.so_qty);oOrdQty+=Number(r.ord_qty);oOut+=Number(r.total_out);oGood+=Number(r.good_qty);oLoss+=Number(r.loss_qty)});
    let oPct=oSoQty>0?(oOut/oSoQty*100).toFixed(1):0;
    let oLossRate=oOut>0?(oLoss/oOut*100).toFixed(2):0;
    let overdueCnt=openSo.filter(r=>r.risk==='OVERDUE').length;
    let remain=oSoQty-oOut;
    document.getElementById('cdKpi').innerHTML=
        `<div class="kpi-box" style="border-color:#ef4444"><div class="label">미완료 수주</div><div class="value" style="color:#ef4444">${openSo.length}</div><div class="sub">전체 ${so.length}</div></div>`+
        `<div class="kpi-box" style="border-color:#fbbf24"><div class="label">수주수량</div><div class="value" style="color:#fbbf24">${fmt(oSoQty)}</div></div>`+
        `<div class="kpi-box" style="border-color:#fb923c"><div class="label">지시수량</div><div class="value" style="color:#fb923c">${fmt(oOrdQty)}</div></div>`+
        `<div class="kpi-box" style="border-color:#4ade80"><div class="label">산출수량</div><div class="value" style="color:#4ade80">${fmt(oOut)}</div></div>`+
        `<div class="kpi-box" style="border-color:#f472b6"><div class="label">잔여수량</div><div class="value" style="color:#f472b6">${fmt(remain>0?remain:0)}</div></div>`+
        `<div class="kpi-box" style="border-color:#a78bfa"><div class="label">달성률</div><div class="value" style="color:#a78bfa">${oPct}%</div></div>`+
        (overdueCnt>0?`<div class="kpi-box" style="border-color:#ef4444;border-width:2px"><div class="label">납기초과</div><div class="value" style="color:#ef4444">${overdueCnt}</div></div>`:'');

    // ── 미완료 Charts ──
    let chartSos=openSo.filter(r=>Number(r.so_qty)>0);
    if(charts.cdSo)charts.cdSo.destroy();
    charts.cdSo=new Chart(document.getElementById('cdSoChart'),{type:'bar',
        data:{labels:chartSos.map(r=>(r.CUST_PO_NO||r.SO_NO).substring(0,25)),
            datasets:[{label:'달성률(%)',data:chartSos.map(r=>Number(r.pct)),
                backgroundColor:chartSos.map(r=>Number(r.pct)>=95?'#22c55e':Number(r.pct)>=70?'#eab308':'#ef4444')}]},
        options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',
            scales:{x:{max:120,ticks:{color:'#94a3b8',callback:v=>v+'%'},grid:{color:'#334155'}},y:{ticks:{color:'#94a3b8',font:{size:9}},grid:{color:'#334155'}}},
            plugins:{legend:{display:false}}}
    });
    if(charts.cdQty)charts.cdQty.destroy();
    charts.cdQty=new Chart(document.getElementById('cdQtyChart'),{type:'bar',
        data:{labels:chartSos.map(r=>(r.CUST_PO_NO||r.SO_NO).substring(0,25)),
            datasets:[{label:'수주수량',data:chartSos.map(r=>Number(r.so_qty)),backgroundColor:'#475569'},
                {label:'지시수량',data:chartSos.map(r=>Number(r.ord_qty)),backgroundColor:'#fb923c'},
                {label:'산출수량',data:chartSos.map(r=>Number(r.total_out)),backgroundColor:'#3b82f6'}]},
        options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',
            scales:{x:{ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}},y:{ticks:{color:'#94a3b8',font:{size:9}},grid:{color:'#334155'}}},
            plugins:{legend:{labels:{color:'#e2e8f0'}}}}
    });

    // ── 미완료 SO table ──
    let tbl=`<table><thead><tr><th>상태</th><th>수주번호</th><th>프로젝트/PO</th><th class="num">수주수량</th><th class="num">지시수량</th><th class="num">산출</th><th class="num">잔여</th><th>달성률</th><th class="num">진행</th><th>시작일</th><th>납기</th></tr></thead><tbody>`;
    openSo.forEach(r=>{
        let rem=Math.max(Number(r.so_qty)-Number(r.total_out),0);
        tbl+=`<tr><td>${badgeHtml(r.risk)}</td><td>${r.SO_NO}</td><td>${(r.CUST_PO_NO||'').substring(0,35)}</td>`;
        tbl+=`<td class="num">${fmt(r.so_qty)}</td><td class="num">${fmt(r.ord_qty)}</td><td class="num">${fmt(r.total_out)}</td>`;
        tbl+=`<td class="num" style="color:#f472b6">${fmt(rem)}</td>`;
        tbl+=`<td style="min-width:100px">${pbarHtml(r.pct)}</td>`;
        tbl+=`<td class="num">${r.active}</td>`;
        tbl+=`<td>${r.start_fmt}</td><td>${r.end_fmt}</td></tr>`;
    });
    tbl+='</tbody></table>';
    document.getElementById('cdSoTable').innerHTML=tbl;

    // ── 미완료 Order table ──
    let tbl2=`<table><thead><tr><th>수주</th><th>공장</th><th>지시번호</th><th>자재명</th><th class="num">수주수량</th><th class="num">지시수량</th><th class="num">산출</th><th class="num">양품</th><th class="num">불량</th><th>달성률</th><th>상태</th></tr></thead><tbody>`;
    openOrd.forEach(r=>{
        tbl2+=`<tr><td>${r.SO_NO}</td><td>${r.factory_name}</td><td>${r.ORDER_NO}</td><td>${(r.MAT_DESC||r.MAT_CODE||'').substring(0,30)}</td>`;
        tbl2+=`<td class="num">${fmt(r.so_qty)}</td><td class="num">${fmt(r.ord_qty)}</td><td class="num">${fmt(r.out_qty)}</td>`;
        tbl2+=`<td class="num">${fmt(r.good_qty)}</td><td class="num">${fmt(r.loss_qty)}</td>`;
        tbl2+=`<td style="min-width:80px">${pbarHtml(r.pct)}</td><td>${badgeHtml(r.ORD_STATUS||'')}</td></tr>`;
    });
    tbl2+='</tbody></table>';
    document.getElementById('cdOrdTable').innerHTML=tbl2;

    // ── 완료 KPI ──
    let cSoQty=0,cOrdQty=0,cOut=0,cGood=0,cLoss=0;
    closedSo.forEach(r=>{cSoQty+=Number(r.so_qty);cOrdQty+=Number(r.ord_qty);cOut+=Number(r.total_out);cGood+=Number(r.good_qty);cLoss+=Number(r.loss_qty)});
    let cPct=cSoQty>0?(cOut/cSoQty*100).toFixed(1):0;
    let cLossRate=cOut>0?(cLoss/cOut*100).toFixed(2):0;
    document.getElementById('cdKpiClosed').innerHTML=
        `<div class="kpi-box" style="border-color:#22c55e"><div class="label">완료 수주</div><div class="value" style="color:#22c55e">${closedSo.length}</div></div>`+
        `<div class="kpi-box" style="border-color:#94a3b8"><div class="label">수주수량</div><div class="value" style="color:#94a3b8">${fmt(cSoQty)}</div></div>`+
        `<div class="kpi-box" style="border-color:#94a3b8"><div class="label">산출수량</div><div class="value" style="color:#94a3b8">${fmt(cOut)}</div></div>`+
        `<div class="kpi-box" style="border-color:#94a3b8"><div class="label">달성률</div><div class="value" style="color:#94a3b8">${cPct}%</div></div>`+
        `<div class="kpi-box" style="border-color:#94a3b8"><div class="label">불량률</div><div class="value" style="color:#94a3b8">${cLossRate}%</div></div>`;

    // ── 완료 SO table ──
    let tbl3=`<table><thead><tr><th>수주번호</th><th>프로젝트/PO</th><th class="num">수주수량</th><th class="num">산출</th><th class="num">양품</th><th class="num">불량</th><th>달성률</th><th>시작일</th><th>납기</th></tr></thead><tbody>`;
    closedSo.forEach(r=>{
        tbl3+=`<tr><td>${r.SO_NO}</td><td>${(r.CUST_PO_NO||'').substring(0,35)}</td>`;
        tbl3+=`<td class="num">${fmt(r.so_qty)}</td><td class="num">${fmt(r.total_out)}</td>`;
        tbl3+=`<td class="num">${fmt(r.good_qty)}</td><td class="num">${fmt(r.loss_qty)}</td>`;
        tbl3+=`<td style="min-width:80px">${pbarHtml(r.pct)}</td>`;
        tbl3+=`<td>${r.start_fmt}</td><td>${r.end_fmt}</td></tr>`;
    });
    tbl3+='</tbody></table>';
    document.getElementById('cdSoTableClosed').innerHTML=tbl3;

    // ── 완료 Order table ──
    let tbl4=`<table><thead><tr><th>수주</th><th>공장</th><th>지시번호</th><th>자재명</th><th class="num">수주수량</th><th class="num">산출</th><th class="num">양품</th><th class="num">불량</th><th>달성률</th><th>상태</th></tr></thead><tbody>`;
    closedOrd.forEach(r=>{
        tbl4+=`<tr><td>${r.SO_NO}</td><td>${r.factory_name}</td><td>${r.ORDER_NO}</td><td>${(r.MAT_DESC||r.MAT_CODE||'').substring(0,30)}</td>`;
        tbl4+=`<td class="num">${fmt(r.so_qty)}</td><td class="num">${fmt(r.out_qty)}</td>`;
        tbl4+=`<td class="num">${fmt(r.good_qty)}</td><td class="num">${fmt(r.loss_qty)}</td>`;
        tbl4+=`<td style="min-width:80px">${pbarHtml(r.pct)}</td><td>${badgeHtml(r.ORD_STATUS||'')}</td></tr>`;
    });
    tbl4+='</tbody></table>';
    document.getElementById('cdOrdTableClosed').innerHTML=tbl4;

    // ── Progress pipeline (미완료만) ──
    if(data.progress){
        progressData=data.progress;
        renderProgress(progressData);
        let counts={ALL:progressData.length,PRODUCING:0,PARTIAL:0,INPUTTED:0,READY:0,WAITING:0,PLAN:0,NEAR_DONE:0};
        progressData.forEach(r=>{counts[r.phase]=(counts[r.phase]||0)+1});
        document.querySelectorAll('#phaseFilter .phase-btn').forEach(btn=>{
            let ph=btn.getAttribute('onclick').match(/'(\\w+)'/)[1];
            let c=counts[ph]||0;
            if(ph==='ALL')btn.textContent=`전체 (${progressData.length})`;
            else{let labels={PRODUCING:'생산중',PARTIAL:'일부산출',INPUTTED:'투입완료',READY:'확정대기',WAITING:'대기',PLAN:'계획',NEAR_DONE:'거의완료'};btn.textContent=`${labels[ph]||ph} (${c})`;}
        });
    }
}

let progressData=[];
function filterPhase(phase){
    document.querySelectorAll('#phaseFilter .phase-btn').forEach(b=>b.classList.remove('active'));
    event.target.classList.add('active');
    if(phase==='ALL')renderProgress(progressData);
    else renderProgress(progressData.filter(r=>r.phase===phase));
}

function renderProgress(data){
    const STAGES=['PLAN','WAITING','READY','INPUTTED','PRODUCING','OUTPUT'];
    const STAGE_LABELS={PLAN:'계획',WAITING:'대기',READY:'확정',INPUTTED:'투입',PRODUCING:'생산',OUTPUT:'산출'};
    const PHASE_TO_STAGE={PLAN:0,WAITING:1,READY:2,INPUTTED:3,PRODUCING:4,PARTIAL:5,NEAR_DONE:5};
    const PHASE_COLORS={PRODUCING:'#22c55e',PARTIAL:'#eab308',NEAR_DONE:'#60a5fa',INPUTTED:'#a78bfa',READY:'#fb923c',WAITING:'#94a3b8',PLAN:'#475569'};

    // Summary bar
    let phaseCounts={};
    data.forEach(r=>{phaseCounts[r.phase]=(phaseCounts[r.phase]||0)+1});
    let total=data.length;
    let sumHtml='<div class="summary-bar">';
    let phaseOrder=['PRODUCING','NEAR_DONE','PARTIAL','INPUTTED','READY','WAITING','PLAN'];
    let phaseLabels={PRODUCING:'생산중',NEAR_DONE:'거의완료',PARTIAL:'일부산출',INPUTTED:'투입완료',READY:'확정대기',WAITING:'대기',PLAN:'계획'};
    phaseOrder.forEach(ph=>{
        let cnt=phaseCounts[ph]||0;
        if(cnt>0){
            let pct=(cnt/total*100).toFixed(0);
            sumHtml+=`<div style="flex:${cnt};background:${PHASE_COLORS[ph]};text-align:center;padding:4px 2px;font-size:11px;color:#fff;min-width:30px" title="${phaseLabels[ph]}: ${cnt}건 (${pct}%)">${phaseLabels[ph]} ${cnt}</div>`;
        }
    });
    sumHtml+='</div>';
    document.getElementById('progressSummary').innerHTML=total>0?sumHtml:'<div style="color:#64748b;text-align:center;padding:20px">진행중인 건이 없습니다</div>';

    if(total===0){document.getElementById('progressTable').innerHTML='';return;}

    // Table
    let tbl=`<table><thead><tr><th>수주</th><th>지시</th><th>자재명</th><th>공장</th><th>라인</th><th class="num">수주</th><th class="num">지시</th><th class="num">투입</th><th class="num">산출</th><th>달성</th><th>생산예정</th><th>납기</th><th>파이프라인</th><th>상태</th></tr></thead><tbody>`;
    data.forEach(r=>{
        let stageIdx=PHASE_TO_STAGE[r.phase]||0;
        let pipeHtml='<div class="pipe">';
        STAGES.forEach((s,i)=>{
            let cls=i<stageIdx?'done':i===stageIdx?'cur':'wait';
            pipeHtml+=`<div class="pipe-s ${cls}" title="${STAGE_LABELS[s]}">${STAGE_LABELS[s]}</div>`;
        });
        pipeHtml+='</div>';
        let pct=Number(r.pct)||0;
        let pctColor=pct>=95?'#22c55e':pct>=50?'#eab308':'#ef4444';
        tbl+=`<tr><td style="font-size:11px">${r.SO_NO||''}</td><td style="font-size:11px">${r.ORDER_NO||''}</td>`;
        tbl+=`<td style="font-size:11px;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${r.MAT_DESC||''}">${(r.MAT_DESC||r.MAT_CODE||'').substring(0,25)}</td>`;
        tbl+=`<td style="font-size:11px">${r.FACTORY_CODE==='1100'?'퍼플':r.FACTORY_CODE==='1200'?'그린':'3공장'}</td>`;
        tbl+=`<td style="font-size:11px">${(r.LINE_DESC||r.LINE_CODE||'').substring(0,10)}</td>`;
        tbl+=`<td class="num" style="font-size:11px">${fmt(r.so_qty)}</td>`;
        tbl+=`<td class="num" style="font-size:11px">${fmt(r.ord_qty)}</td>`;
        tbl+=`<td class="num" style="font-size:11px">${fmt(r.in_qty)}</td>`;
        tbl+=`<td class="num" style="font-size:11px">${fmt(r.out_qty)}</td>`;
        tbl+=`<td style="min-width:50px"><div style="background:#1e293b;border-radius:4px;height:14px;position:relative"><div style="background:${pctColor};width:${Math.min(pct,100)}%;height:100%;border-radius:4px"></div><span style="position:absolute;right:3px;top:-1px;font-size:10px;color:#e2e8f0">${pct}%</span></div></td>`;
        tbl+=`<td style="font-size:11px;white-space:nowrap">${r.start_fmt||'-'}</td>`;
        tbl+=`<td style="font-size:11px;white-space:nowrap">${r.end_fmt||'-'}</td>`;
        tbl+=`<td style="min-width:200px">${pipeHtml}</td>`;
        let phBadge=`<span class="ph-${r.phase.toLowerCase()}" style="font-size:10px;padding:2px 6px;border-radius:4px">${phaseLabels[r.phase]||r.phase}</span>`;
        tbl+=`<td>${phBadge}</td></tr>`;
    });
    tbl+='</tbody></table>';
    document.getElementById('progressTable').innerHTML=tbl;
}

// ── Tab 3 ──
const CAT_COLORS={'블러시/블러셔':'#f472b6','립 제품':'#ef4444','파운데이션/쿠션':'#fbbf24','세럼/에센스':'#a78bfa','크림/로션':'#60a5fa','아이 메이크업':'#34d399','선케어':'#fb923c','컨투어/하이라이터':'#e879f9','브로우':'#94a3b8','기타':'#475569'};
async function loadCategory(){
    let [catData,custMonth]=await Promise.all([
        (await fetch('/api/category_trend')).json(),
        (await fetch('/api/customer_monthly')).json()
    ]);

    let months=[...new Set(catData.map(r=>r.month))].sort();
    let cats=[...new Set(catData.map(r=>r.category))];
    let byCat={};
    catData.forEach(r=>{if(!byCat[r.category])byCat[r.category]={};byCat[r.category][r.month]=(byCat[r.category][r.month]||0)+Number(r.qty)});
    if(charts.cat)charts.cat.destroy();
    charts.cat=new Chart(document.getElementById('catChart'),{type:'bar',
        data:{labels:months,datasets:cats.filter(c=>c!=='기타').map(c=>({label:c,data:months.map(m=>byCat[c]?.[m]||0),backgroundColor:CAT_COLORS[c]||'#64748b'}))},
        options:{responsive:true,maintainAspectRatio:false,
            scales:{y:{stacked:true,ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}},x:{stacked:true,ticks:{color:'#94a3b8'},grid:{color:'#334155'}}},
            plugins:{legend:{labels:{color:'#e2e8f0',font:{size:10}}}}}
    });

    // Customer monthly - top 8
    let custTotals={};
    custMonth.forEach(r=>{custTotals[r.CUSTOMER_CODE]=(custTotals[r.CUSTOMER_CODE]||0)+Number(r.qty)});
    let topCusts=Object.entries(custTotals).sort((a,b)=>b[1]-a[1]).slice(0,8).map(e=>e[0]);
    let custNames={};custMonth.forEach(r=>{if(!custNames[r.CUSTOMER_CODE])custNames[r.CUSTOMER_CODE]=r.cust_name||r.CUSTOMER_CODE});
    let cmMonths=[...new Set(custMonth.map(r=>r.month))].sort();
    let byCust={};
    custMonth.forEach(r=>{if(topCusts.includes(r.CUSTOMER_CODE)){if(!byCust[r.CUSTOMER_CODE])byCust[r.CUSTOMER_CODE]={};byCust[r.CUSTOMER_CODE][r.month]=(byCust[r.CUSTOMER_CODE][r.month]||0)+Number(r.qty)}});
    let cmColors=['#60a5fa','#f472b6','#a78bfa','#34d399','#fbbf24','#fb923c','#ef4444','#e879f9'];
    if(charts.custMonth)charts.custMonth.destroy();
    charts.custMonth=new Chart(document.getElementById('custMonthChart'),{type:'line',
        data:{labels:cmMonths,datasets:topCusts.map((c,i)=>({label:(custNames[c]||c).substring(0,15),data:cmMonths.map(m=>byCust[c]?.[m]||0),
            borderColor:cmColors[i%8],backgroundColor:cmColors[i%8]+'33',tension:.3,pointRadius:2}))},
        options:{responsive:true,maintainAspectRatio:false,
            scales:{y:{ticks:{color:'#94a3b8',callback:v=>fmt(v)},grid:{color:'#334155'}},x:{ticks:{color:'#94a3b8'},grid:{color:'#334155'}}},
            plugins:{legend:{labels:{color:'#e2e8f0',font:{size:10}}}}}
    });

    // Category table
    let catSummary={};
    catData.forEach(r=>{if(!catSummary[r.category])catSummary[r.category]={qty:0,so:0};catSummary[r.category].qty+=Number(r.qty);catSummary[r.category].so+=Number(r.so_cnt)});
    let tbl=`<table><thead><tr><th>카테고리</th><th class="num">총수량</th><th class="num">수주건</th></tr></thead><tbody>`;
    Object.entries(catSummary).sort((a,b)=>b[1].qty-a[1].qty).forEach(([c,v])=>{
        tbl+=`<tr><td><span style="display:inline-block;width:12px;height:12px;border-radius:2px;background:${CAT_COLORS[c]||'#475569'};margin-right:8px;vertical-align:middle"></span>${c}</td>`;
        tbl+=`<td class="num">${fmt(v.qty)}</td><td class="num">${v.so}</td></tr>`;
    });
    tbl+='</tbody></table>';
    document.getElementById('catTable').innerHTML=tbl;
}

// ── Tab 4 ──
async function loadIssues(){
    let data=await(await fetch('/api/issues')).json();

    document.getElementById('issueKpi').innerHTML=
        `<div class="kpi-box" style="border-color:#ef4444"><div class="label">납기초과 미완료</div><div class="value" style="color:#ef4444">${data.overdue.length}</div></div>`+
        `<div class="kpi-box" style="border-color:#fbbf24"><div class="label">7일내 납기 위험</div><div class="value" style="color:#fbbf24">${data.atrisk.length}</div></div>`+
        `<div class="kpi-box" style="border-color:#f472b6"><div class="label">불량률 높은 수주</div><div class="value" style="color:#f472b6">${data.defect.length}</div></div>`;

    // Overdue
    let tbl=`<table><thead><tr><th>거래처</th><th>거래처명</th><th>수주</th><th>PO/프로젝트</th><th class="num">수주</th><th class="num">지시</th><th class="num">산출</th><th class="num">잔여</th><th>달성률</th><th>납기</th></tr></thead><tbody>`;
    data.overdue.forEach(r=>{
        tbl+=`<tr><td>${r.CUSTOMER_CODE}</td><td>${(r.cust_name||'').substring(0,15)}</td><td>${r.SO_NO}</td><td>${(r.CUST_PO_NO||'').substring(0,25)}</td>`;
        tbl+=`<td class="num">${fmt(r.so_qty)}</td><td class="num">${fmt(r.ord_qty)}</td><td class="num">${fmt(r.total_out)}</td><td class="num" style="color:#f87171">${fmt(r.remaining)}</td>`;
        tbl+=`<td style="min-width:80px">${pbarHtml(r.pct)}</td><td style="color:#f87171">${r.deadline_fmt}</td></tr>`;
    });
    tbl+='</tbody></table>';
    document.getElementById('overdueTable').innerHTML=tbl;

    // At risk
    let tbl2=`<table><thead><tr><th>거래처</th><th>거래처명</th><th>수주</th><th>PO/프로젝트</th><th class="num">수주</th><th class="num">지시</th><th class="num">산출</th><th class="num">잔여</th><th>달성률</th><th>납기</th></tr></thead><tbody>`;
    data.atrisk.forEach(r=>{
        tbl2+=`<tr><td>${r.CUSTOMER_CODE}</td><td>${(r.cust_name||'').substring(0,15)}</td><td>${r.SO_NO}</td><td>${(r.CUST_PO_NO||'').substring(0,25)}</td>`;
        tbl2+=`<td class="num">${fmt(r.so_qty)}</td><td class="num">${fmt(r.ord_qty)}</td><td class="num">${fmt(r.total_out)}</td><td class="num" style="color:#fbbf24">${fmt(r.remaining)}</td>`;
        tbl2+=`<td style="min-width:80px">${pbarHtml(r.pct)}</td><td style="color:#fbbf24">${r.deadline_fmt}</td></tr>`;
    });
    tbl2+='</tbody></table>';
    document.getElementById('atriskTable').innerHTML=tbl2;

    // Defect
    let tbl3=`<table><thead><tr><th>거래처</th><th>거래처명</th><th>수주</th><th>PO/프로젝트</th><th class="num">산출</th><th class="num">불량수</th><th class="num">불량률</th></tr></thead><tbody>`;
    data.defect.forEach(r=>{
        tbl3+=`<tr><td>${r.CUSTOMER_CODE}</td><td>${(r.cust_name||'').substring(0,15)}</td><td>${r.SO_NO}</td><td>${(r.CUST_PO_NO||'').substring(0,25)}</td>`;
        tbl3+=`<td class="num">${fmt(r.total_out)}</td><td class="num" style="color:#f472b6">${fmt(r.loss_qty)}</td><td class="num" style="color:#f472b6">${r.defect_rate}%</td></tr>`;
    });
    tbl3+='</tbody></table>';
    document.getElementById('defectTable').innerHTML=tbl3;
}

// ── KPI 상세 모달 ──
async function showKpiDetail(type){
    let factUrl='/api/kpi_factory'+(custPeriod?'?month='+custPeriod:'');
    let factData=await(await fetch(factUrl)).json();
    let FNAME={'1100':'퍼플카운티','1200':'그린카운티','1300':'3공장'};
    let titles={cust_cnt:'총 거래처 상세',so_cnt:'총 수주 상세',so_qty:'수주수량 상세',ord_qty:'지시수량 상세',total_out:'산출수량 상세',pct:'달성률 상세'};
    let sortKey=type==='cust_cnt'?'pct':type==='pct'?'pct':type;
    let sortDir=(type==='pct'||type==='cust_cnt')?'asc':'desc';

    let html=`<h3>${titles[type]||type}</h3>`;
    // Factory summary
    html+=`<h4>공장별 요약</h4><table><thead><tr><th>공장</th><th class="num">거래처</th><th class="num">수주건</th><th class="num">수주수량</th><th class="num">지시수량</th><th class="num">산출수량</th><th>달성률</th><th class="num">마감</th><th class="num">진행</th></tr></thead><tbody>`;
    let tot={c:0,s:0,sq:0,oq:0,ou:0,cl:0,ac:0};
    factData.forEach(r=>{
        tot.c+=Number(r.cust_cnt);tot.s+=Number(r.so_cnt);tot.sq+=Number(r.so_qty);
        tot.oq+=Number(r.ord_qty);tot.ou+=Number(r.total_out);tot.cl+=Number(r.closed_cnt);tot.ac+=Number(r.active_cnt);
        html+=`<tr><td>${FNAME[r.FACTORY_CODE]||r.FACTORY_CODE}</td><td class="num">${r.cust_cnt}</td><td class="num">${fmt(r.so_cnt)}</td><td class="num">${fmt(r.so_qty)}</td><td class="num">${fmt(r.ord_qty)}</td><td class="num">${fmt(r.total_out)}</td><td>${pbarHtml(r.pct)}</td><td class="num">${r.closed_cnt}</td><td class="num">${r.active_cnt}</td></tr>`;
    });
    let tp=tot.sq>0?(tot.ou/tot.sq*100).toFixed(1):0;
    html+=`<tr style="font-weight:700;border-top:2px solid #64748b"><td>합계</td><td class="num">${tot.c}</td><td class="num">${fmt(tot.s)}</td><td class="num">${fmt(tot.sq)}</td><td class="num">${fmt(tot.oq)}</td><td class="num">${fmt(tot.ou)}</td><td>${pbarHtml(tp)}</td><td class="num">${tot.cl}</td><td class="num">${tot.ac}</td></tr></tbody></table>`;

    // Distribution for 달성률/거래처
    if(type==='pct'||type==='cust_cnt'){
        let hi=allCustomers.filter(r=>Number(r.pct)>=95).length;
        let mid=allCustomers.filter(r=>Number(r.pct)>=50&&Number(r.pct)<95).length;
        let lo=allCustomers.filter(r=>Number(r.pct)<50).length;
        html+=`<h4>달성률 분포</h4><div style="display:flex;gap:12px;margin-bottom:8px">`;
        html+=`<div style="flex:1;background:#14532d;border-radius:8px;padding:12px;text-align:center"><div style="color:#86efac;font-size:12px">95% 이상</div><div style="color:#4ade80;font-size:22px;font-weight:700">${hi}개사</div></div>`;
        html+=`<div style="flex:1;background:#854d0e;border-radius:8px;padding:12px;text-align:center"><div style="color:#fde68a;font-size:12px">50~95%</div><div style="color:#fbbf24;font-size:22px;font-weight:700">${mid}개사</div></div>`;
        html+=`<div style="flex:1;background:#991b1b;border-radius:8px;padding:12px;text-align:center"><div style="color:#fca5a5;font-size:12px">50% 미만</div><div style="color:#f87171;font-size:22px;font-weight:700">${lo}개사</div></div></div>`;
    }

    // Customer ranking
    let sorted=[...allCustomers].sort((a,b)=>sortDir==='asc'?Number(a[sortKey])-Number(b[sortKey]):Number(b[sortKey])-Number(a[sortKey]));
    let topN=sorted.slice(0,20);
    let label=sortDir==='asc'?'하위':'상위';
    html+=`<h4>거래처별 ${label} 20</h4><div class="scroll-table" style="max-height:400px"><table><thead><tr><th>#</th><th>거래처</th><th>거래처명</th><th class="num">수주건</th><th class="num">수주수량</th><th class="num">지시수량</th><th class="num">산출수량</th><th>달성률</th></tr></thead><tbody>`;
    topN.forEach((r,i)=>{
        html+=`<tr><td>${i+1}</td><td><span class="clickable" onclick="document.getElementById('kpiModal').style.display='none';selectCust('${r.CUSTOMER_CODE}')">${r.CUSTOMER_CODE}</span></td><td>${r.cust_name||''}</td><td class="num">${r.so_cnt}</td><td class="num">${fmt(r.so_qty)}</td><td class="num">${fmt(r.ord_qty)}</td><td class="num">${fmt(r.total_out)}</td><td>${pbarHtml(r.pct)}</td></tr>`;
    });
    html+=`</tbody></table></div>`;

    document.getElementById('kpiModalBody').innerHTML=html;
    document.getElementById('kpiModal').style.display='flex';
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
    print('Sales Dashboard: http://localhost:5002')
    app.run(host='0.0.0.0', port=5002, debug=False)
