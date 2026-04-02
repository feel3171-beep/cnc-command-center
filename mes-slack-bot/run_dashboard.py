"""생산 현황 대시보드 실행"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from bots.production import run

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    run(target_date=target)
