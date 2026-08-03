from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Settings
BOOK_DIR = PROJECT_ROOT / "book"
TARGET_LANGUAGE = "en"  # "en", "ru", "uk", "de"
BUILD_MARKDOWN = True
BUILD_PDF = True

TRANSLATIONS_FILE = Path(__file__).with_name("translations.json")
SPECIAL_FILES = {"cover.md", "license.md", "book.md", "README.md"}
CHAPTER_PATTERN = re.compile(r"^(?P<number>\d+)\s*-\s*.+\.md$")
TEMPLATE_PATTERN = re.compile(r"{{\s*(?P<key>[\w.-]+)\s*}}")
LOCAL_IMAGE_PATTERN = re.compile(r"(!\[[^\]]*\]\()(?P<bracket><)?images/")
FRONT_COVER_PATTERN = re.compile(
    r"\n:::: \{\.front-cover\}\n.*?\n::::\n",
    re.DOTALL,
)
PDF_ENGINE = "weasyprint"
REQUIRED_TRANSLATIONS = {
    "contents_title",
    "license_title",
    "license_intro",
    "license_permissions",
    "cover_artwork_title",
    "cover_artwork_credit",
    "cover_artwork_modification",
}
BOOK_TRANSLATION_KEYS = {
    "title",
    "subtitle",
    "author",
    "description",
    "language",
    "date",
}
YEAR_PATTERN = re.compile(r"(?<!\d)(?P<year>\d{4})(?!\d)")


class BuildError(RuntimeError):
    pass


def slugify(value: str) -> str:
    """Return a lowercase kebab-case name while preserving Unicode letters."""
    value = unicodedata.normalize("NFC", value).casefold()
    value = re.sub(r"[^\w]+", "-", value, flags=re.UNICODE)
    value = value.strip("-")
    return value or "book"


def artifact_name(title: str, language: str) -> str:
    return f"{slugify(title)}-{slugify(language)}"


def output_directory(book_dir: Path, title: str, language: str) -> Path:
    return book_dir / "result" / artifact_name(title, language)


def copy_cover_image(cover_image: Path, output_dir: Path) -> Path:
    output_cover = output_dir / "cover.png"
    if cover_image.resolve() != output_cover.resolve():
        shutil.copyfile(cover_image, output_cover)
    return output_cover


def front_cover_markdown(title: str) -> str:
    return f":::: {{.front-cover}}\n![{title}](cover.png)\n::::"


def run(command: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise BuildError(f"Required command is missing: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or str(error)).strip()
        raise BuildError(f"{' '.join(command)}\n{details}") from error
    return result.stdout


def inline_text(inlines: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for inline in inlines:
        kind = inline["t"]
        value = inline.get("c")
        if kind == "Str":
            parts.append(str(value))
        elif kind in {"Space", "SoftBreak", "LineBreak"}:
            parts.append(" ")
        elif kind in {"Code", "Math"}:
            parts.append(str(value[-1]))
        elif kind in {
            "Emph",
            "Strong",
            "Strikeout",
            "SmallCaps",
            "Superscript",
            "Subscript",
        }:
            parts.append(inline_text(value))
        elif kind in {"Link", "Image", "Span"}:
            parts.append(inline_text(value[1]))
        elif kind == "Quoted":
            parts.append(inline_text(value[1]))
    return "".join(parts).strip()


def metadata_value(node: dict[str, Any]) -> Any:
    kind = node["t"]
    value = node.get("c")
    if kind == "MetaString":
        return value
    if kind == "MetaBool":
        return value
    if kind == "MetaInlines":
        return inline_text(value)
    if kind == "MetaList":
        return [metadata_value(item) for item in value]
    if kind == "MetaMap":
        return {key: metadata_value(item) for key, item in value.items()}
    raise BuildError(f"Unsupported metadata value: {kind}")


def read_metadata(metadata_file: Path, book_dir: Path) -> dict[str, Any]:
    raw_json = run(
        [
            "pandoc",
            str(metadata_file),
            "--from=markdown",
            "--to=json",
        ],
        cwd=book_dir,
    )
    parsed = json.loads(raw_json)
    return {
        key: metadata_value(value)
        for key, value in parsed.get("meta", {}).items()
    }


def nested_value(metadata: dict[str, Any], key: str) -> Any:
    value: Any = metadata
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise BuildError(f"Missing metadata for template variable: {key}")
        value = value[part]
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return value


def render_template(path: Path, metadata: dict[str, Any]) -> str:
    source = path.read_text(encoding="utf-8")
    return TEMPLATE_PATTERN.sub(
        lambda match: str(nested_value(metadata, match.group("key"))),
        source,
    ).strip()


def resolve_placeholder_value(
    value: Any,
    context: dict[str, Any],
    translations: dict[str, Any],
) -> Any:
    if isinstance(value, list):
        return [
            resolve_placeholder_value(item, context, translations)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: resolve_placeholder_value(item, context, translations)
            for key, item in value.items()
        }
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        key = match.group("key")
        if key.startswith("i18n."):
            scope = translations
            parts = key.split(".")[1:]
        else:
            scope = context
            parts = key.split(".")
        current: Any = scope
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise BuildError(f"Missing metadata for template variable: {key}")
        return str(current)

    if TEMPLATE_PATTERN.search(value):
        return TEMPLATE_PATTERN.sub(replace, value)
    return value


def resolve_metadata_placeholders(
    metadata: dict[str, Any],
    translations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    translations = translations or {}
    resolved: dict[str, Any] = {}
    for key, value in metadata.items():
        resolved[key] = resolve_placeholder_value(
            value,
            {**metadata, **resolved},
            translations,
        )
    return resolved


def resolve_book_dir(base_dir: Path, _language: str) -> Path:
    base_dir = Path(base_dir).expanduser()
    if not base_dir.is_absolute():
        base_dir = (Path.cwd() / base_dir).resolve(strict=False)
    return base_dir


def resolve_content_dir(base_dir: Path, language: str) -> Path:
    content_dir = base_dir / "assets" / language
    if content_dir.is_dir():
        return content_dir
    return base_dir


def load_local_translations(
    book_dir: Path,
    language: str,
) -> dict[str, Any] | None:
    candidates = [
        book_dir / "assets" / "translations.json",
        book_dir / "translations.json",
        book_dir / "assets" / language / "translations.json",
        book_dir.parent / "translations.json",
    ]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise BuildError(
                f"Invalid local translations file: {candidate}: {error}"
            ) from error
        if not isinstance(data, dict):
            raise BuildError(
                f"Local translations must be a JSON object: {candidate}"
            )
        if language in data and isinstance(data[language], dict):
            return data[language]
    return None


def merge_local_translations(
    translations: dict[str, Any],
    local_translations: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(translations)
    local_book: dict[str, Any] = {}
    nested_book = local_translations.get("book")
    if isinstance(nested_book, dict):
        local_book.update(nested_book)
    local_book.update(
        {
            key: local_translations[key]
            for key in BOOK_TRANSLATION_KEYS
            if key in local_translations
        }
    )

    if local_book:
        invalid = sorted(
            key
            for key in BOOK_TRANSLATION_KEYS
            if not isinstance(local_book.get(key), str)
            or not local_book[key].strip()
        )
        if invalid:
            raise BuildError(
                "Missing local book translations: " + ", ".join(invalid)
            )
        merged["book"] = local_book

    merged.update(
        {
            key: value
            for key, value in local_translations.items()
            if key != "book" and key not in BOOK_TRANSLATION_KEYS
        }
    )
    return merged


def read_translations(language: str, book_dir: Path | None = None) -> dict[str, Any]:
    try:
        catalog = json.loads(TRANSLATIONS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise BuildError(
            f"Translations file does not exist: {TRANSLATIONS_FILE}"
        ) from error
    except json.JSONDecodeError as error:
        raise BuildError(
            f"Invalid translations file: {TRANSLATIONS_FILE}: {error}"
        ) from error

    if not isinstance(catalog, dict):
        raise BuildError("Translations must be grouped by language")

    translations = catalog.get(language)
    if not isinstance(translations, dict):
        supported = ", ".join(sorted(str(key) for key in catalog))
        raise BuildError(
            f"Unsupported target language '{language}'. "
            f"Available languages: {supported}"
        )

    if book_dir is not None:
        local_translations = load_local_translations(book_dir, language)
        if local_translations is None:
            raise BuildError(
                "Missing book translations for "
                f"'{language}' in {book_dir / 'assets' / 'translations.json'}"
            )
        translations = merge_local_translations(
            translations,
            local_translations,
        )

    invalid = sorted(
        key
        for key in REQUIRED_TRANSLATIONS
        if not isinstance(translations.get(key), str)
        or not translations[key].strip()
    )
    if invalid:
        raise BuildError(
            f"Missing translations for '{language}': {', '.join(invalid)}"
        )
    return translations


def copyright_year(date: str) -> str:
    years = YEAR_PATTERN.findall(date)
    if len(years) != 1:
        raise BuildError(
            f"Book date must contain exactly one four-digit year: {date!r}"
        )
    return years[0]


def apply_book_metadata(
    metadata: dict[str, Any],
    book_translation: dict[str, Any],
    language: str,
) -> dict[str, Any]:
    invalid = sorted(
        key
        for key in BOOK_TRANSLATION_KEYS
        if not isinstance(book_translation.get(key), str)
        or not book_translation[key].strip()
    )
    if invalid:
        raise BuildError(
            "Missing book translations: " + ", ".join(invalid)
        )

    localized = dict(metadata)
    for key in ("title", "subtitle", "author", "description", "date"):
        localized[key] = book_translation[key]
    localized["lang"] = language
    localized["copyright-year"] = copyright_year(book_translation["date"])
    localized["rights"] = (
        f"© {localized['copyright-year']} {book_translation['author']}"
    )
    return localized


def localized_metadata_source(metadata: dict[str, Any]) -> str:
    """Generate a complete YAML metadata block for Pandoc."""
    lines = ["---"]
    for key, val in metadata.items():
        if key == "i18n":
            continue
        lines.append(f"{key}: {json.dumps(val, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def output_image_paths(markdown: str, image_path: str = "../images") -> str:
    normalized_path = image_path.replace(os.sep, "/").rstrip("/") + "/"
    return LOCAL_IMAGE_PATTERN.sub(
        lambda match: (
            f"{match.group(1)}{match.group('bracket') or ''}{normalized_path}"
        ),
        markdown,
    )


def find_chapters(book_dir: Path) -> list[Path]:
    chapters: list[tuple[int, str, Path]] = []
    for path in book_dir.glob("*.md"):
        if path.name in SPECIAL_FILES:
            continue
        match = CHAPTER_PATTERN.fullmatch(path.name)
        if match is None:
            raise BuildError(
                f"Chapter filename must be '<number> - <title>.md': {path.name}"
            )
        chapters.append((int(match.group("number")), path.name.casefold(), path))

    if not chapters:
        raise BuildError(f"No numbered chapters found in {book_dir}")
    chapters.sort()
    return [path for _, _, path in chapters]


def make_toc(
    chapters: list[Path],
    book_dir: Path,
    depth: int,
    title: str,
) -> str:
    template_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".md",
            encoding="utf-8",
            delete=False,
        ) as template:
            template.write("$toc$\n")
            template_path = Path(template.name)

        toc = run(
            [
                "pandoc",
                *[str(chapter) for chapter in chapters],
                "--from=markdown",
                "--to=markdown",
                "--standalone",
                "--toc",
                f"--toc-depth={depth}",
                f"--template={template_path}",
                "--wrap=none",
            ],
            cwd=book_dir,
        ).strip()
    finally:
        if template_path is not None:
            template_path.unlink(missing_ok=True)

    return f"# {title} {{.toc-title .unlisted}}\n\n{toc}"


def validate_epub(
    epub_file: Path,
    cover_image: Path,
    translations: dict[str, Any],
) -> None:
    try:
        with zipfile.ZipFile(epub_file) as archive:
            broken_file = archive.testzip()
            if broken_file is not None:
                raise BuildError(f"Corrupted file in EPUB: {broken_file}")

            package = ElementTree.fromstring(archive.read("EPUB/content.opf"))
            namespace = {"opf": "http://www.idpf.org/2007/opf"}
            cover_item = next(
                (
                    item
                    for item in package.findall(
                        ".//opf:manifest/opf:item",
                        namespace,
                    )
                    if "cover-image" in item.attrib.get("properties", "").split()
                ),
                None,
            )
            if cover_item is None:
                raise BuildError("EPUB does not declare a cover image")

            cover_path = PurePosixPath("EPUB") / cover_item.attrib["href"]
            if archive.read(str(cover_path)) != cover_image.read_bytes():
                raise BuildError("Embedded EPUB cover differs from the source image")

            xhtml_namespace = {"xhtml": "http://www.w3.org/1999/xhtml"}
            expected_headings = {
                translations["license_title"],
                translations["cover_artwork_title"],
            }
            headings_share_page = False
            for name in archive.namelist():
                is_content_document = (
                    name.startswith("EPUB/text/")
                    and name.endswith(".xhtml")
                )
                if not is_content_document:
                    continue
                document = ElementTree.fromstring(archive.read(name))
                headings = {
                    "".join(heading.itertext()).strip()
                    for heading in document.findall(".//xhtml:h1", xhtml_namespace)
                }
                if expected_headings.issubset(headings):
                    headings_share_page = True
                    break
            if not headings_share_page:
                raise BuildError(
                    "License and cover artwork were split across EPUB pages"
                )
    except (KeyError, ElementTree.ParseError, zipfile.BadZipFile) as error:
        raise BuildError(f"Invalid EPUB archive: {error}") from error


def validate_sources(
    base_dir: Path,
    content_dir: Path,
) -> tuple[Path, Path, Path, Path]:
    if shutil.which("pandoc") is None:
        raise BuildError("Pandoc is not installed")

    metadata = base_dir / "metadata.yaml"
    if not metadata.is_file():
        metadata = content_dir / "metadata.yaml"
    cover = content_dir / "cover.md"
    if not cover.is_file():
        cover = base_dir / "cover.md"
    license_file = base_dir / "license.md"
    if not license_file.is_file():
        license_file = content_dir / "license.md"
    css = base_dir / "styles.css"
    if not css.is_file():
        css = content_dir / "styles.css"
    missing = [
        str(path)
        for path in (metadata, cover, license_file, css)
        if not path.is_file()
    ]
    if missing:
        raise BuildError("Missing required files:\n" + "\n".join(missing))
    return metadata, cover, license_file, css


def require_pdf_engine() -> None:
    if shutil.which(PDF_ENGINE) is None:
        raise BuildError(
            "PDF output requires WeasyPrint. Install it or set "
            "BUILD_PDF = False."
        )


def build(
    book_dir: Path,
    generate_markdown: bool,
    generate_pdf: bool,
    target_language: str,
) -> None:
    book_dir = resolve_book_dir(book_dir, target_language)
    content_dir = resolve_content_dir(book_dir, target_language)
    metadata_file, cover_file, license_file, css_file = validate_sources(
        book_dir,
        content_dir,
    )
    if generate_pdf:
        require_pdf_engine()

    metadata = read_metadata(metadata_file, book_dir)
    translations = read_translations(target_language, book_dir)
    metadata = apply_book_metadata(
        metadata,
        translations.get("book", {}),
        target_language,
    )

    required_metadata = (
        "title",
        "author",
        "lang",
        "identifier",
        "publisher",
        "subject",
        "cover-image",
        "rights",
    )
    missing_metadata = [key for key in required_metadata if not metadata.get(key)]
    if missing_metadata:
        raise BuildError(
            "Missing required metadata: " + ", ".join(missing_metadata)
        )
    metadata["i18n"] = translations
    metadata = resolve_metadata_placeholders(metadata, translations)

    cover_image_candidate = Path(str(metadata["cover-image"]))
    cover_image = None
    for base in (content_dir, book_dir):
        candidate = base / cover_image_candidate
        if candidate.is_file():
            cover_image = candidate
            break
    if cover_image is None:
        raise BuildError(f"Cover image does not exist: {cover_image_candidate}")

    chapters = find_chapters(content_dir)

    book_title = str(metadata["title"])
    output_name = artifact_name(book_title, target_language)

    output_dir = output_directory(book_dir, book_title, target_language)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_cover = copy_cover_image(cover_image, output_dir)

    metadata["cover-image"] = output_cover.name
    metadata["cover-image-alt"] = book_title

    markdown_file = output_dir / f"{output_name}.md"
    epub_file = output_dir / f"{output_name}.epub"
    pdf_file = output_dir / f"{output_name}.pdf"

    working_markdown = (
        markdown_file
        if generate_markdown
        else output_dir / f".{output_name}.md"
    )
    if not generate_markdown:
        markdown_file.unlink(missing_ok=True)

    title_marker = "# Cover {.unlisted}"
    sections = [
        localized_metadata_source(metadata),
        title_marker,
        front_cover_markdown(book_title),
        render_template(cover_file, metadata),
        make_toc(
            chapters,
            content_dir,
            int(metadata.get("toc-depth", 2)),
            translations["contents_title"],
        ),
        *[
            output_image_paths(
                chapter.read_text(encoding="utf-8").strip(),
                os.path.relpath(content_dir / "images", output_dir),
            )
            for chapter in chapters
        ],
        render_template(license_file, metadata),
    ]
    combined_markdown = "\n\n".join(sections).rstrip() + "\n"
    working_markdown.write_text(combined_markdown, encoding="utf-8")

    epub_source = output_dir / f".{output_name}.epub.md"
    epub_source.write_text(
        FRONT_COVER_PATTERN.sub("\n", combined_markdown, count=1),
        encoding="utf-8",
    )

    resource_path = os.pathsep.join(
        (str(output_dir), str(content_dir), str(book_dir))
    )
    common = [
        "pandoc",
        str(working_markdown),
        "--from=markdown",
        "--standalone",
        "--section-divs",
        "--toc=false",
        f"--metadata=lang={target_language}",
        f"--resource-path={resource_path}",
    ]

    temporary_epub = output_dir / f".{output_name}.epub.tmp"
    epub_command = common.copy()
    epub_command[1] = str(epub_source)
    epub_command.extend(
        [
            "--to=epub3",
            f"--css={css_file}",
            f"--epub-cover-image={output_cover}",
            "--epub-title-page=false",
            "--split-level=1",
            "--output",
            str(temporary_epub),
        ]
    )
    try:
        run(epub_command, cwd=content_dir)
        validate_epub(temporary_epub, output_cover, translations)
        temporary_epub.replace(epub_file)

        if generate_pdf:
            pdf_command = [
                *common,
                "--to=html5",
                f"--css={css_file}",
                f"--pdf-engine={PDF_ENGINE}",
                "--output",
                str(pdf_file),
            ]
            run(pdf_command, cwd=content_dir)
        else:
            pdf_file.unlink(missing_ok=True)
    finally:
        epub_source.unlink(missing_ok=True)
        temporary_epub.unlink(missing_ok=True)
        if not generate_markdown:
            working_markdown.unlink(missing_ok=True)

    print(f"Language:  {target_language}")
    print(f"Directory: {output_dir}")
    print(f"Markdown:  {markdown_file if generate_markdown else 'skipped'}")
    print(f"EPUB:      {epub_file}")
    print(f"PDF:       {pdf_file if generate_pdf else 'skipped'}")


def main() -> int:
    try:
        build(BOOK_DIR, BUILD_MARKDOWN, BUILD_PDF, TARGET_LANGUAGE)
    except (BuildError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
