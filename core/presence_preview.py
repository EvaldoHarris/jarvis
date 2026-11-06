"""Short, transient webcam preview sent only to the selected paired Android."""
import asyncio
import threading
import time


async def preview(bridge, device, alert_id, stopped, duration=20):
    from core import camera_frames
    from actions.screen_processor import cv2, _get_camera_index, _cv2_backend
    loop = asyncio.get_running_loop()
    frames = asyncio.Queue(maxsize=1)
    deadline = time.monotonic() + duration

    def offer(image):
        if stopped.is_set():
            return
        if frames.full():
            frames.get_nowait()
        frames.put_nowait(image)

    def capture():
        cap = None
        try:
            while not stopped.is_set() and time.monotonic() < deadline:
                # Reuse the UI's live camera when available. If we own a handle,
                # keep reading real frames and publish them for face recognition;
                # never refresh the timestamp of a cached frame repeatedly.
                image = camera_frames.latest() if cap is None else None
                if image is None:
                    if cap is None:
                        cap = cv2.VideoCapture(_get_camera_index(), _cv2_backend())
                        if not cap.isOpened():
                            break
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        break
                    height, width = frame.shape[:2]
                    if width > 960:
                        frame = cv2.resize(frame, (960, max(1, int(height * 960 / width))))
                    ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    if not ok:
                        continue
                    image = encoded.tobytes()
                    camera_frames.publish(image)
                loop.call_soon_threadsafe(offer, image)
                stopped.wait(.5)
        except Exception:
            pass
        finally:
            if cap is not None:
                cap.release()

    worker = threading.Thread(target=capture, daemon=True, name='presence-webcam-preview')
    worker.start()
    try:
        while not stopped.is_set() and time.monotonic() < deadline:
            try:
                image = await asyncio.wait_for(frames.get(), timeout=1)
            except asyncio.TimeoutError:
                if not worker.is_alive():
                    break
                continue
            if not await bridge.deliver_presence_frame(device, alert_id, image):
                break
    except Exception:
        pass
    finally:
        stopped.set()
        await bridge.deliver_presence_frame(device, alert_id, b'', final=True)
