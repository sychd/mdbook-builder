import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_book import resolve_book_dir, resolve_metadata_placeholders


class BuildBookTests(unittest.TestCase):
    def test_resolve_metadata_placeholders_uses_translation_values(self) -> None:
        metadata = {
            "title": "{{ i18n.book.title }}",
            "subtitle": "{{ i18n.book.subtitle }}",
            "i18n": {
                "book": {
                    "title": "Book Title",
                    "subtitle": "Book Subtitle",
                }
            },
        }

        resolved = resolve_metadata_placeholders(metadata, metadata.get("i18n", {}))

        self.assertEqual(resolved["title"], "Book Title")
        self.assertEqual(resolved["subtitle"], "Book Subtitle")

    def test_resolve_book_dir_prefers_language_assets_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            configured_root = root / "book"
            language_dir = configured_root / "assets" / "ru"
            language_dir.mkdir(parents=True)
            (language_dir / "metadata.yaml").write_text(
                "title: Test\n",
                encoding="utf-8",
            )

            resolved = resolve_book_dir(configured_root, "ru")

            self.assertEqual(resolved, language_dir)


if __name__ == "__main__":
    unittest.main()
