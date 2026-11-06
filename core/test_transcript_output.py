import unittest

from providers.engine_pipeline import _ReasoningFilter


class TranscriptOutputTests(unittest.TestCase):
    def visible(self, chunks):
        cleaner = _ReasoningFilter()
        return "".join(cleaner.feed(chunk) for chunk in chunks) + cleaner.flush()

    def test_private_channels_are_hidden_at_every_stream_boundary(self):
        source = "thought\nINTERNAL ONE\ntext\nFechando. thought\nINTERNAL TWO\ntext\nFechado."
        for split in range(len(source) + 1):
            with self.subTest(split=split):
                self.assertEqual(self.visible([source[:split], source[split:]]), "Fechando. Fechado.")
        self.assertEqual(self.visible(source), "Fechando. Fechado.")

    def test_control_markers_and_unterminated_thought_do_not_leak(self):
        source = "<ctrl12>thought\nINTERNAL\n<ctrl13>text\nPronto."
        self.assertEqual(self.visible(source), "Pronto.")
        self.assertEqual(self.visible(["thought\nINTERNAL"]), "")

    def test_regular_text_and_existing_reasoning_tags(self):
        self.assertEqual(self.visible(["Fechando o navegador."]), "Fechando o navegador.")
        self.assertEqual(self.visible("<think>INTERNAL</think>Feito."), "Feito.")


if __name__ == "__main__":
    unittest.main()
