from pathlib import Path
import re
import sys


def split_markdown(path: Path, output_dir: Path, title_map: dict[str, str], cover_text: str | None = None):
    text = path.read_text(encoding='utf-8')
    parts = re.split(r'(?m)^# ', text)

    if not parts:
        raise ValueError('No content found')

    # first part is before the first heading; skip it
    parts = parts[1:]

    for idx, part in enumerate(parts):
        if not part.strip():
            continue

        lines = part.strip().splitlines()
        if not lines:
            continue

        title_line = lines[0].strip()
        title = title_line.split('\n')[0].strip()

        body = '\n'.join(lines[1:]).strip()

        if idx == 0:
            body = body.strip()

        # remove trailing separators like ---
        body = re.sub(r'\n{3,}---\s*$', '', body, flags=re.MULTILINE)

        filename = title_map.get(title)
        if not filename:
            filename = f"{idx} - {title}.md"

        output_path = output_dir / filename
        output_text = f"# {title}\n\n{body}\n" if body else f"# {title}\n"
        output_path.write_text(output_text, encoding='utf-8')

    if cover_text is not None:
        (output_dir / 'cover.md').write_text(cover_text + '\n', encoding='utf-8')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python split_book.py <source_file> [output_dir]')
        sys.exit(1)

    source = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else source.parent

    title_map = {
        'de': {
            'Brise. Prolog': '0 - Brise. Prolog.md',
            'Der Strand. Rote und gelbe Flaggen': '1 - Der Strand. Rote und gelbe Flaggen.md',
            'Der Pier. Vorbereitung': '2 - Der Pier. Vorbereitung.md',
            'Der Absprung. Konsum und Dosierungen': '3 - Der Absprung. Konsum und Dosierungen.md',
            'Der Sprung. Das Eintauchen in die Erfahrung': '4 - Der Sprung. Das Eintauchen in die Erfahrung.md',
            'Das Ufer. Integration': '5 - Das Ufer. Integration.md',
            'Der Liegestuhl. Schlussbemerkung': '6 - Der Liegestuhl. Schlussbemerkung.md',
        },
        'uk': {
            'Бриз. Пролог': '0 - Бриз. Пролог.md',
            'Пляж. Червоні та жовті прапорці': '1 - Пляж. Червоні та жовті прапорці.md',
            'Пірс. Підготовка': '2 - Пірс. Підготовка.md',
            'Поштовх. Вживання та дозування': '3 - Поштовх. Вживання та дозування.md',
            'Стрибок. Занурення в досвід': '4 - Стрибок. Занурення в досвід.md',
            'Берег. Інтеграція': '5 - Берег. Інтеграція.md',
            'Шезлонг. Висновок': '6 - Шезлонг. Висновок.md',
        },
        'en': {
            'The Breeze. Prologue': '0 - The Breeze. Prologue.md',
            'The Beach. Red and Yellow Flags': '1 - The Beach. Red and Yellow Flags.md',
            'The Pier. Preparation': '2 - The Pier. Preparation.md',
            'The Push. Consumption and Dosages': '3 - The Push. Consumption and Dosages.md',
            'The Jump. Immersion in the Experience': '4 - The Jump. Immersion in the Experience.md',
            'The Shore. Integration': '5 - The Shore. Integration.md',
            'The Lounge. Conclusion': '6 - The Lounge. Conclusion.md',
        },
    }

    chosen_map = title_map.get(output_dir.name, title_map['en'])
    cover_text = {
        'de': """Diese Buch wird Sie durch alle Phasen einer psychedelischen Reise begleiten: von der Vorbereitung und Absichtsbildung bis hin zur Arbeit mit unerwarteten Wendungen und zur sanften Integration.""",
        'uk': """Ця книга проведе вас через усі етапи психоделічної подорожі: від підготовки й наміру до роботи з непередбаченими поворотами та м'якої інтеграції.""",
        'en': """This book will guide you through every stage of a psychedelic journey: from preparation and intention, to working with unexpected turns, to gentle integration.""",
    }.get(output_dir.name, "")

    split_markdown(source, output_dir, chosen_map, cover_text)
    print(f'Split completed: {source} -> {output_dir}')
