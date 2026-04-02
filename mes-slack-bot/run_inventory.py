"""재고/자재 알람 실행"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from bots.inventory import run

if __name__ == "__main__":
    run()
