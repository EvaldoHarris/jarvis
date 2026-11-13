"""Fetch the pinned OpenCV Zoo model; no camera credentials or images are sent."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.security_detection import prepare

if __name__ == '__main__':
    path = prepare()
    print('Detector local verificado:', path.name)
