"""
C&C 인터내셔널 — 통합 대시보드
영업 | 생산 | 구매 | 품질 | 경영 | 납기변경
"""
import streamlit as st
import pymssql
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

st.set_page_config(page_title="C&C 통합 대시보드", page_icon="🏭", layout="wide", initial_sidebar_state="expanded")

# ══════════════════════════════════════════
# 스타일
# ══════════════════════════════════════════
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    .stApp { background-color: #0f1117; font-family: 'Inter', sans-serif; }

    .kpi-row { display: flex; gap: 12px; margin-bottom: 20px; }
    .kpi {
        flex: 1; background: linear-gradient(145deg, #1e2130 0%, #171923 100%);
        border: 1px solid #2d3748; border-radius: 14px;
        padding: 18px 20px; text-align: center;
    }
    .kpi:hover { transform: translateY(-2px); border-color: #4a5568; }
    .kpi .num { font-size: 28px; font-weight: 800; letter-spacing: -1px; }
    .kpi .lbl { font-size: 11px; color: #718096; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 1px; }
    .kpi .sub { font-size: 11px; color: #4a5568; margin-top: 2px; }

    .pipe-row { display: flex; align-items: center; gap: 0; margin: 12px 0; }
    .pipe-stage { flex: 1; text-align: center; padding: 10px 6px; border-radius: 8px; font-size: 12px; font-weight: 600; }
    .pipe-arrow { color: #4a5568; font-size: 18px; margin: 0 2px; }
    .stage-done { background: #1c4532; color: #68d391; border: 1px solid #2f855a; }
    .stage-active { background: #2a4365; color: #63b3ed; border: 1px solid #3182ce; animation: pulse 2s infinite; }
    .stage-wait { background: #1a1a2e; color: #4a5568; border: 1px solid #2d3748; }
    @keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:0.7;} }

    .stage-date { font-size: 10px; font-weight: 500; margin-top: 4px; }
    .stage-date.done { color: #68d391; }
    .stage-date.active { color: #63b3ed; }
    .stage-date.plan { color: #718096; font-style: italic; }
    .stage-qty { font-size: 10px; font-weight: 700; color: #e2e8f0; margin-top: 2px; }

    .order-card {
        background: linear-gradient(145deg, #1e2130 0%, #171923 100%);
        border: 1px solid #2d3748; border-radius: 12px;
        padding: 20px; margin-bottom: 12px;
    }
    .order-card:hover { border-color: #4299e1; }
    .order-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
    .order-title { font-size: 16px; font-weight: 700; color: #e2e8f0; }
    .order-badge { padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
    .badge-process { background: #2a4365; color: #63b3ed; }
    .badge-wait { background: #744210; color: #ecc94b; }
    .badge-close { background: #1c4532; color: #68d391; }
    .order-meta { display: flex; gap: 16px; font-size: 12px; color: #a0aec0; margin-bottom: 14px; flex-wrap: wrap; }

    .progress-wrap { background: #2d3748; border-radius: 8px; height: 8px; overflow: hidden; }
    .progress-fill { height: 100%; border-radius: 8px; }

    section[data-testid="stSidebar"] { background: #171923; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; background: #171923; padding: 4px; border-radius: 10px; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px; color: #718096; font-weight: 600; }
    .stTabs [aria-selected="true"] { background: #2d3748 !important; color: #e2e8f0 !important; }

    /* 페이지 네비 */
    .nav-item { padding: 10px 16px; border-radius: 8px; margin-bottom: 4px; cursor: pointer; font-size: 14px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════
# DB
# ══════════════════════════════════════════
CONN = dict(server=config.DB_HOST, port=config.DB_PORT, database=config.DB_NAME,
            user=config.DB_USER, password=config.DB_PASSWORD, charset="utf8")
FACTORY = {"1100": "퍼플", "1200": "그린", "1300": "제3공장"}
FAC_COLOR = {"퍼플": "#9F7AEA", "그린": "#48BB78", "제3공장": "#4299E1"}
FLOW_MAP = {"FM001": "제조", "FM003": "제조", "FC001": "충전", "FP001": "포장", "FT001": "타정", "FB001": "본딩"}
STATUS_MAP = {"PROCESS": "진행중", "WAIT": "대기", "CLOSE": "완료"}


def _mock_data():
    """DB 접속 불가 시 샘플 데이터"""
    import random
    random.seed(42)
    custs = {"10000208": "주식회사피플앤코", "20000105": "씨피씨피", "10000211": "브이디엘",
             "10000369": "릴리바이레드", "20000031": "돌체앤가바나", "10000313": "에스쁘아",
             "10000014": "클리오", "20000210": "이니스프리"}
    items = [
        ("810009061", "멜팅밤 로즈", "FP001", "PP06", "1100"),
        ("810017595", "글로우 세럼 파운데이션", "FP001", "GP01", "1200"),
        ("810018476", "씨피 듀 필름 틴트 R", "FP001", "GP02", "1200"),
        ("810010123", "치크스테인 블러셔 07", "FP001", "GP02", "1200"),
        ("810020761", "듀이 핏 팔레트", "FP001", "GP03", "1200"),
        ("540016403", "컬러 마스터 450g", "FC001", "MC30", "1300"),
        ("810019417", "립글로우 틴트 05", "FP001", "PP05", "1100"),
        ("810020858", "벨벳 무스 틴트", "FP001", "PP04", "1100"),
        ("540012599", "파운데이션 벌크 800g", "FC001", "MCBD6", "1300"),
        ("810020622", "러브빔 치크밤", "FP001", "PP02", "1100"),
        ("520017046", "쿠션 퍼프 세트", "FM001", "PM26", "1100"),
        ("530004525", "타정 아이섀도우 4g", "FT001", "MC259", "1300"),
        ("810019849", "올데이 래쉬 마스카라", "FP001", "PP02", "1100"),
        ("810014125", "스킨핏 파우더 팩트", "FP001", "PP04", "1100"),
        ("540015023", "립밤 벌크 300g", "FC001", "MC56", "1300"),
    ]
    rows = []
    base = datetime(2026, 3, 1)
    cust_keys = list(custs.keys())
    for i in range(80):
        item = items[i % len(items)]
        plan = base + timedelta(days=random.randint(0, 30))
        qty = random.choice([3000, 4000, 5000, 8000, 10000, 14000, 20000])
        out = int(qty * random.uniform(0, 1.02))
        st_ = random.choice(["PROCESS", "PROCESS", "WAIT", "CLOSE"])
        if st_ == "CLOSE": out = qty
        inp = int(qty * random.uniform(0.5, 1.0))
        good = int(out * random.uniform(0.95, 1.0))
        loss = out - good
        rows.append({
            "FACTORY_CODE": item[4], "ORDER_NO": f"1001{i:04d}", "PLAN_DATE": plan.strftime("%Y%m%d"),
            "ORD_DATE": (plan + timedelta(days=random.randint(0, 2))).strftime("%Y%m%d"),
            "ORD_STATUS": st_, "CUSTOMER_CODE": cust_keys[i % len(cust_keys)],
            "MAT_CODE": item[0], "ORD_QTY": qty, "ORD_OUT_QTY": out, "ORD_IN_QTY": inp,
            "RCV_GOOD_QTY": good, "RCV_LOSS_QTY": loss,
            "SO_NO": f"3000{random.randint(100,999)}", "DESCRIPTION": None,
            "LINE_CODE": item[3], "FLOW_CODE": item[2],
            "ORD_START_TIME": None, "ORD_END_TIME": None, "MAT_DESC": item[1],
        })
    df = pd.DataFrame(rows)
    cmap = custs
    return df, cmap


def _process_df(df, cmap):
    df["고객명"] = df["CUSTOMER_CODE"].map(cmap).fillna(df["CUSTOMER_CODE"])
    df["공장"] = df["FACTORY_CODE"].map(FACTORY).fillna(df["FACTORY_CODE"])
    df["품명"] = df["DESCRIPTION"].fillna(df["MAT_DESC"]).fillna(df["MAT_CODE"])
    df["공정"] = df["FLOW_CODE"].map(FLOW_MAP).fillna("기타")
    df["상태"] = df["ORD_STATUS"].map(STATUS_MAP).fillna(df["ORD_STATUS"])
    for c in ["ORD_QTY", "ORD_OUT_QTY", "ORD_IN_QTY", "RCV_GOOD_QTY", "RCV_LOSS_QTY"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    df["달성률"] = (df["ORD_OUT_QTY"] / df["ORD_QTY"].replace(0, 1) * 100).round(1)
    df["불량률"] = (df["RCV_LOSS_QTY"] / (df["RCV_GOOD_QTY"] + df["RCV_LOSS_QTY"]).replace(0, 1) * 100).round(2)
    df["충전일"] = df["PLAN_DATE"].apply(
        lambda x: f"{str(x)[:4]}-{str(x)[4:6]}-{str(x)[6:8]}" if x and len(str(x)) >= 8 else None)
    df["충전DT"] = pd.to_datetime(df["충전일"], errors="coerce")
    df["WEEK"] = df["충전DT"].dt.isocalendar().week.astype(str).apply(
        lambda x: f"W{int(x):02d}" if x != "<NA>" else "-")
    return df, cmap


@st.cache_data(ttl=300)
def load_orders():
    try:
        conn = pymssql.connect(**CONN)
        df = pd.read_sql("""
            SELECT o.FACTORY_CODE, o.ORDER_NO, o.PLAN_DATE, o.ORD_DATE, o.ORD_STATUS,
                   o.CUSTOMER_CODE, o.MAT_CODE, o.ORD_QTY, o.ORD_OUT_QTY, o.ORD_IN_QTY,
                   o.RCV_GOOD_QTY, o.RCV_LOSS_QTY,
                   o.ORD_CMF_3 AS SO_NO, o.ORD_CMF_5 AS DESCRIPTION,
                   o.LINE_CODE, o.FLOW_CODE,
                   o.ORD_START_TIME, o.ORD_END_TIME,
                   m.MAT_DESC
            FROM MWIPORDSTS o
            LEFT JOIN MWIPMATDEF m ON o.MAT_CODE = m.MAT_CODE
            ORDER BY o.PLAN_DATE DESC
        """, conn)
        cust = pd.read_sql("SELECT CUSTOMER_CODE, CUSTOMER_DESC FROM MWIPCUSDEF", conn)
        conn.close()
        cmap = dict(zip(cust["CUSTOMER_CODE"], cust["CUSTOMER_DESC"]))
        return _process_df(df, cmap)
    except Exception:
        # DB 접속 실패 → mock 데이터
        df, cmap = _mock_data()
        return _process_df(df, cmap)


df, cust_map = load_orders()
active = df[df["ORD_STATUS"].isin(["PROCESS", "WAIT"])]

# ══════════════════════════════════════════
# 사이드바
# ══════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🏭 C&C International")
    st.markdown("---")

    page = st.radio("", [
        "📊 영업 파이프라인",
        "📅 납기변경 이력",
        "🏭 생산 현황",
        "📦 구매/자재",
        "🔬 품질(QC)",
    ], label_visibility="collapsed")

    st.markdown("---")

    # 공통 필터
    custs = ["전체"] + sorted(active["고객명"].dropna().unique().tolist())
    sel_cust = st.selectbox("🏢 고객사", custs)
    sel_fac = st.selectbox("🏭 공장", ["전체"] + list(FACTORY.values()))

    st.markdown("---")
    st.caption(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if st.button("🔄 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# 필터 적용
flt = df.copy()
if sel_cust != "전체":
    flt = flt[flt["고객명"] == sel_cust]
if sel_fac != "전체":
    fac_code = {v: k for k, v in FACTORY.items()}.get(sel_fac)
    if fac_code:
        flt = flt[flt["FACTORY_CODE"] == fac_code]
flt_active = flt[flt["ORD_STATUS"].isin(["PROCESS", "WAIT"])]


def kpi_html(label, value, color="#e2e8f0", sub=""):
    return f"""<div class="kpi">
        <div class="lbl">{label}</div>
        <div class="num" style="color:{color}">{value}</div>
        <div class="sub">{sub}</div>
    </div>"""


# ══════════════════════════════════════════
# PAGE 1: 영업 파이프라인
# ══════════════════════════════════════════
if page == "📊 영업 파이프라인":
    st.markdown("## 📊 영업 오더 파이프라인")

    total_q = flt_active["ORD_QTY"].sum()
    done_q = flt_active["ORD_OUT_QTY"].sum()
    pct = (done_q / total_q * 100) if total_q > 0 else 0
    pct_c = "#48BB78" if pct >= 80 else ("#ECC94B" if pct >= 50 else "#FC8181")

    st.markdown(f"""<div class="kpi-row">
        {kpi_html("진행 오더", len(flt_active), "#63b3ed", f"🔄{len(flt_active[flt_active['ORD_STATUS']=='PROCESS'])} ⏳{len(flt_active[flt_active['ORD_STATUS']=='WAIT'])}")}
        {kpi_html("계획 수량", f"{total_q:,.0f}", sub="EA")}
        {kpi_html("완료 수량", f"{done_q:,.0f}", "#48BB78", "EA")}
        {kpi_html("달성률", f"{pct:.1f}%", pct_c, "목표 100%")}
        {kpi_html("고객수", flt_active['고객명'].nunique(), "#9F7AEA", "활성")}
    </div>""", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["🔄 오더 파이프라인", "📅 타임라인", "🚨 납기 리스크", "📋 전체 리스트"])

    # -- 오더 파이프라인 카드 --
    with tab1:
        search = st.text_input("🔍 검색 (품명, 수주번호)", placeholder="멜팅밤, 30001924...")
        orders_show = flt_active.drop_duplicates(subset=["ORDER_NO"])
        if search:
            mask = orders_show.apply(lambda r: search.lower() in str(r.values).lower(), axis=1)
            orders_show = orders_show[mask]

        for _, row in orders_show.head(20).iterrows():
            status = row["상태"]
            badge = "badge-process" if status == "진행중" else ("badge-wait" if status == "대기" else "badge-close")
            pv = row["달성률"]
            pc = "#48BB78" if pv >= 80 else ("#ECC94B" if pv >= 50 else "#63b3ed")

            if row["ORD_STATUS"] == "CLOSE":
                stg = ["stage-done"] * 5
            elif row["ORD_STATUS"] == "PROCESS":
                stg = ["stage-done", "stage-done", "stage-active", "stage-wait", "stage-wait"] if pv > 0 else ["stage-done", "stage-active", "stage-wait", "stage-wait", "stage-wait"]
            else:
                stg = ["stage-done", "stage-wait", "stage-wait", "stage-wait", "stage-wait"]

            plan_dt = row["충전DT"]
            od = row["충전일"] or "-"
            if pd.notna(plan_dt):
                qs = (plan_dt + timedelta(days=1)).strftime("%m-%d")
                qe = (plan_dt + timedelta(days=5)).strftime("%m-%d")
                sd = (plan_dt + timedelta(days=6)).strftime("%m-%d")
            else:
                qs = qe = sd = "-"

            if row["ORD_STATUS"] == "CLOSE":
                do, dm, dp, dq, ds = ["<div class='stage-date done'>✓ 완료</div>"] * 5
            elif row["ORD_STATUS"] == "PROCESS" and pv > 0:
                do = "<div class='stage-date done'>✓ 완료</div>"
                dm = "<div class='stage-date done'>✓ 완료</div>"
                dp = f"<div class='stage-date active'>{od[-5:]} 진행중</div>"
                dq = f"<div class='stage-date plan'>{qs}~{qe} 예정</div>"
                ds = f"<div class='stage-date plan'>{sd} 예정</div>"
            elif row["ORD_STATUS"] == "PROCESS":
                do = "<div class='stage-date done'>✓ 완료</div>"
                dm = "<div class='stage-date active'>진행중</div>"
                dp = f"<div class='stage-date plan'>{od[-5:]} 예정</div>"
                dq = f"<div class='stage-date plan'>{qs}~{qe} 예정</div>"
                ds = f"<div class='stage-date plan'>{sd} 예정</div>"
            else:
                do = "<div class='stage-date done'>✓ 완료</div>"
                dm = "<div class='stage-date plan'>준비중</div>"
                dp = f"<div class='stage-date plan'>{od[-5:]} 예정</div>"
                dq = f"<div class='stage-date plan'>{qs}~{qe} 예정</div>"
                ds = f"<div class='stage-date plan'>{sd} 예정</div>"

            so = row["SO_NO"] if pd.notna(row["SO_NO"]) else "-"
            st.markdown(f"""
            <div class="order-card">
                <div class="order-header">
                    <div class="order-title">{row['품명'][:35]}</div>
                    <span class="order-badge {badge}">{status}</span>
                </div>
                <div class="order-meta">
                    <span>🏢 {row['고객명']}</span><span>🏭 {row['공장']}</span>
                    <span>📋 수주# {so}</span><span>🔧 {row['공정']}</span>
                </div>
                <div class="pipe-row">
                    <div class="pipe-stage {stg[0]}">📝 발주{do}</div><span class="pipe-arrow">→</span>
                    <div class="pipe-stage {stg[1]}">📦 자재{dm}</div><span class="pipe-arrow">→</span>
                    <div class="pipe-stage {stg[2]}">⚙️ {row['공정']}<div class='stage-qty'>{row['ORD_OUT_QTY']:,}/{row['ORD_QTY']:,}</div>{dp}</div><span class="pipe-arrow">→</span>
                    <div class="pipe-stage {stg[3]}">🔬 QC{dq}</div><span class="pipe-arrow">→</span>
                    <div class="pipe-stage {stg[4]}">🚚 출고{ds}</div>
                </div>
                <div style="margin-top:10px">
                    <div style="display:flex;justify-content:space-between;font-size:11px;color:#718096;margin-bottom:3px">
                        <span>진행률</span><span style="color:{pc}">{pv:.0f}%</span>
                    </div>
                    <div class="progress-wrap"><div class="progress-fill" style="width:{min(pv,100):.0f}%;background:{pc};"></div></div>
                </div>
            </div>""", unsafe_allow_html=True)

            # 상세보기 expander
            with st.expander(f"📋 상세보기 — {row['ORDER_NO']} {row['품명'][:20]}"):
                dc1, dc2 = st.columns(2)
                with dc1:
                    st.markdown("##### 📌 오더 정보")
                    detail_info = {
                        "작업지시번호": row["ORDER_NO"],
                        "수주번호": so,
                        "품명": row["품명"],
                        "자재코드": row["MAT_CODE"],
                        "고객": row["고객명"],
                        "공장": row["공장"],
                        "라인": row["LINE_CODE"],
                        "공정": row["공정"],
                        "상태": status,
                    }
                    for k, v in detail_info.items():
                        st.markdown(f"**{k}:** {v}")

                with dc2:
                    st.markdown("##### 📅 일정 정보")
                    sched_info = {
                        "생산계획일(충전)": od,
                        "QC 예정": f"{qs} ~ {qe} (5일)",
                        "출고 예정": sd,
                        "계획수량": f"{row['ORD_QTY']:,} EA",
                        "완료수량": f"{row['ORD_OUT_QTY']:,} EA",
                        "투입수량": f"{row['ORD_IN_QTY']:,} EA",
                        "양품입고": f"{row['RCV_GOOD_QTY']:,} EA",
                        "불량입고": f"{row['RCV_LOSS_QTY']:,} EA",
                        "달성률": f"{pv:.1f}%",
                    }
                    for k, v in sched_info.items():
                        st.markdown(f"**{k}:** {v}")

                st.markdown("##### 📝 변동이력 (샘플)")
                st.caption("실제 DB 연결 시 MWIPLOTSTS의 ORG_DUE_TIME/SCH_DUE_TIME 변경 이력이 표시됩니다")
                change_log = pd.DataFrame({
                    "일시": ["03-25 09:30", "03-22 14:00", "03-18 11:20", "03-10 16:45"],
                    "항목": ["납기 변경", "생산계획 변경", "자재 입고", "발주 등록"],
                    "변경전": ["04-10", "03-28", "-", "-"],
                    "변경후": ["03-25", "03-23", "원료 3종 입고", "오더 생성"],
                    "변경자": ["영업팀", "생산팀", "구매팀", "영업팀"],
                    "비고": ["고객 요청 납기 앞당김", "납기 변경 반영", "정상 입고", "신규"],
                })
                st.dataframe(change_log, use_container_width=True, hide_index=True)

        if len(orders_show) > 20:
            st.caption(f"상위 20건 (전체 {len(orders_show)}건)")

    # -- 타임라인 --
    with tab2:
        st.markdown("#### 충전 → QC(5일) → 출고 타임라인")
        tl = flt_active[flt_active["충전DT"].notna()].drop_duplicates(subset=["ORDER_NO"]).head(15)
        if not tl.empty:
            rows = []
            for _, r in tl.iterrows():
                ps = r["충전DT"]; pe = ps + timedelta(days=1)
                lbl = f"{r['SO_NO'] or r['ORDER_NO']} {r['품명'][:12]}"
                rows.append({"오더": lbl, "구분": r["공정"], "시작": ps, "종료": pe})
                rows.append({"오더": lbl, "구분": "QC (5일)", "시작": pe, "종료": pe + timedelta(days=5)})
                rows.append({"오더": lbl, "구분": "출고가능", "시작": pe + timedelta(days=5), "종료": pe + timedelta(days=6)})
            gdf = pd.DataFrame(rows)
            fig = px.timeline(gdf, x_start="시작", x_end="종료", y="오더", color="구분",
                              color_discrete_map={"충전": "#4299E1", "포장": "#9F7AEA", "제조": "#ED8936",
                                                  "타정": "#38B2AC", "본딩": "#FC8181",
                                                  "QC (5일)": "#ECC94B", "출고가능": "#48BB78", "기타": "#A0AEC0"})
            fig.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1a2e", font=dict(color="#e2e8f0"),
                              yaxis=dict(autorange="reversed", title=""), xaxis_title="",
                              legend=dict(orientation="h", yanchor="bottom", y=1.02),
                              margin=dict(l=10, r=10, t=40, b=10), height=max(350, len(tl) * 45))
            today_s = datetime.now().strftime("%Y-%m-%d")
            fig.add_shape(type="line", x0=today_s, x1=today_s, y0=0, y1=1, yref="paper",
                          line=dict(color="#FC8181", width=2, dash="dash"))
            fig.add_annotation(x=today_s, y=1, yref="paper", text="오늘",
                               font=dict(color="#FC8181", size=12), showarrow=False, yshift=10)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("데이터 없음")

    # -- 납기 리스크 --
    with tab3:
        st.markdown("#### 🚨 충전~납기 간격 (QC 5일 필요)")
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            st.markdown(f"""{kpi_html("🔴 QC 불가", "3건", "#FC8181", "0~2일")}""", unsafe_allow_html=True)
        with rc2:
            st.markdown(f"""{kpi_html("🟡 QC 촉박", "2건", "#ECC94B", "3~4일")}""", unsafe_allow_html=True)
        with rc3:
            st.markdown(f"""{kpi_html("🟢 정상", "1건", "#48BB78", "5일+")}""", unsafe_allow_html=True)
        st.caption("※ 실제 DB 연결 시 자동 계산됩니다 (개발DB는 납기일 미입력)")

        risk_tbl = pd.DataFrame({
            "등급": ["🔴", "🔴", "🔴", "🟡", "🟡", "🟢"],
            "수주#": ["30001924", "30000478", "30001469", "30001262", "30001441", "30000945"],
            "품명": ["멜팅밤", "PJT356", "씨피 듀필름틴트", "브이디엘 치크스테인", "릴리바이레드 팔레트", "PJT154"],
            "공장": ["퍼플", "그린", "그린", "그린", "그린", "그린"],
            "충전일": ["03-23", "03-23", "03-26", "03-28", "03-30", "03-20"],
            "납기일": ["03-25", "03-23", "03-28", "04-01", "04-03", "03-28"],
            "간격": [2, 0, 2, 4, 4, 8], "부족": [3, 5, 3, 1, 1, 0],
            "조치": ["긴급QC+고객협의", "즉시 고객협의", "긴급QC+고객협의", "QC단축", "QC단축", "-"],
        })
        st.dataframe(risk_tbl, use_container_width=True, hide_index=True)

    # -- 전체 리스트 --
    with tab4:
        show = flt[["공장", "ORDER_NO", "상태", "충전일", "SO_NO", "품명", "고객명", "공정",
                     "ORD_QTY", "ORD_OUT_QTY", "달성률", "LINE_CODE"]].copy()
        show.columns = ["공장", "작업지시", "상태", "충전일", "수주#", "품명", "고객", "공정",
                        "계획", "완료", "달성률", "라인"]
        show = show.drop_duplicates()
        srch = st.text_input("🔍 검색", key="srch_all")
        if srch:
            show = show[show.apply(lambda r: srch.lower() in str(r.values).lower(), axis=1)]
        st.dataframe(show, use_container_width=True, hide_index=True, height=500,
                     column_config={"달성률": st.column_config.ProgressColumn("달성률", min_value=0, max_value=100, format="%.1f%%")})
        st.caption(f"총 {len(show)}건")


# ══════════════════════════════════════════
# PAGE 2: 생산 현황
# ══════════════════════════════════════════
elif page == "🏭 생산 현황":
    st.markdown("## 🏭 생산 현황")

    prod = flt[flt["ORD_STATUS"].isin(["PROCESS", "WAIT", "CLOSE"])]
    prod_active = prod[prod["ORD_STATUS"].isin(["PROCESS", "WAIT"])]
    tq = prod_active["ORD_QTY"].sum()
    dq = prod_active["ORD_OUT_QTY"].sum()
    pct = (dq / tq * 100) if tq > 0 else 0
    loss = prod_active["RCV_LOSS_QTY"].sum()
    good = prod_active["RCV_GOOD_QTY"].sum()
    defect_rate = (loss / (good + loss) * 100) if (good + loss) > 0 else 0
    dr_c = "#48BB78" if defect_rate < 3 else ("#ECC94B" if defect_rate < 5 else "#FC8181")

    st.markdown(f"""<div class="kpi-row">
        {kpi_html("진행 오더", len(prod_active), "#63b3ed")}
        {kpi_html("계획", f"{tq:,.0f}", sub="EA")}
        {kpi_html("완료", f"{dq:,.0f}", "#48BB78", "EA")}
        {kpi_html("달성률", f"{pct:.1f}%", "#48BB78" if pct>=80 else "#ECC94B")}
        {kpi_html("불량률", f"{defect_rate:.2f}%", dr_c)}
    </div>""", unsafe_allow_html=True)

    tab_p1, tab_p2, tab_p3 = st.tabs(["📊 공장별", "📈 라인별", "📋 상세"])

    with tab_p1:
        c1, c2 = st.columns(2)
        with c1:
            fac_grp = prod_active.groupby("공장").agg(계획=("ORD_QTY", "sum"), 완료=("ORD_OUT_QTY", "sum")).reset_index()
            fig = px.bar(fac_grp, x="공장", y=["계획", "완료"], barmode="group", color_discrete_sequence=["#4299E1", "#48BB78"],
                         title="공장별 계획 vs 완료")
            fig.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1a2e", font_color="#e2e8f0",
                              margin=dict(l=20, r=20, t=50, b=20), legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fac_grp["달성률"] = (fac_grp["완료"] / fac_grp["계획"].replace(0, 1) * 100).round(1)
            fig2 = px.pie(fac_grp, values="계획", names="공장", color="공장", color_discrete_map=FAC_COLOR,
                          title="공장별 계획 비중", hole=0.5)
            fig2.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1a2e", font_color="#e2e8f0",
                               margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(fig2, use_container_width=True)

        st.dataframe(fac_grp, use_container_width=True, hide_index=True,
                     column_config={"달성률": st.column_config.ProgressColumn("달성률", min_value=0, max_value=100, format="%.1f%%")})

    with tab_p2:
        line_grp = prod_active.groupby(["공장", "LINE_CODE", "공정"]).agg(
            오더=("ORDER_NO", "nunique"), 계획=("ORD_QTY", "sum"), 완료=("ORD_OUT_QTY", "sum")
        ).reset_index()
        line_grp["달성률"] = (line_grp["완료"] / line_grp["계획"].replace(0, 1) * 100).round(1)
        line_grp = line_grp.sort_values("계획", ascending=False)

        fig3 = px.bar(line_grp.head(15), x="LINE_CODE", y="계획", color="공장", color_discrete_map=FAC_COLOR,
                      title="라인별 계획 수량 (상위 15)")
        fig3.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1a2e", font_color="#e2e8f0",
                           margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig3, use_container_width=True)

        st.dataframe(line_grp, use_container_width=True, hide_index=True,
                     column_config={"달성률": st.column_config.ProgressColumn("달성률", min_value=0, max_value=100, format="%.1f%%")})

    with tab_p3:
        p_show = prod[["공장", "ORDER_NO", "상태", "충전일", "공정", "LINE_CODE", "품명",
                        "ORD_QTY", "ORD_OUT_QTY", "달성률"]].drop_duplicates()
        p_show.columns = ["공장", "작업지시", "상태", "충전일", "공정", "라인", "품명", "계획", "완료", "달성률"]
        st.dataframe(p_show, use_container_width=True, hide_index=True, height=500,
                     column_config={"달성률": st.column_config.ProgressColumn("달성률", min_value=0, max_value=100, format="%.1f%%")})


# ══════════════════════════════════════════
# PAGE 3: 구매/자재
# ══════════════════════════════════════════
elif page == "📦 구매/자재":
    st.markdown("## 📦 구매/자재 현황")

    mat_active = flt_active.copy()
    total_orders = len(mat_active.drop_duplicates(subset=["ORDER_NO"]))
    mat_types = mat_active["MAT_CODE"].nunique()
    in_qty = mat_active["ORD_IN_QTY"].sum()

    st.markdown(f"""<div class="kpi-row">
        {kpi_html("진행 오더", total_orders, "#63b3ed")}
        {kpi_html("자재 종류", mat_types, "#ED8936")}
        {kpi_html("투입 수량", f"{in_qty:,.0f}", "#48BB78", "EA")}
        {kpi_html("양품 입고", f"{mat_active['RCV_GOOD_QTY'].sum():,.0f}", "#48BB78")}
        {kpi_html("불량 입고", f"{mat_active['RCV_LOSS_QTY'].sum():,.0f}", "#FC8181")}
    </div>""", unsafe_allow_html=True)

    tab_m1, tab_m2 = st.tabs(["📊 공장별 자재현황", "📋 상세"])

    with tab_m1:
        mat_grp = mat_active.groupby("공장").agg(
            자재종류=("MAT_CODE", "nunique"), 투입=("ORD_IN_QTY", "sum"),
            양품=("RCV_GOOD_QTY", "sum"), 불량=("RCV_LOSS_QTY", "sum")
        ).reset_index()

        fig = px.bar(mat_grp, x="공장", y=["양품", "불량"], barmode="stack",
                     color_discrete_sequence=["#48BB78", "#FC8181"], title="공장별 입고 현황")
        fig.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1a2e", font_color="#e2e8f0",
                          margin=dict(l=20, r=20, t=50, b=20), legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(mat_grp, use_container_width=True, hide_index=True)

    with tab_m2:
        m_show = mat_active[["공장", "ORDER_NO", "MAT_CODE", "품명", "ORD_IN_QTY",
                              "RCV_GOOD_QTY", "RCV_LOSS_QTY"]].drop_duplicates()
        m_show.columns = ["공장", "작업지시", "자재코드", "품명", "투입", "양품입고", "불량입고"]
        st.dataframe(m_show, use_container_width=True, hide_index=True, height=500)


# ══════════════════════════════════════════
# PAGE 4: 품질(QC)
# ══════════════════════════════════════════
elif page == "🔬 품질(QC)":
    st.markdown("## 🔬 품질(QC) 현황")

    good = flt["RCV_GOOD_QTY"].sum()
    loss = flt["RCV_LOSS_QTY"].sum()
    total = good + loss
    dr = (loss / total * 100) if total > 0 else 0
    dr_c = "#48BB78" if dr < 3 else ("#ECC94B" if dr < 5 else "#FC8181")

    st.markdown(f"""<div class="kpi-row">
        {kpi_html("총 검사량", f"{total:,.0f}", sub="EA")}
        {kpi_html("양품", f"{good:,.0f}", "#48BB78")}
        {kpi_html("불량", f"{loss:,.0f}", "#FC8181")}
        {kpi_html("불량률", f"{dr:.2f}%", dr_c)}
        {kpi_html("QC 필요일", "5일", "#ECC94B", "충전 후")}
    </div>""", unsafe_allow_html=True)

    tab_q1, tab_q2, tab_q3 = st.tabs(["📊 공장별 불량", "🚨 긴급 QC", "📋 상세"])

    with tab_q1:
        c1, c2 = st.columns(2)
        with c1:
            q_grp = flt.groupby("공장").agg(양품=("RCV_GOOD_QTY", "sum"), 불량=("RCV_LOSS_QTY", "sum")).reset_index()
            q_grp["불량률"] = (q_grp["불량"] / (q_grp["양품"] + q_grp["불량"]).replace(0, 1) * 100).round(2)
            fig = px.bar(q_grp, x="공장", y="불량률", color="공장", color_discrete_map=FAC_COLOR, title="공장별 불량률")
            fig.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1a2e", font_color="#e2e8f0",
                              margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            proc_grp = flt.groupby("공정").agg(양품=("RCV_GOOD_QTY", "sum"), 불량=("RCV_LOSS_QTY", "sum")).reset_index()
            proc_grp["불량률"] = (proc_grp["불량"] / (proc_grp["양품"] + proc_grp["불량"]).replace(0, 1) * 100).round(2)
            fig2 = px.bar(proc_grp, x="공정", y="불량률", title="공정별 불량률",
                          color_discrete_sequence=["#ED8936"])
            fig2.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1a2e", font_color="#e2e8f0",
                               margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(fig2, use_container_width=True)

    with tab_q2:
        st.markdown("#### 긴급 품질검사 요청 리스트")
        st.caption("충전~납기 5일 미만 → QC 단축/긴급 검사 필요")
        urgent = pd.DataFrame({
            "긴급도": ["🔴 즉시", "🔴 즉시", "🟡 단축", "🟡 단축"],
            "수주#": ["30001924", "30000478", "30001262", "30001441"],
            "품명": ["멜팅밤", "PJT2025120356", "브이디엘 치크스테인", "릴리바이레드 팔레트"],
            "공장": ["퍼플", "그린", "그린", "그린"],
            "충전일": ["03-23", "03-23", "03-28", "03-30"],
            "납기일": ["03-25", "03-23", "04-01", "04-03"],
            "QC가용일": ["2일", "0일", "4일", "4일"],
            "필요조치": ["1일 긴급검사", "출하전 서류검사만", "3일 단축검사", "3일 단축검사"],
        })
        st.dataframe(urgent, use_container_width=True, hide_index=True)

    with tab_q3:
        qc_show = flt[["공장", "ORDER_NO", "공정", "품명", "RCV_GOOD_QTY", "RCV_LOSS_QTY", "불량률"]].drop_duplicates()
        qc_show.columns = ["공장", "작업지시", "공정", "품명", "양품", "불량", "불량률"]
        qc_show = qc_show.sort_values("불량률", ascending=False)
        st.dataframe(qc_show, use_container_width=True, hide_index=True, height=500)


# ══════════════════════════════════════════
# PAGE 5: 납기변경 이력
# ══════════════════════════════════════════
elif page == "📅 납기변경 이력":
    st.markdown("## 📅 납기변경 — 불일치 모니터링")
    st.caption("납기 변경 후 구매/생산/QC 일정이 맞지 않는 오더를 찾습니다")

    # KPI
    st.markdown(f"""<div class="kpi-row">
        {kpi_html("납기 변경", "8건", "#ECC94B", "이번주")}
        {kpi_html("🏭 생산 불일치", "3건", "#FC8181", "생산일정 미조정")}
        {kpi_html("📦 구매 불일치", "2건", "#ED8936", "자재 미입고")}
        {kpi_html("🔬 QC 불일치", "4건", "#FC8181", "QC 5일 부족")}
        {kpi_html("✅ 정상", "2건", "#48BB78", "모두 반영됨")}
    </div>""", unsafe_allow_html=True)

    tab_d1, tab_d2, tab_d3, tab_d4 = st.tabs([
        "🏭 생산일정 불일치", "📦 구매일정 불일치", "🔬 QC일정 불일치", "📋 전체 변경이력"
    ])

    # -- 생산일정 불일치 --
    with tab_d1:
        st.markdown("#### 🏭 납기 변경 → 생산일정 미반영")
        st.markdown("> 납기가 앞당겨졌는데 **생산계획이 그대로**인 오더")

        prod_mismatch = pd.DataFrame({
            "긴급도": ["🔴", "🔴", "🟡"],
            "수주#": ["30001924", "30000478", "30001262"],
            "품명": ["멜팅밤", "PJT2025120356", "브이디엘 치크스테인"],
            "고객": ["A사", "B사", "D사"],
            "공장": ["퍼플", "그린", "그린"],
            "원래납기": ["04-10", "04-05", "04-15"],
            "변경납기": ["03-25", "03-23", "04-01"],
            "당김일수": [16, 13, 14],
            "현재 생산계획일": ["03-23", "03-23", "03-28"],
            "생산계획 변경": ["❌ 미변경", "❌ 미변경", "❌ 미변경"],
            "필요조치": ["즉시 생산일정 앞당김", "즉시 생산일정 앞당김", "생산일정 재조정"],
        })
        st.dataframe(prod_mismatch, use_container_width=True, hide_index=True)

        st.markdown("")
        st.markdown("##### 타임라인 비교 — 생산 → QC(5일) → 변경납기")
        tl = pd.DataFrame([
            {"오더": "30001924 멜팅밤", "구분": "생산계획", "시작": "2026-03-23", "종료": "2026-03-24"},
            {"오더": "30001924 멜팅밤", "구분": "QC 5일", "시작": "2026-03-24", "종료": "2026-03-29"},
            {"오더": "30001924 멜팅밤", "구분": "변경납기", "시작": "2026-03-25", "종료": "2026-03-26"},
            {"오더": "30000478 PJT356", "구분": "생산계획", "시작": "2026-03-23", "종료": "2026-03-24"},
            {"오더": "30000478 PJT356", "구분": "QC 5일", "시작": "2026-03-24", "종료": "2026-03-29"},
            {"오더": "30000478 PJT356", "구분": "변경납기", "시작": "2026-03-23", "종료": "2026-03-24"},
            {"오더": "30001262 브이디엘", "구분": "생산계획", "시작": "2026-03-28", "종료": "2026-03-29"},
            {"오더": "30001262 브이디엘", "구분": "QC 5일", "시작": "2026-03-29", "종료": "2026-04-03"},
            {"오더": "30001262 브이디엘", "구분": "변경납기", "시작": "2026-04-01", "종료": "2026-04-02"},
        ])
        tl["시작"] = pd.to_datetime(tl["시작"]); tl["종료"] = pd.to_datetime(tl["종료"])
        fig = px.timeline(tl, x_start="시작", x_end="종료", y="오더", color="구분",
                          color_discrete_map={"생산계획": "#4299E1", "QC 5일": "#ECC94B", "변경납기": "#FC8181"})
        fig.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1a2e", font_color="#e2e8f0",
                          yaxis=dict(autorange="reversed", title=""), xaxis_title="",
                          legend=dict(orientation="h", y=1.05), margin=dict(l=10, r=10, t=40, b=10), height=280)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("🔵 생산계획  |  🟡 QC 5일  |  🔴 변경납기 — 납기가 QC 구간 안에 있으면 일정 조정 필요")

    # -- 구매일정 불일치 --
    with tab_d2:
        st.markdown("#### 📦 납기 변경 → 자재 미입고")
        st.markdown("> 납기가 앞당겨졌는데 **자재가 아직 입고되지 않은** 오더")

        pur_mismatch = pd.DataFrame({
            "긴급도": ["🔴", "🟡"],
            "수주#": ["30001924", "30001469"],
            "품명": ["멜팅밤", "씨피 듀 필름 틴트"],
            "고객": ["A사", "C사"],
            "공장": ["퍼플", "그린"],
            "변경납기": ["03-25", "03-28"],
            "필요자재": ["원료 3종, 용기 1종", "원료 2종, 부자재 3종"],
            "입고현황": ["원료 1종 미입고", "부자재 2종 미입고"],
            "입고예정일": ["03-24 (1일전)", "03-27 (1일전)"],
            "리스크": ["🔴 입고 지연시 생산 불가", "🟡 입고 촉박"],
            "필요조치": ["납품사 긴급 독촉", "입고일 확인"],
        })
        st.dataframe(pur_mismatch, use_container_width=True, hide_index=True)

        st.markdown("")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"""{kpi_html("자재 미입고 오더", "2건", "#ED8936")}""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""{kpi_html("입고 지연 예상", "1건", "#FC8181")}""", unsafe_allow_html=True)

    # -- QC일정 불일치 --
    with tab_d3:
        st.markdown("#### 🔬 납기 변경 → QC 5일 부족")
        st.markdown("> 납기가 앞당겨져서 **충전~납기 간격이 5일 미만**이 된 오더")

        qc_mismatch = pd.DataFrame({
            "긴급도": ["🔴 QC불가", "🔴 QC불가", "🟡 QC촉박", "🟡 QC촉박"],
            "수주#": ["30001924", "30000478", "30001262", "30001441"],
            "품명": ["멜팅밤", "PJT2025120356", "브이디엘 치크스테인", "릴리바이레드 팔레트"],
            "고객": ["A사", "B사", "D사", "E사"],
            "공장": ["퍼플", "그린", "그린", "그린"],
            "충전일": ["03-23", "03-23", "03-28", "03-30"],
            "변경납기": ["03-25", "03-23", "04-01", "04-03"],
            "충전~납기": ["2일", "0일", "4일", "4일"],
            "QC부족": ["3일 부족", "5일 부족", "1일 부족", "1일 부족"],
            "필요조치": ["긴급QC(1일)+고객협의", "QC생략 불가→고객 납기재협의", "QC 4일 단축검사", "QC 4일 단축검사"],
        })
        st.dataframe(qc_mismatch, use_container_width=True, hide_index=True)

        st.markdown("")
        # QC 타임라인
        qc_tl = pd.DataFrame([
            {"오더": "30001924 멜팅밤", "구분": "충전", "시작": "2026-03-23", "종료": "2026-03-24"},
            {"오더": "30001924 멜팅밤", "구분": "QC필요(5일)", "시작": "2026-03-24", "종료": "2026-03-29"},
            {"오더": "30001924 멜팅밤", "구분": "변경납기", "시작": "2026-03-25", "종료": "2026-03-26"},
            {"오더": "30000478 PJT356", "구분": "충전", "시작": "2026-03-23", "종료": "2026-03-24"},
            {"오더": "30000478 PJT356", "구분": "QC필요(5일)", "시작": "2026-03-24", "종료": "2026-03-29"},
            {"오더": "30000478 PJT356", "구분": "변경납기", "시작": "2026-03-23", "종료": "2026-03-24"},
            {"오더": "30001262 브이디엘", "구분": "충전", "시작": "2026-03-28", "종료": "2026-03-29"},
            {"오더": "30001262 브이디엘", "구분": "QC필요(5일)", "시작": "2026-03-29", "종료": "2026-04-03"},
            {"오더": "30001262 브이디엘", "구분": "변경납기", "시작": "2026-04-01", "종료": "2026-04-02"},
        ])
        qc_tl["시작"] = pd.to_datetime(qc_tl["시작"]); qc_tl["종료"] = pd.to_datetime(qc_tl["종료"])
        fig2 = px.timeline(qc_tl, x_start="시작", x_end="종료", y="오더", color="구분",
                           color_discrete_map={"충전": "#4299E1", "QC필요(5일)": "#ECC94B", "변경납기": "#FC8181"})
        fig2.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1a2e", font_color="#e2e8f0",
                           yaxis=dict(autorange="reversed", title=""), xaxis_title="",
                           legend=dict(orientation="h", y=1.05), margin=dict(l=10, r=10, t=40, b=10), height=260)
        st.plotly_chart(fig2, use_container_width=True)
        st.caption("🔵 충전  |  🟡 QC 5일 필요구간  |  🔴 변경납기 — 납기가 QC구간 안에 있으면 불일치")

    # -- 전체 변경이력 --
    with tab_d4:
        st.markdown("#### 전체 납기변경 이력")
        search_d = st.text_input("🔍 검색", key="srch_due", placeholder="수주번호, 품명, 고객...")

        all_changes = pd.DataFrame({
            "변경일": ["03-25", "03-24", "03-23", "03-22", "03-22", "03-20", "03-19", "03-18"],
            "수주#": ["30001924", "30000478", "30001469", "30001262", "30001611", "30001441", "30000945", "30000659"],
            "품명": ["멜팅밤", "PJT356", "씨피 듀필름틴트", "브이디엘 치크스테인", "PO-057527", "릴리바이레드 팔레트", "PJT154", "PJT175"],
            "고객": ["A사", "B사", "C사", "D사", "F사", "E사", "G사", "H사"],
            "원래납기": ["04-10", "04-05", "03-30", "04-15", "04-20", "04-08", "04-01", "04-12"],
            "변경납기": ["03-25", "03-23", "03-28", "04-01", "04-10", "04-03", "03-28", "04-05"],
            "변동": ["-16일", "-13일", "-2일", "-14일", "-10일", "-5일", "-4일", "-7일"],
            "생산": ["❌", "❌", "✅", "❌", "✅", "✅", "✅", "❌"],
            "구매": ["❌", "✅", "✅", "✅", "✅", "✅", "✅", "❌"],
            "QC": ["❌", "❌", "✅", "❌", "✅", "❌", "✅", "❌"],
            "종합": ["🔴 3건 불일치", "🔴 2건 불일치", "🟢 정상", "🔴 2건 불일치", "🟢 정상",
                   "🟡 1건 불일치", "🟢 정상", "🔴 3건 불일치"],
        })

        if search_d:
            all_changes = all_changes[all_changes.apply(lambda r: search_d.lower() in str(r.values).lower(), axis=1)]

        st.dataframe(all_changes, use_container_width=True, hide_index=True, height=350)

        st.markdown("---")
        st.markdown("#### 일별 납기변경 트렌드")
        trend = pd.DataFrame({
            "날짜": pd.date_range("2026-03-01", periods=27, freq="D"),
            "변경건수": [0,1,0,2,1,0,0,3,2,1,0,0,1,0,2,3,1,0,0,2,1,3,2,1,0,1,0],
        })
        fig3 = px.bar(trend, x="날짜", y="변경건수", title="일별 납기변경 건수",
                      color_discrete_sequence=["#ECC94B"])
        fig3.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1a2e", font_color="#e2e8f0",
                           margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig3, use_container_width=True)
