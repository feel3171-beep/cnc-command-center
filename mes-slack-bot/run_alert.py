"""이상 알람 실행"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from bots.alert import run

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    run(target_date=target)
