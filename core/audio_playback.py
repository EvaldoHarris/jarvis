"""Small, bounded startup buffer for streaming mono PCM16 at 24 kHz."""
import asyncio


async def collect_audio(queue, first, *, prebuffer=False, turn_done=None):
    """Preserve every queued byte; wait at most 80 ms to smooth startup jitter."""
    batch = bytearray(first)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 0.08
    while len(batch) < 9600:  # about 200 ms
        try:
            batch.extend(queue.get_nowait())
            continue
        except asyncio.QueueEmpty:
            pass
        if not prebuffer or len(batch) >= 5760 or (turn_done and turn_done.is_set()):
            break
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        try:
            batch.extend(await asyncio.wait_for(queue.get(), timeout=remaining))
        except asyncio.TimeoutError:
            break
    return batch
