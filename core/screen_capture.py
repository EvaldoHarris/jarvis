"""Capture the virtual desktop and preserve its desktop-coordinate origin."""


def capture_desktop():
    import mss
    from PIL import Image

    with mss.mss() as capture:
        area = dict(capture.monitors[0])
        shot = capture.grab(area)
        image = Image.frombytes("RGB", shot.size, shot.rgb)
    return image, area["left"], area["top"]


def point_on_desktop(x, y):
    """Exclude gaps between monitors, allowing negative desktop coordinates."""
    import mss

    with mss.mss() as capture:
        return any(m["left"] <= x < m["left"] + m["width"] and
                   m["top"] <= y < m["top"] + m["height"]
                   for m in capture.monitors[1:])
