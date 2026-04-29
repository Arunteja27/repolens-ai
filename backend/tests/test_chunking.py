from repolens.services.chunking import SlidingWindowChunker, SymbolAwareChunker


def test_sliding_window_preserves_line_ranges() -> None:
    chunker = SlidingWindowChunker(chunk_size_lines=5, overlap_lines=2)
    text = "\n".join([f"line {index}" for index in range(1, 13)])

    chunks = chunker.chunk_text("demo.py", text, "python")

    ranges = [(chunk.start_line, chunk.end_line) for chunk in chunks]
    assert ranges == [(1, 5), (4, 8), (7, 11), (10, 12)]


def test_symbol_aware_python_chunker_preserves_symbol_lines() -> None:
    chunker = SymbolAwareChunker(chunk_size_lines=20, overlap_lines=5)
    text = """\
def alpha():
    return "a"

class Beta:
    def method(self):
        return "b"
"""

    chunks = chunker.chunk_text("demo.py", text, "python")

    alpha_chunk = next(chunk for chunk in chunks if chunk.symbol_name == "alpha")
    beta_chunk = next(chunk for chunk in chunks if chunk.symbol_name == "Beta")
    assert (alpha_chunk.start_line, alpha_chunk.end_line) == (1, 2)
    assert (beta_chunk.start_line, beta_chunk.end_line) == (4, 6)

