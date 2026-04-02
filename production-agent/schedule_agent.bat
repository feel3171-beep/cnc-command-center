@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ================================================
echo  생산 분석 에이전트 - 작업 스케줄러 등록
echo  매일 07:30 자동 실행
echo ================================================
echo.

:: 관리자 권한 확인
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] 관리자 권한으로 실행해주세요.
    echo 이 파일을 우클릭 후 "관리자 권한으로 실행" 선택
    pause
    exit /b 1
)

:: Python 경로 자동 감지
for /f "tokens=*" %%i in ('where python') do set PYTHON_PATH=%%i
echo Python 경로: %PYTHON_PATH%

:: 에이전트 경로
set AGENT_PATH=%~dp0agent.py
echo 에이전트 경로: %AGENT_PATH%

:: 기존 작업 제거 (있을 경우)
schtasks /delete /tn "MES_생산분석_에이전트" /f >nul 2>&1

:: 작업 스케줄러 등록: 매일 07:30
schtasks /create ^
    /tn "MES_생산분석_에이전트" ^
    /tr "\"%PYTHON_PATH%\" \"%AGENT_PATH%\"" ^
    /sc daily ^
    /st 07:30 ^
    /ru "%USERNAME%" ^
    /f

if %errorlevel% equ 0 (
    echo.
    echo ✅ 작업 등록 완료!
    echo    이름: MES_생산분석_에이전트
    echo    실행: 매일 07:30
    echo.
    echo 확인: 작업 스케줄러 열기 ^> "작업 스케줄러 라이브러리"
) else (
    echo ❌ 등록 실패. 관리자 권한 확인 필요.
)

echo.
pause
