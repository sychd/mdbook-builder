# Markdown Book Builder

The builder always generates an EPUB file. Markdown and PDF output can be
enabled using the settings at the top of `scripts/build_book.py`:

```python
BOOK_DIR = PROJECT_ROOT / "book"
BUILD_MARKDOWN = True
BUILD_PDF = False
```

To use a different directory, set `BOOK_DIR`, for example:
`BOOK_DIR = Path("/path/to/book")`.

## Requirements

- Python 3.11+
- Pandoc 3.x
- WeasyPrint — PDF only (`brew install weasyprint`)

## Usage

```bash
python3 scripts/build_book.py
```

Name chapter files `<number> - <title>.md` and start each one with
`# Chapter Title`. The `cover.md` and `license.md` templates support
placeholders such as `{{ title }}`.

Book-specific translations live in `book/assets/translations.json`, grouped
by language. Each language must define `title`, `subtitle`, `author`,
`description`, `language`, and `date`. The builder maps the selected language
code to Pandoc's `lang`, derives `copyright-year` from `date`, and overlays
these fields onto `book/metadata.yaml` before conversion. Shared interface
translations remain in `scripts/translations.json`.

Output is written to
`book/result/<kebab-case-title>-<language>/`. The Markdown, EPUB, and PDF use
the same `<kebab-case-title>-<language>` basename. The directory also contains
`cover.png`; generated metadata references this file and uses the localized
book title as its image alt text.

## Metadata

- `identifier` — a persistent internal UUID for the edition, not an ISBN.
  Create a new UUID for a new book or edition; keep the existing UUID for
  minor corrections.
- `publisher` — the author's name or a self-publishing imprint.
- `subject` — the book's topics or genres; replace the placeholders with
  one to three values.

Generate a new UUID without additional dependencies:

```bash
python3 -c 'import uuid; print(f"urn:uuid:{uuid.uuid4()}")'
```

KDP does not require an ISBN for an eBook. For a print edition, use the ISBN
and imprint assigned by KDP or registered through an ISBN agency.

## Before publishing

1. Fill in `book/assets/translations.json` and replace the remaining metadata
   placeholders.
2. Build the book: `python3 scripts/build_book.py`.
3. Validate the EPUB with the official
   [EPUBCheck](https://github.com/w3c/epubcheck/releases):

```bash
epubcheck book/result/example-book-en/example-book-en.epub
```
