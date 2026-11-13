"""Local COCO person/vehicle filtering using OpenCV Zoo's pinned YOLOX model."""
import hashlib
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'models/security/yolox_s.onnx'
SHA256 = 'c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063'
URL = ('https://media.githubusercontent.com/media/opencv/opencv_zoo/'
       '48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_yolox/'
       'object_detection_yolox_2022nov.onnx')
LABELS = {0: 'pessoa', 2: 'carro', 3: 'moto', 5: 'ônibus', 7: 'caminhão'}


def person_candidate(score, runner_up, box, width, height):
    """Discard ambiguous class assignments, tiny regions and padding boxes."""
    x, y, w, h = box
    visible_w = max(0., min(width, x + w) - max(0., x))
    visible_h = max(0., min(height, y + h) - max(0., y))
    return (score >= .60 and score - runner_up >= .12 and visible_w >= 6
            and visible_h >= max(16, height * .025)
            and visible_w * visible_h >= width * height * .00025
            and visible_w * visible_h >= w * h * .5)


class PersonConfirmation:
    """Require three consecutive spatially consistent, confident observations."""
    def __init__(self, threshold=.70, max_gap=4):
        self.threshold, self.max_gap = threshold, max_gap
        self.tracks = {}

    def reset(self, camera):
        self.tracks.pop(camera, None)

    @staticmethod
    def matches(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        intersection = max(0, min(ax+aw, bx+bw)-max(ax, bx)) * max(0, min(ay+ah, by+bh)-max(ay, by))
        union = aw*ah + bw*bh - intersection
        distance = ((ax+aw/2-bx-bw/2)**2 + (ay+ah/2-by-bh/2)**2)**.5
        return (union > 0 and intersection / union >= .15) or distance <= min(.18, max(.03, max(aw, ah, bw, bh)))

    def filter(self, camera, detections, now):
        others = [d for d in detections if d['label'] != 'pessoa']
        candidates = sorted((d for d in detections if d['label'] == 'pessoa'
                             and d.get('score', 0) >= self.threshold and len(d.get('box', [])) == 4),
                            key=lambda d: d['score'], reverse=True)[:12]
        previous = [t for t in self.tracks.get(camera, []) if 0 <= now-t['time'] <= self.max_gap]
        tracks, confirmed = [], []
        for detection in candidates:
            match = next((t for t in previous if self.matches(t['box'], detection['box'])), None)
            count = match['count'] + 1 if match else 1
            if match:
                previous.remove(match)
            tracks.append(dict(box=detection['box'], count=count, time=now))
            if count >= 3:
                confirmed.append(detection)
        self.tracks[camera] = tracks
        return others + confirmed


def prepare():
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    if MODEL.exists() and hashlib.sha256(MODEL.read_bytes()).hexdigest() == SHA256:
        return MODEL
    data = urllib.request.urlopen(URL, timeout=60).read(40_000_001)
    if len(data) != 35858002 or hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError('O modelo de detecção não passou na verificação de integridade.')
    temporary = MODEL.with_suffix('.tmp')
    temporary.write_bytes(data)
    temporary.replace(MODEL)
    return MODEL


class Detector:
    def __init__(self, confidence=.55):
        import cv2
        import numpy as np
        if not MODEL.exists() or hashlib.sha256(MODEL.read_bytes()).hexdigest() != SHA256:
            raise RuntimeError('Prepare o detector local antes de iniciar o monitoramento.')
        self.cv, self.np = cv2, np
        cv2.setNumThreads(2)
        self.threshold = confidence
        self.net = cv2.dnn.readNetFromONNX(str(MODEL))
        grids, strides = [], []
        for stride in (8, 16, 32):
            x, y = np.meshgrid(np.arange(640 // stride), np.arange(640 // stride))
            grid = np.stack((x, y), 2).reshape(-1, 2)
            grids.append(grid)
            strides.append(np.full((len(grid), 1), stride))
        self.grid, self.strides = np.concatenate(grids), np.concatenate(strides)

    def detect(self, jpeg):
        cv, np = self.cv, self.np
        frame = cv.imdecode(np.frombuffer(jpeg, np.uint8), cv.IMREAD_COLOR)
        if frame is None:
            raise ValueError('Imagem inválida.')
        height, width = frame.shape[:2]
        scale = min(640 / height, 640 / width)
        resized = cv.resize(cv.cvtColor(frame, cv.COLOR_BGR2RGB),
                            (int(width * scale), int(height * scale)))
        padded = np.full((640, 640, 3), 114., np.float32)
        padded[:resized.shape[0], :resized.shape[1]] = resized
        self.net.setInput(padded.transpose(2, 0, 1)[None])
        output = self.net.forward()[0]
        scores = output[:, 4, None] * output[:, 5:]
        second_best = np.partition(scores, -2, axis=1)[:, -2]
        ids = scores.argmax(axis=1)
        confidence = scores.max(axis=1)
        keep = (confidence >= self.threshold) & np.isin(ids, list(LABELS))
        rows, ids, confidence, second_best = output[keep], ids[keep], confidence[keep], second_best[keep]
        centers = (rows[:, :2] + self.grid[keep]) * self.strides[keep]
        dimensions = np.exp(rows[:, 2:4]) * self.strides[keep]
        boxes = np.concatenate((centers - dimensions / 2, dimensions), axis=1) / scale
        result = []
        for cls in set(ids.tolist()):
            indices = np.flatnonzero(ids == cls)
            if cls == 0:
                indices = np.asarray([i for i in indices if person_candidate(
                    float(confidence[i]), float(second_best[i]), boxes[i], width, height)], dtype=int)
            if not len(indices):
                continue
            selected = cv.dnn.NMSBoxes(boxes[indices].tolist(), confidence[indices].tolist(),
                                       self.threshold, .5)
            for position in np.asarray(selected).reshape(-1):
                index = indices[int(position)]
                x, y, w, h = [float(v) for v in boxes[index]]
                left, top = max(0., min(width, x)), max(0., min(height, y))
                right, bottom = max(left, min(width, x+w)), max(top, min(height, y+h))
                result.append(dict(label=LABELS[cls], score=round(float(confidence[index]), 3),
                                   box=[left/width, top/height, (right-left)/width, (bottom-top)/height]))
        return result
