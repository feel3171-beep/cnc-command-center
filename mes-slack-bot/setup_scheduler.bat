@echo off
REM ============================================
REM  MES 종합 관리 시스템 - 스케줄러 등록
REM  관리자 권한으로 실행하세요
REM ============================================

SET BOT_DIR=C:\Users\user\Desktop\C^&C\claude\mes-slack-bot
SET PYTHON=python

echo ============================================
echo  기존 봇 (4종)
echo ============================================

echo [1/8] 생산 대시보드 (매일 08:00, 12:00, 17:00)
schtasks /create /tn "MES_Dashboard_08" /tr "%PYTHON% %BOT_DIR%\run_dashboard.py" /sc daily /st 08:00 /f
schtasks /create /tn "MES_Dashboard_12" /tr "%PYTHON% %BOT_DIR%\run_dashboard.py" /sc daily /st 12:00 /f
schtasks /create /tn "MES_Dashboard_17" /tr "%PYTHON% %BOT_DIR%\run_dashboard.py" /sc daily /st 17:00 /f

echo [2/8] 이상 알람 (매 2시간)
schtasks /create /tn "MES_Alert" /tr "%PYTHON% %BOT_DIR%\run_alert.py" /sc daily /st 07:00 /ri 120 /du 14:00 /f

echo [3/8] 주간 리포트 (월요일 09:00)
schtasks /create /tn "MES_WeeklyReport" /tr "%PYTHON% %BOT_DIR%\run_report.py" /sc weekly /d MON /st 09:00 /f

echo [4/8] 재고 알람 (매일 08:30)
schtasks /create /tn "MES_Inventory" /tr "%PYTHON% %BOT_DIR%\run_inventory.py" /sc daily /st 08:30 /f

echo.
echo ============================================
echo  신규 역할별 봇 (4종)
echo ============================================

echo [5/8] 생산 담당자 (교대시간 06:00, 14:00, 22:00 + 2시간마다)
schtasks /create /tn "MES_ProdOps_06" /tr "%PYTHON% %BOT_DIR%\run_prod_ops.py" /sc daily /st 06:00 /f
schtasks /create /tn "MES_ProdOps_14" /tr "%PYTHON% %BOT_DIR%\run_prod_ops.py" /sc daily /st 14:00 /f
schtasks /create /tn "MES_ProdOps_22" /tr "%PYTHON% %BOT_DIR%\run_prod_ops.py" /sc daily /st 22:00 /f
schtasks /create /tn "MES_ProdOps_2h" /tr "%PYTHON% %BOT_DIR%\run_prod_ops.py" /sc daily /st 08:00 /ri 120 /du 12:00 /f

echo [6/8] 영업 담당자 (09:00, 16:00)
schtasks /create /tn "MES_SalesOps_09" /tr "%PYTHON% %BOT_DIR%\run_sales_ops.py" /sc daily /st 09:00 /f
schtasks /create /tn "MES_SalesOps_16" /tr "%PYTHON% %BOT_DIR%\run_sales_ops.py" /sc daily /st 16:00 /f

echo [7/8] 구매 담당자 (08:30)
schtasks /create /tn "MES_PurchaseOps" /tr "%PYTHON% %BOT_DIR%\run_purchase_ops.py" /sc daily /st 08:30 /f

echo [8/9] 납기 변경 감시 (매일 07:30, 13:30)
schtasks /create /tn "MES_DeliveryWatch_07" /tr "%PYTHON% %BOT_DIR%\run_delivery_watch.py" /sc daily /st 07:30 /f
schtasks /create /tn "MES_DeliveryWatch_13" /tr "%PYTHON% %BOT_DIR%\run_delivery_watch.py" /sc daily /st 13:30 /f

echo [9/10] 긴급 품질검사 (매일 07:00, 14:00)
schtasks /create /tn "MES_QC_Urgent_07" /tr "%PYTHON% %BOT_DIR%\run_qc_urgent.py" /sc daily /st 07:00 /f
schtasks /create /tn "MES_QC_Urgent_14" /tr "%PYTHON% %BOT_DIR%\run_qc_urgent.py" /sc daily /st 14:00 /f

echo [10/10] 경영진 브리핑 (매일 18:00 + 주간 월 09:00)
schtasks /create /tn "MES_Executive_Daily" /tr "%PYTHON% %BOT_DIR%\run_executive.py" /sc daily /st 18:00 /f
schtasks /create /tn "MES_Executive_Weekly" /tr "%PYTHON% %BOT_DIR%\run_report.py" /sc weekly /d MON /st 09:00 /f

echo.
echo ============================================
echo  등록 완료!
echo ============================================
echo.
echo  Streamlit 대시보드 실행:
echo  cd %BOT_DIR%\dashboard
echo  streamlit run app.py
echo.
pause
