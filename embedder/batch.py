from os.path import join as pjoin, splitext, isdir
from argparse import ArgumentParser
try:
    from embedder import read_woff_properties, generate_css
except ImportError:
    from .embedder import read_woff_properties, generate_css
from os import walk, mkdir


def generate_batch(directory: str, loud=True):
    for dirname in ('combined', 'single'):
        if not isdir(dirname):
            mkdir(dirname)
    families = {}

    for path, dirs, files in walk(directory):
        for file in files:
            if splitext(file)[-1] != '.woff':
                continue
            filepath = pjoin(path, file)
            try:
                woff_props = read_woff_properties(filepath)
                full_name = woff_props['name']['Full']
                dest_path = pjoin('single', f'{full_name}.css')

                css = generate_css(filepath)
                font_family = css.split('\n')[1][14:-1]
                if font_family in families:
                    families[font_family].append(css)
                else:
                    families[font_family] = [css]

                with open(dest_path, 'w', encoding='utf-8') as css_file:
                    css_file.write(css)

            except Exception as error:
                if loud:
                    print(f'Error with {file}: {error}')
                continue
            if loud:
                print(f'Done: {file}')

    for family in families:
        dest_path = pjoin('combined', f'{family}.css')
        with open(dest_path, 'w', encoding='utf-8') as file:
            file.write('\n'.join(families[family]))
        if loud:
            print('Wrote family', family)


if __name__ == '__main__':
    parser = ArgumentParser(description="Embed fonts in CSS files (batch)")

    parser.add_argument('source', nargs=1, type=str, help='Path to directory of .woff files')
    args = parser.parse_args()
    generate_batch(args.source[0])
