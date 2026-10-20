import unittest
from types import SimpleNamespace as Event

import numpy as np
from core.turn_watchdog import has_answer_progress, MicrophoneTurn


class TurnWatchdogTests(unittest.TestCase):
    def test_local_speech_arms_recovery_even_without_server_transcription(self):
        turn = MicrophoneTurn()
        pcm = np.full(1024, 1000, dtype=np.int16).tobytes()
        for n in range(5):
            turn.observe(pcm, 10 + n * .064)
        self.assertIsNone(turn.ended(10.5))
        self.assertEqual(turn.ended(11.1), 10)
        self.assertIsNone(turn.ended(12))

    def test_silence_and_single_click_do_not_start_response_watchdog(self):
        turn = MicrophoneTurn()
        turn.observe(bytes(2048), 10)
        self.assertIsNone(turn.ended(12))
        turn.observe(np.full(1024, 1000, dtype=np.int16).tobytes(), 13)
        self.assertIsNone(turn.ended(15))

    def test_user_transcription_is_not_an_answer(self):
        self.assertFalse(has_answer_progress(Event(server_content=Event(
            input_transcription=Event(text="Qual é a hora?")))))

    def test_connection_updates_do_not_clear_wait(self):
        self.assertFalse(has_answer_progress(Event(session_resumption_update=Event(new_handle="handle"))))
        self.assertFalse(has_answer_progress(Event(server_content=Event(turn_complete=True))))

    def test_audio_text_and_tools_count_as_progress(self):
        self.assertTrue(has_answer_progress(Event(data=b"audio")))
        self.assertTrue(has_answer_progress(Event(tool_call=Event(function_calls=["test"]))))
        self.assertTrue(has_answer_progress(Event(server_content=Event(
            output_transcription=Event(text="São duas horas.")))))
        self.assertTrue(has_answer_progress(Event(server_content=Event(
            model_turn=Event(parts=[Event(text="Resposta")])))))


if __name__ == "__main__":
    unittest.main()
