"""Event-loop-owned queue for non-interrupting background announcements."""
import heapq
import itertools

MESSAGE = 0
BACKGROUND = 10


class SpeechAnnouncements:
    def __init__(self):
        self._pending = []
        self._sequence = itertools.count()
        self.inflight = False

    def enqueue(self, instruction, priority=BACKGROUND):
        heapq.heappush(self._pending, (priority, next(self._sequence), instruction))

    def turn_finished(self):
        self.inflight = False

    async def dispatch(self, ready, send):
        # Reserve before awaiting network I/O: a second producer cannot send
        # another turn during the gap before the first audio packet arrives.
        if self.inflight or not self._pending or not ready():
            return False
        item = heapq.heappop(self._pending)
        self.inflight = True
        try:
            await send(item[2])
        except BaseException:
            self.inflight = False
            heapq.heappush(self._pending, item)
            raise
        return True
