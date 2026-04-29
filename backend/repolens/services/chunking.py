from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

try:
    from tree_sitter_languages import get_parser
except ImportError:  # pragma: no cover - optional dependency
    get_parser = None


TREE_SITTER_LANGUAGE_MAP = {
    "javascript": "javascript",
    "typescript": "typescript",
    "tsx": "tsx",
    "java": "java",
    "ruby": "ruby",
    "go": "go",
    "cpp": "cpp",
}

TREE_SITTER_SYMBOL_TYPES = {
    "javascript": {"class_declaration", "function_declaration", "method_definition"},
    "typescript": {"class_declaration", "function_declaration", "method_definition"},
    "tsx": {"class_declaration", "function_declaration", "method_definition"},
    "java": {"class_declaration", "interface_declaration", "method_declaration"},
    "ruby": {"class", "method"},
    "go": {"function_declaration", "method_declaration", "type_declaration"},
    "cpp": {"function_definition", "class_specifier", "struct_specifier"},
}


@dataclass(slots=True)
class ChunkDraft:
    file_path: str
    language: str
    start_line: int
    end_line: int
    chunk_text: str
    symbol_name: str | None = None
    symbol_type: str | None = None


class SlidingWindowChunker:
    def __init__(self, chunk_size_lines: int = 80, overlap_lines: int = 20) -> None:
        self.chunk_size_lines = chunk_size_lines
        self.overlap_lines = overlap_lines

    def chunk_text(
        self,
        file_path: str,
        text: str,
        language: str,
        symbol_name: str | None = None,
        symbol_type: str | None = None,
    ) -> list[ChunkDraft]:
        lines = text.splitlines()
        return self.chunk_lines(
            file_path=file_path,
            lines=lines,
            language=language,
            start_line=1,
            symbol_name=symbol_name,
            symbol_type=symbol_type,
        )

    def chunk_lines(
        self,
        file_path: str,
        lines: list[str],
        language: str,
        start_line: int,
        symbol_name: str | None = None,
        symbol_type: str | None = None,
    ) -> list[ChunkDraft]:
        if not lines:
            return []
        step = max(1, self.chunk_size_lines - self.overlap_lines)
        chunks: list[ChunkDraft] = []
        cursor = 0
        while cursor < len(lines):
            end = min(len(lines), cursor + self.chunk_size_lines)
            chunk_lines = lines[cursor:end]
            chunks.append(
                ChunkDraft(
                    file_path=file_path,
                    language=language,
                    start_line=start_line + cursor,
                    end_line=start_line + end - 1,
                    chunk_text="\n".join(chunk_lines).strip(),
                    symbol_name=symbol_name,
                    symbol_type=symbol_type,
                )
            )
            if end >= len(lines):
                break
            cursor += step
        return [chunk for chunk in chunks if chunk.chunk_text]


class SymbolAwareChunker:
    def __init__(self, chunk_size_lines: int = 80, overlap_lines: int = 20) -> None:
        self.sliding = SlidingWindowChunker(
            chunk_size_lines=chunk_size_lines,
            overlap_lines=overlap_lines,
        )

    def chunk_text(self, file_path: str, text: str, language: str) -> list[ChunkDraft]:
        if language == "python":
            python_chunks = self._chunk_python_symbols(file_path, text)
            if python_chunks:
                return python_chunks
        if get_parser is not None and language in TREE_SITTER_LANGUAGE_MAP:
            tree_sitter_chunks = self._chunk_tree_sitter(file_path, text, language)
            if tree_sitter_chunks:
                return tree_sitter_chunks
        return self.sliding.chunk_text(file_path=file_path, text=text, language=language)

    def _chunk_python_symbols(self, file_path: str, text: str) -> list[ChunkDraft]:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return self.sliding.chunk_text(file_path=file_path, text=text, language="python")

        lines = text.splitlines()
        symbols: list[tuple[int, int, str | None, str | None]] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            end_line = node.end_lineno
            if end_line is None:
                continue
            symbol_type = "class" if isinstance(node, ast.ClassDef) else "function"
            symbols.append((node.lineno, end_line, node.name, symbol_type))

        symbols.sort(key=lambda item: (item[0], item[1]))
        return self._chunk_symbol_regions(
            file_path=file_path,
            lines=lines,
            language="python",
            symbols=symbols,
        )

    def _chunk_tree_sitter(self, file_path: str, text: str, language: str) -> list[ChunkDraft]:
        parser = get_parser(TREE_SITTER_LANGUAGE_MAP[language])
        tree = parser.parse(text.encode("utf-8"))
        target_types = TREE_SITTER_SYMBOL_TYPES[language]
        symbols: list[tuple[int, int, str | None, str | None]] = []
        stack = [tree.root_node]
        source = text.encode("utf-8")
        while stack:
            node = stack.pop()
            stack.extend(reversed(node.children))
            if node.type not in target_types:
                continue
            name_node = node.child_by_field_name("name")
            symbol_name = None
            if name_node is not None:
                symbol_name = source[name_node.start_byte : name_node.end_byte].decode(
                    "utf-8", errors="ignore"
                )
            symbols.append(
                (
                    node.start_point[0] + 1,
                    node.end_point[0] + 1,
                    symbol_name,
                    node.type,
                )
            )
        lines = text.splitlines()
        return self._chunk_symbol_regions(
            file_path=file_path,
            lines=lines,
            language=language,
            symbols=sorted(symbols, key=lambda item: (item[0], item[1])),
        )

    def _chunk_symbol_regions(
        self,
        file_path: str,
        lines: list[str],
        language: str,
        symbols: list[tuple[int, int, str | None, str | None]],
    ) -> list[ChunkDraft]:
        chunks: list[ChunkDraft] = []
        covered_lines: set[int] = set()
        for start_line, end_line, symbol_name, symbol_type in symbols:
            region = lines[start_line - 1 : end_line]
            chunks.extend(
                self.sliding.chunk_lines(
                    file_path=file_path,
                    lines=region,
                    language=language,
                    start_line=start_line,
                    symbol_name=symbol_name,
                    symbol_type=symbol_type,
                )
            )
            covered_lines.update(range(start_line, end_line + 1))

        cursor = 1
        while cursor <= len(lines):
            if cursor in covered_lines:
                cursor += 1
                continue
            start = cursor
            while cursor <= len(lines) and cursor not in covered_lines:
                cursor += 1
            end = cursor - 1
            region = lines[start - 1 : end]
            chunks.extend(
                self.sliding.chunk_lines(
                    file_path=file_path,
                    lines=region,
                    language=language,
                    start_line=start,
                    symbol_type="context",
                )
            )
        deduped: dict[tuple[int, int, str], ChunkDraft] = {}
        for chunk in chunks:
            deduped[(chunk.start_line, chunk.end_line, chunk.chunk_text)] = chunk
        return list(deduped.values())


def infer_language(file_path: str) -> str:
    return Path(file_path).suffix.lstrip(".")
