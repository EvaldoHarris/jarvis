import asyncio
import unittest

from core.audio_playback import collect_audio, PlaybackClock, offer_latest_audio


class AudioPlaybackTests(unittest.IsolatedAsyncioTestCase):
    async def test_microphone_can_release_without_server_turn_complete(self):
        clock = PlaybackClock()
        clock.written(9600, started=10., latency=.2)
        self.assertFalse(clock.drained(10.3))
        self.assertTrue(clock.drained(10.6))

    async def test_buffered_audio_is_not_released_early(self):
        clock = PlaybackClock()
        clock.written(48000, started=10., latency=.2)
        clock.written(48000, started=10.1, latency=.2)
        self.assertFalse(clock.drained(11.5))
        self.assertTrue(clock.drained(12.4))

    async def test_full_microphone_queue_keeps_newest_audio(self):
        queue = asyncio.Queue(maxsize=2)
        queue.put_nowait(b"old")
        queue.put_nowait(b"recent")
        offer_latest_audio(queue, b"new")
        self.assertEqual(queue.get_nowait(), b"recent")
        self.assertEqual(queue.get_nowait(), b"new")

    async def test_startup_absorbs_delayed_chunks_without_losing_bytes(self):
        queue = asyncio.Queue()

        async def feed():
            await asyncio.sleep(0.005)
            queue.put_nowait(b"b" * 2400)
            await asyncio.sleep(0.005)
            queue.put_nowait(b"c" * 2400)

        feeder = asyncio.create_task(feed())
        batch = await collect_audio(queue, b"a" * 2400, prebuffer=True)
        await feeder
        self.assertEqual(batch, b"a" * 2400 + b"b" * 2400 + b"c" * 2400)

    async def test_completed_short_answer_is_not_dropped_or_padded(self):
        done = asyncio.Event()
        done.set()
        result = await collect_audio(asyncio.Queue(), b"short", prebuffer=True, turn_done=done)
        self.assertEqual(result, b"short")

    async def test_stalled_network_releases_available_audio(self):
        result = await asyncio.wait_for(
            collect_audio(asyncio.Queue(), b"audio", prebuffer=True), timeout=0.5)
        self.assertEqual(result, b"audio")

    async def test_batch_limit_preserves_remaining_queue_for_next_write(self):
        queue = asyncio.Queue()
        for _ in range(5):
            queue.put_nowait(b"x" * 2400)
        batch = await collect_audio(queue, b"a" * 2400)
        self.assertEqual(len(batch), 9600)
        remainder = queue.get_nowait() + queue.get_nowait()
        self.assertEqual(batch + remainder, b"a" * 2400 + b"x" * 12000)


if __name__ == "__main__":
    unittest.main()
