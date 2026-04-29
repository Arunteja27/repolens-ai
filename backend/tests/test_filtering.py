from pathlib import Path

from repolens.core.config import Settings
from repolens.services.filtering import FileFilter


def test_file_filter_skips_ignored_and_binary_files(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    project_root = tmp_path / "fixture"
    (project_root / "src").mkdir(parents=True)
    (project_root / "node_modules" / "lib").mkdir(parents=True)
    (project_root / "src" / "app.ts").write_text("console.log('hello');\n", encoding="utf-8")
    (project_root / "node_modules" / "lib" / "index.js").write_text("ignored", encoding="utf-8")
    (project_root / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (project_root / "package-lock.json").write_text("x" * 80_000, encoding="utf-8")

    files = FileFilter(settings).iter_source_files(project_root)

    assert [item.file_path for item in files] == ["src/app.ts"]


def _make_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / ".data",
        temp_repo_dir=tmp_path / ".data" / "repos",
        chroma_dir=tmp_path / ".data" / "chroma",
        database_path=tmp_path / ".data" / "repolens.db",
    )
    settings.ensure_directories()
    return settings

