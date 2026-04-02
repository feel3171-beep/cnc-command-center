@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ================================================
echo  생산 분석 에이전트 시작
echo ================================================
echo.

:: ANTHROPIC_API_KEY 확인
if "%ANTHROPIC_API_KEY%"=="" (
    echo [오류] ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.
    echo.
    echo 설정 방법:
    echo   set ANTHROPIC_API_KEY=sk-ant-xxxxx
    echo   또는 .env 파일에 ANTHROPIC_API_KEY=sk-ant-xxxxx 추가
    echo.
)

:: 패키지 설치 확인
python -c "import fastapi, uvicorn, pyodbc, anthropic" 2>nul
if errorlevel 1 (
    echo [설치] 필요한 패키지를 설치합니다...
    pip install -r requirements.txt
    echo.
)

echo [시작] http://localhost:8000 에서 서버를 실행합니다.
echo [종료] Ctrl+C 를 누르면 서버가 종료됩니다.
echo.
start http://localhost:8000
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
