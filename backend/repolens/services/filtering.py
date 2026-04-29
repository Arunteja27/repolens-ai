from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from repolens.core.config import Settings


IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}

IGNORED_EXTENSIONS = {
    ".7z",
    ".avif",
    ".bmp",
    ".class",
    ".dll",
    ".dylib",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lockb",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".so",
    ".svg",
    ".tar",
    ".wasm",
    ".webp",
    ".zip",
}

LOCKFILE_NAMES = {
    "Cargo.lock",
    "Gemfile.lock",
    "composer.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "yarn.lock",
}

LANGUAGE_MAP = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".java": "java",
    ".rb": "ruby",
    ".go": "go",
    ".cpp": "cpp",
    ".h": "cpp",
    ".md": "markdown",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
}


@dataclass(slots=True)
class SourceFile:
    absolute_path: Path
    file_path: str
    language: str


class FileFilter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def iter_source_files(self, root: Path) -> list[SourceFile]:
        files: list[SourceFile] = []
        for current_root, dirs, filenames in os.walk(root):
            dirs[:] = [
                directory
                for directory in dirs
                if directory not in IGNORED_DIRECTORIES and not directory.startswith(".cache")
            ]
            for filename in filenames:
                absolute_path = Path(current_root) / filename
                if not self.should_include(absolute_path):
                    continue
                relative_path = absolute_path.relative_to(root).as_posix()
                files.append(
                    SourceFile(
                        absolute_path=absolute_path,
                        file_path=relative_path,
                        language=language_for_path(absolute_path),
                    )
                )
        files.sort(key=lambda item: item.file_path)
        return files

    def should_include(self, path: Path) -> bool:
        if path.suffix.lower() in IGNORED_EXTENSIONS:
            return False
        if path.suffix.lower() not in self.settings.supported_extensions:
            return False
        size = path.stat().st_size
        if path.name in LOCKFILE_NAMES and size > self.settings.max_lockfile_size_bytes:
            return False
        if size > self.settings.max_file_size_bytes:
            return False
        return not self.is_binary(path)

    @staticmethod
    def is_binary(path: Path) -> bool:
        sample = path.read_bytes()[:1024]
        if b"\x00" in sample:
            return True
        if not sample:
            return False
        text_characters = sum(1 for byte in sample if 9 <= byte <= 13 or 32 <= byte <= 126)
        return (text_characters / len(sample)) < 0.75


def language_for_path(path: Path) -> str:
    return LANGUAGE_MAP.get(path.suffix.lower(), "text")

