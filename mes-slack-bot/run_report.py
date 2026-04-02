"""주간/월간 분석 리포트 실행"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from bots.report import run

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    run(target_date=target)
