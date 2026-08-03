from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import build_book


class BuildBookTests(unittest.TestCase):
    def test_slugify_returns_lowercase_kebab_case(self) -> None:
        self.assertEqual(
            build_book.slugify("  Example Book!  "),
            "example-book",
        )

    def test_read_translations_loads_flat_book_metadata_from_assets(self) -> None:
        shared_catalog = {
            "en": {
                key: key
                for key in build_book.REQUIRED_TRANSLATIONS
            }
        }
        local_book = {
            "title": "Localized title",
            "subtitle": "Localized subtitle",
            "author": "Localized author",
            "description": "Localized description",
            "language": "English",
            "date": "03.08.2026",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            book_dir = Path(tmpdir) / "book"
            assets_dir = book_dir / "assets"
            assets_dir.mkdir(parents=True)
            shared_file = Path(tmpdir) / "shared-translations.json"
            shared_file.write_text(json.dumps(shared_catalog), encoding="utf-8")
            (assets_dir / "translations.json").write_text(
                json.dumps({"en": local_book}),
                encoding="utf-8",
            )

            with patch.object(build_book, "TRANSLATIONS_FILE", shared_file):
                translations = build_book.read_translations("en", book_dir)

        self.assertEqual(translations["book"], local_book)
        self.assertNotIn("file_name", translations["book"])

    def test_read_translations_requires_book_assets_catalog(self) -> None:
        shared_catalog = {
            "en": {
                key: key
                for key in build_book.REQUIRED_TRANSLATIONS
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            book_dir = root / "book"
            book_dir.mkdir()
            shared_file = root / "shared-translations.json"
            shared_file.write_text(json.dumps(shared_catalog), encoding="utf-8")

            with (
                patch.object(build_book, "TRANSLATIONS_FILE", shared_file),
                self.assertRaisesRegex(
                    build_book.BuildError,
                    "Missing book translations",
                ),
            ):
                build_book.read_translations("en", book_dir)

    def test_read_subjects_supports_commas_lines_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            book_dir = Path(tmpdir) / "book"
            assets_dir = book_dir / "assets"
            assets_dir.mkdir(parents=True)
            (assets_dir / "tags.txt").write_text(
                "Science, Health & Wellness\nscience\nSelf-Help,  ",
                encoding="utf-8",
            )

            subjects = build_book.read_subjects(book_dir)

        self.assertEqual(
            subjects,
            ["Science", "Health & Wellness", "Self-Help"],
        )

    def test_read_subjects_rejects_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            book_dir = Path(tmpdir) / "book"
            (book_dir / "assets").mkdir(parents=True)

            with self.assertRaisesRegex(
                build_book.BuildError,
                "tags.txt",
            ):
                build_book.read_subjects(book_dir)

    def test_read_subjects_rejects_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            book_dir = Path(tmpdir) / "book"
            assets_dir = book_dir / "assets"
            assets_dir.mkdir(parents=True)
            (assets_dir / "tags.txt").write_text(" , \n", encoding="utf-8")

            with self.assertRaisesRegex(build_book.BuildError, "is empty"):
                build_book.read_subjects(book_dir)

    def test_normalize_target_languages_requires_non_empty_array(self) -> None:
        with self.assertRaisesRegex(build_book.BuildError, "non-empty array"):
            build_book.normalize_target_languages([])

        with self.assertRaisesRegex(build_book.BuildError, "not a string"):
            build_book.normalize_target_languages("en")

    def test_normalize_target_languages_normalizes_and_rejects_duplicates(
        self,
    ) -> None:
        self.assertEqual(
            build_book.normalize_target_languages([" en ", "DE"]),
            ["en", "de"],
        )

        with self.assertRaisesRegex(build_book.BuildError, "Duplicate"):
            build_book.normalize_target_languages(["en", "EN"])

    def test_build_builds_every_target_language(self) -> None:
        with patch.object(build_book, "build_language") as build_language:
            build_book.build(Path("book"), True, False, ["en", "de"])

        self.assertEqual(
            build_language.call_args_list,
            [
                call(Path("book"), True, False, "en"),
                call(Path("book"), True, False, "de"),
            ],
        )

    def test_apply_book_metadata_localizes_yaml_fields_and_derives_year(self) -> None:
        metadata = {
            "title": "Template title",
            "rights": "stale rights",
            "cover-image": "images/cover.png",
        }
        book_translation = {
            "title": "Example Book",
            "subtitle": "Example Subtitle",
            "author": "Example Author",
            "description": "Example description.",
            "language": "English",
            "date": "2026-08-03",
        }

        localized = build_book.apply_book_metadata(
            metadata,
            book_translation,
            "en",
        )

        self.assertEqual(localized["title"], "Example Book")
        self.assertEqual(localized["subtitle"], "Example Subtitle")
        self.assertEqual(localized["author"], "Example Author")
        self.assertEqual(localized["description"], "Example description.")
        self.assertEqual(localized["lang"], "en")
        self.assertEqual(localized["date"], "2026-08-03")
        self.assertEqual(localized["copyright-year"], "2026")
        self.assertEqual(localized["rights"], "© 2026 Example Author")

    def test_apply_book_metadata_rejects_date_without_year(self) -> None:
        translation = {
            "title": "Title",
            "subtitle": "Subtitle",
            "author": "Author",
            "description": "Description",
            "language": "English",
            "date": "August third",
        }

        with self.assertRaisesRegex(build_book.BuildError, "four-digit year"):
            build_book.apply_book_metadata({}, translation, "en")

    def test_artifact_name_appends_language_to_title_slug(self) -> None:
        self.assertEqual(
            build_book.artifact_name("Example Book", "EN"),
            "example-book-en",
        )

    def test_output_directory_has_same_name_as_artifacts(self) -> None:
        directory = build_book.output_directory(
            Path("book"),
            "Example Book",
            "en",
        )

        self.assertEqual(
            directory,
            Path("book/result/example-book-en"),
        )

    def test_copy_cover_image_uses_fixed_name_inside_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source.jpg"
            output_dir = root / "result" / "book-en"
            output_dir.mkdir(parents=True)
            source.write_bytes(b"cover contents")

            output_cover = build_book.copy_cover_image(source, output_dir)

            self.assertEqual(output_cover, output_dir / "cover.png")
            self.assertEqual(output_cover.read_bytes(), b"cover contents")

    def test_front_cover_uses_title_as_alt_text(self) -> None:
        self.assertEqual(
            build_book.front_cover_markdown("Example Book"),
            ":::: {.front-cover}\n"
            "![Example Book](cover.png)\n"
            "::::",
        )

    def test_localized_metadata_source_preserves_nested_metadata(self) -> None:
        source = build_book.localized_metadata_source(
            {
                "title": "Example Book",
                "identifier": [{"scheme": "URN", "text": "urn:uuid:test"}],
                "subject": ["One", "Two"],
                "i18n": {"contents_title": "Contents"},
            }
        )

        self.assertIn('title: "Example Book"', source)
        self.assertIn(
            'identifier: [{"scheme": "URN", "text": "urn:uuid:test"}]',
            source,
        )
        self.assertIn('subject: ["One", "Two"]', source)
        self.assertNotIn("i18n:", source)


if __name__ == "__main__":
    unittest.main()
