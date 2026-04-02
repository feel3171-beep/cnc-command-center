"""이상 알람 - 불량률 급증, 설비 알람, 생산 지연 감지"""

from datetime import datetime
import db
import config
from slack_sender import (
    send_message, fmt_num, fmt_pct,
    divider, header_block, section_block, context_block,
)


def check_defect_alerts(plan_date):
    """불량률 임계값 초과 작업지시 감지"""
    sql = """
        SELECT
            o.FACTORY_CODE,
            o.ORDER_NO,
            o.LINE_CODE,
            l.LINE_DESC,
            m.MAT_DESC,
            o.ORD_OUT_QTY as PROD_QTY,
            o.RCV_GOOD_QTY as GOOD_QTY,
            o.RCV_LOSS_QTY as LOSS_QTY,
            CASE WHEN (o.RCV_GOOD_QTY + o.RCV_LOSS_QTY) > 0
                 THEN CAST(100.0 * o.RCV_LOSS_QTY / (o.RCV_GOOD_QTY + o.RCV_LOSS_QTY) AS decimal(5,2))
                 ELSE 0 END as DEFECT_RATE
        FROM MWIPORDSTS o
        LEFT JOIN MWIPLINDEF l ON o.FACTORY_CODE = l.FACTORY_CODE AND o.LINE_CODE = l.LINE_CODE
        LEFT JOIN MWIPMATDEF m ON o.FACTORY_CODE = m.FACTORY_CODE AND o.MAT_CODE = m.MAT_CODE
        WHERE o.PLAN_DATE = %s
          AND (o.RCV_GOOD_QTY + o.RCV_LOSS_QTY) > 0
          AND CAST(100.0 * o.RCV_LOSS_QTY / (o.RCV_GOOD_QTY + o.RCV_LOSS_QTY) AS decimal(5,2)) >= %s
        ORDER BY DEFECT_RATE DESC
    """
    return db.query(sql, (plan_date, config.ALERT_DEFECT_RATE))


def check_low_achievement(plan_date):
    """생산 달성률 저조 라인 감지"""
    sql = """
        SELECT
            o.FACTORY_CODE,
            o.LINE_CODE,
            l.LINE_DESC,
            SUM(o.ORD_QTY) as PLAN_QTY,
            SUM(o.ORD_OUT_QTY) as PROD_QTY,
            CASE WHEN SUM(o.ORD_QTY) > 0
                 THEN CAST(100.0 * SUM(o.ORD_OUT_QTY) / SUM(o.ORD_QTY) AS decimal(5,2))
                 ELSE 0 END as ACHIEVEMENT
        FROM MWIPORDSTS o
        LEFT JOIN MWIPLINDEF l ON o.FACTORY_CODE = l.FACTORY_CODE AND o.LINE_CODE = l.LINE_CODE
        WHERE o.PLAN_DATE = %s
          AND o.ORD_QTY > 0
        GROUP BY o.FACTORY_CODE, o.LINE_CODE, l.LINE_DESC
        HAVING CAST(100.0 * SUM(o.ORD_OUT_QTY) / SUM(o.ORD_QTY) AS decimal(5,2)) < %s
           AND SUM(o.ORD_QTY) > 0
        ORDER BY ACHIEVEMENT ASC
    """
    return db.query(sql, (plan_date, config.ALERT_ACHIEVEMENT_LOW))


def check_equipment_alarms():
    """미확인 설비/관리 알람 감지"""
    sql = """
        SELECT TOP 10
            ALARM_HIST_ID, TRAN_TIME, FACTORY_CODE,
            ALARM_CODE, ALARM_LEVEL,
            DISPLAY_TITLE, DISPLAY_CONTENTS
        FROM MADMALMHIS
        WHERE ACK_FLAG = 0
          AND ALARM_LEVEL IN ('WARNING', 'CRITICAL')
        ORDER BY TRAN_TIME DESC
    """
    return db.query(sql)


def check_quality_failures(plan_date):
    """품질 검사 불합격 감지"""
    sql = """
        SELECT TOP 10
            INSP_NO, FACTORY_CODE, MAT_CODE,
            INSP_REQ_QTY, NG_QTY,
            JUDGE_RESULT_CODE, LOSS_CODE,
            INSP_TIME
        FROM CQCMREQSTS
        WHERE JUDGE_RESULT_CODE IS NOT NULL
          AND JUDGE_RESULT_CODE != 'OK'
          AND NG_QTY > 0
          AND INSP_TIME >= %s
        ORDER BY INSP_TIME DESC
    """
    date_start = f"{plan_date[:4]}-{plan_date[4:6]}-{plan_date[6:]} 00:00:00"
    return db.query(sql, (date_start,))


def run(target_date=None):
    """알람 체크 실행"""
    today = target_date or datetime.now().strftime("%Y%m%d")
    date_str = f"{today[:4]}-{today[4:6]}-{today[6:]}"
    alerts_found = False
    blocks = [header_block(f"\U0001f6a8 이상 알람 ({date_str})")]

    # 1. 불량률 초과
    defects = check_defect_alerts(today)
    if defects:
        alerts_found = True
        lines = [f"\U0001f534 *불량률 {config.ALERT_DEFECT_RATE}% 초과 ({len(defects)}건)*"]
        for d in defects[:5]:
            fc_name = config.FACTORY_NAMES.get(d["FACTORY_CODE"], d["FACTORY_CODE"])
            mat = d["MAT_DESC"] or d.get("MAT_CODE", "")
            if len(mat) > 20:
                mat = mat[:20] + "..."
            lines.append(
                f"  \u2022 [{fc_name}] {d['LINE_DESC'] or d['LINE_CODE']} | {mat} | "
                f"불량 {fmt_num(d['LOSS_QTY'])}개 (*{fmt_pct(d['DEFECT_RATE'])}*)"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 2. 생산 달성률 저조
    low_ach = check_low_achievement(today)
    if low_ach:
        alerts_found = True
        lines = [f"\U0001f7e1 *생산 달성률 {config.ALERT_ACHIEVEMENT_LOW}% 미만 ({len(low_ach)}건)*"]
        for a in low_ach[:5]:
            fc_name = config.FACTORY_NAMES.get(a["FACTORY_CODE"], a["FACTORY_CODE"])
            lines.append(
                f"  \u2022 [{fc_name}] {a['LINE_DESC'] or a['LINE_CODE']} | "
                f"{fmt_num(a['PROD_QTY'])} / {fmt_num(a['PLAN_QTY'])} (*{fmt_pct(a['ACHIEVEMENT'])}*)"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 3. 미확인 설비 알람
    equip_alarms = check_equipment_alarms()
    if equip_alarms:
        alerts_found = True
        lines = [f"\u26a0\ufe0f *미확인 설비 알람 ({len(equip_alarms)}건)*"]
        for ea in equip_alarms[:5]:
            fc_name = config.FACTORY_NAMES.get(ea["FACTORY_CODE"], ea["FACTORY_CODE"])
            title = ea["DISPLAY_TITLE"] or ea["ALARM_CODE"]
            level = ea["ALARM_LEVEL"]
            lines.append(f"  \u2022 [{fc_name}] [{level}] {title}")
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 4. 품질 검사 불합격
    qc_fails = check_quality_failures(today)
    if qc_fails:
        alerts_found = True
        lines = [f"\U0001f9ea *품질 검사 불합격 ({len(qc_fails)}건)*"]
        for q in qc_fails[:5]:
            fc_name = config.FACTORY_NAMES.get(q["FACTORY_CODE"], q["FACTORY_CODE"])
            lines.append(
                f"  \u2022 [{fc_name}] 검사 {q['INSP_NO']} | NG {fmt_num(q['NG_QTY'])}개 | {q['JUDGE_RESULT_CODE']}"
            )
        blocks.append(section_block("\n".join(lines)))

    if not alerts_found:
        blocks.append(section_block("\u2705 현재 이상 알람이 없습니다."))

    send_message(f"이상 알람 ({date_str})", blocks=blocks)
    print(f"[OK] 이상 알람 전송 완료 ({date_str}), 알람 {'' if alerts_found else '없음'}")


if __name__ == "__main__":
    run()
