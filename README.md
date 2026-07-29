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
`# Chapter Title`. Edit the metadata in `book/metadata.yaml`. The `cover.md`
and `license.md` templates support placeholders such as `{{ title }}`.

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

1. Replace the placeholders and set the final publication date.
2. Build the book: `python3 scripts/build_book.py`.
3. Validate the EPUB with the official
   [EPUBCheck](https://github.com/w3c/epubcheck/releases):

```bash
epubcheck book/result/book.epub
```
