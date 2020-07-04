from argparse import ArgumentParser
from typing import Tuple, Dict, Union, List
from struct import unpack
from os.path import split
from zlib import decompress
from io import BytesIO
from base64 import encodebytes


class FileFormatError(Exception):
    pass


def read_woff_properties(filepath: str) -> Dict[str, Dict[str, Union[str, int]]]:
    # the specifications for the WOFF format are here:
    # https://www.w3.org/TR/WOFF/
    # naming conventions are adopted from this document,
    # despite not being particularly pythonic

    with open(filepath, 'rb') as file:
        filename = split(filepath)[-1]
        header_dict = {
            "signature": unpack('>I', file.read(4))[0],
            "flavor": unpack('>I', file.read(4))[0],
            "length": unpack('>I', file.read(4))[0],
            "numTables": unpack('>H', file.read(2))[0],
            "reserved": unpack('>H', file.read(2))[0],
            "totalSfntSize": unpack('>I', file.read(4))[0],
            "majorVersion": unpack('>H', file.read(2))[0],
            "minorVersion": unpack('>H', file.read(2))[0],
            "metaOffset": unpack('>I', file.read(4))[0],
            "metaLength": unpack('>I', file.read(4))[0],
            "metaOrigLength": unpack('>I', file.read(4))[0],
            "privOffset": unpack('>I', file.read(4))[0],
            "privLength": unpack('>I', file.read(4))[0]
        }

        # there's a whole lot of stuff that can be done
        # to ensure that the WOFF is valid, but if it passes
        # all three of these checks, it's probably good enough
        # (unless it starts throwing other errors)
        if header_dict['signature'] != 2001684038:
            raise FileFormatError(f'File {filename} does not seem to be a valid WOFF file (signature: {header_dict["signature"]})')
        if header_dict['majorVersion'] != 1:
            raise FileFormatError(f'File {filename} is a WOFF version {header_dict["majorVersion"]}, which is not supported')
        if header_dict['totalSfntSize'] % 4 != 0:
            raise FileFormatError(f'File {filename} has an invalid size, indicating that it is not a valid WOFF file')

        # this bit finds tables with useful information and turns them into bytes strings
        # sometimes they need to be decompressed, luckily zlib is in the standard library
        table_headers = {k: None for k in ['name', 'os/2']}
        tables = {}
        for table_index in range(header_dict['numTables']):
            table_data = {
                "tag": file.read(4).decode('ascii'),
                "offset": unpack('>I', file.read(4))[0],
                "compLength": unpack('>I', file.read(4))[0],
                "origLength": unpack('>I', file.read(4))[0],
                "origChecksum": unpack('>I', file.read(4))[0]
            }
            tag = table_data['tag'].lower()
            if tag in table_headers:
                table_headers[tag] = table_data
        for table_name in table_headers:
            if table_headers[table_name] is None:
                raise FileFormatError(f'File {filename} does not seem to have an internal {table_name} table')
            is_compressed = table_headers[table_name]['compLength'] != table_headers[table_name]['origLength']
            file.seek(table_headers[table_name]['offset'])
            table_data = file.read(table_headers[table_name]['compLength'])
            if is_compressed:
                table_data = decompress(table_data)
                # the specification allows for leading null bytes, in order to make the file match 4-byte-block format
                # but, this can be too much: you can end up stripping important null bytes later on
                # there used to be some code that stripped leading null bytes, but it turns out that that's a terrible
                # idea and it causes many problems
            # need to parse the data before it can be used
            if table_name == 'os/2':
                tables[table_name] = parse_os2_table(table_data)
            elif table_name == 'name':
                tables[table_name] = parse_name_table(table_data)
            else:
                tables[table_name] = table_data

    return tables


def parse_name_table(data: bytes) -> Dict[str, Union[str, int]]:
    buffer = BytesIO(data)

    format_selector = unpack('>H', buffer.read(2))[0]

    if format_selector not in [0, 1]:
        raise FileFormatError(f'A name table of format {format_selector} was found, which is invalid')

    naming_table = {
        "format": format_selector,
        "count": unpack('>H', buffer.read(2))[0],
        "stringOffset": unpack('>H', buffer.read(2))[0]
    }
    name_ids = {
        0: "Copyright",
        1: "Family",
        2: "Subfamily",
        3: "Identifier",
        4: "Full",
        5: "Version",
        6: "PostScript",
        7: "Trademark",
        8: "Manufacturer",
        9: "Designer",
        10: "Description",
        11: "URL",
        12: "URL",
        13: "License",
        14: "License",
        15: "Reserved",
        16: "Typographic",
        17: "Typographic",
        18: "Compatible",
        19: "Sample",
        20: "PostScript",
        21: "WWS",
        22: "WWS",
        23: "Light",
        24: "Dark",
        25: "Variations"
    }

    name_record_positions: List[Tuple[int, int, int]] = []
    for name_record_index in range(naming_table['count']):
        platform_id = unpack('>H', buffer.read(2))[0]
        encoding_id = unpack('>H', buffer.read(2))[0]
        language_id = unpack('>H', buffer.read(2))[0]
        name_id = unpack('>H', buffer.read(2))[0]
        length = unpack('>H', buffer.read(2))[0]
        offset = unpack('>H', buffer.read(2))[0]
        name_record_positions.append((name_id, offset, length))

    name_records = {}
    for name_id, offset, length in name_record_positions:
        buffer.seek(naming_table['stringOffset'] + offset)
        value = buffer.read(length)
        text = value.decode('utf-16-be').replace(b'\x00'.decode('utf-8'), '')
        try:
            name_records[name_ids[name_id]] = text
        except KeyError:
            continue

    return name_records


def parse_os2_table(data: bytes) -> Dict[str, Union[str, int]]:
    buffer = BytesIO(data)

    version = unpack('>H', buffer.read(2))[0]

    # oof
    # https://docs.microsoft.com/en-us/typography/opentype/spec/os2#os2-table-and-opentype-font-variations
    if version == 5:
        return {
            "version": version,
            "xAvgCharWidth": unpack('>h', buffer.read(2))[0],
            "usWeightClass": unpack('>H', buffer.read(2))[0],
            "usWidthClass": unpack('>H', buffer.read(2))[0],
            "fsType": unpack('>H', buffer.read(2))[0],
            "ySubscriptXSize": unpack('>h', buffer.read(2))[0],
            "ySubscriptYSize": unpack('>h', buffer.read(2))[0],
            "ySubscriptXOffset": unpack('>h', buffer.read(2))[0],
            "ySubscriptYOffset": unpack('>h', buffer.read(2))[0],
            "ySuperscriptXSize": unpack('>h', buffer.read(2))[0],
            "ySuperscriptYSize": unpack('>h', buffer.read(2))[0],
            "ySuperscriptXOffset": unpack('>h', buffer.read(2))[0],
            "ySuperscriptYOffset": unpack('>h', buffer.read(2))[0],
            "yStrikeoutSize": unpack('>h', buffer.read(2))[0],
            "yStrikeoutPosition": unpack('>h', buffer.read(2))[0],
            "sFamilyClass": unpack('>h', buffer.read(2))[0],
            "panose": [unpack('>b', buffer.read(1))[0] for i in range(10)],
            "ulUnicodeRange1": unpack('>I', buffer.read(4))[0],
            "ulUnicodeRange2": unpack('>I', buffer.read(4))[0],
            "ulUnicodeRange3": unpack('>I', buffer.read(4))[0],
            "ulUnicodeRange4": unpack('>I', buffer.read(4))[0],
            "achVendID": buffer.read(4).decode('ascii'),
            "fsSelection": unpack('>H', buffer.read(2))[0],
            "usFirstCharIndex": unpack('>H', buffer.read(2))[0],
            "usLastCharIndex": unpack('>H', buffer.read(2))[0],
            "sTypoAscender": unpack('>h', buffer.read(2))[0],
            "sTypoDescender": unpack('>h', buffer.read(2))[0],
            "sTypoLineGap": unpack('>h', buffer.read(2))[0],
            "usWinAscent": unpack('>H', buffer.read(2))[0],
            "usWinDescent": unpack('>H', buffer.read(2))[0],
            "ulCodePageRange1": unpack('>I', buffer.read(4))[0],
            "ulCodePageRange2": unpack('>I', buffer.read(4))[0],
            "sxHeight": unpack('>h', buffer.read(2))[0],
            "sCapHeight": unpack('>h', buffer.read(2))[0],
            "usDefaultChar": unpack('>H', buffer.read(2))[0],
            "usBreakChar": unpack('>H', buffer.read(2))[0],
            "usMaxContext": unpack('>H', buffer.read(2))[0],
            "usLowerOpticalPointSize": unpack('>H', buffer.read(2))[0],
            "usUpperOpticalPointSize": unpack('>H', buffer.read(2))[0]
        }
    elif version in [2, 3, 4]:
        return {
            "version": version,
            "xAvgCharWidth": unpack('>h', buffer.read(2))[0],
            "usWeightClass": unpack('>H', buffer.read(2))[0],
            "usWidthClass": unpack('>H', buffer.read(2))[0],
            "fsType": unpack('>H', buffer.read(2))[0],
            "ySubscriptXSize": unpack('>h', buffer.read(2))[0],
            "ySubscriptYSize": unpack('>h', buffer.read(2))[0],
            "ySubscriptXOffset": unpack('>h', buffer.read(2))[0],
            "ySubscriptYOffset": unpack('>h', buffer.read(2))[0],
            "ySuperscriptXSize": unpack('>h', buffer.read(2))[0],
            "ySuperscriptYSize": unpack('>h', buffer.read(2))[0],
            "ySuperscriptXOffset": unpack('>h', buffer.read(2))[0],
            "ySuperscriptYOffset": unpack('>h', buffer.read(2))[0],
            "yStrikeoutSize": unpack('>h', buffer.read(2))[0],
            "yStrikeoutPosition": unpack('>h', buffer.read(2))[0],
            "sFamilyClass": unpack('>h', buffer.read(2))[0],
            "panose": [unpack('>b', buffer.read(1))[0] for i in range(10)],
            "ulUnicodeRange1": unpack('>I', buffer.read(4))[0],
            "ulUnicodeRange2": unpack('>I', buffer.read(4))[0],
            "ulUnicodeRange3": unpack('>I', buffer.read(4))[0],
            "ulUnicodeRange4": unpack('>I', buffer.read(4))[0],
            "achVendID": buffer.read(4).decode('ascii'),
            "fsSelection": unpack('>H', buffer.read(2))[0],
            "usFirstCharIndex": unpack('>H', buffer.read(2))[0],
            "usLastCharIndex": unpack('>H', buffer.read(2))[0],
            "sTypoAscender": unpack('>h', buffer.read(2))[0],
            "sTypoDescender": unpack('>h', buffer.read(2))[0],
            "sTypoLineGap": unpack('>h', buffer.read(2))[0],
            "usWinAscent": unpack('>H', buffer.read(2))[0],
            "usWinDescent": unpack('>H', buffer.read(2))[0],
            "ulCodePageRange1": unpack('>I', buffer.read(4))[0],
            "ulCodePageRange2": unpack('>I', buffer.read(4))[0],
            "sxHeight": unpack('>h', buffer.read(2))[0],
            "sCapHeight": unpack('>h', buffer.read(2))[0],
            "usDefaultChar": unpack('>H', buffer.read(2))[0],
            "usBreakChar": unpack('>H', buffer.read(2))[0],
            "usMaxContext": unpack('>H', buffer.read(2))[0]
        }
    elif version == 1:
        return {
            "version": version,
            "xAvgCharWidth": unpack('>h', buffer.read(2))[0],
            "usWeightClass": unpack('>H', buffer.read(2))[0],
            "usWidthClass": unpack('>H', buffer.read(2))[0],
            "fsType": unpack('>H', buffer.read(2))[0],
            "ySubscriptXSize": unpack('>h', buffer.read(2))[0],
            "ySubscriptYSize": unpack('>h', buffer.read(2))[0],
            "ySubscriptXOffset": unpack('>h', buffer.read(2))[0],
            "ySubscriptYOffset": unpack('>h', buffer.read(2))[0],
            "ySuperscriptXSize": unpack('>h', buffer.read(2))[0],
            "ySuperscriptYSize": unpack('>h', buffer.read(2))[0],
            "ySuperscriptXOffset": unpack('>h', buffer.read(2))[0],
            "ySuperscriptYOffset": unpack('>h', buffer.read(2))[0],
            "yStrikeoutSize": unpack('>h', buffer.read(2))[0],
            "yStrikeoutPosition": unpack('>h', buffer.read(2))[0],
            "sFamilyClass": unpack('>h', buffer.read(2))[0],
            "panose": [unpack('>b', buffer.read(1))[0] for i in range(10)],
            "ulUnicodeRange1": unpack('>I', buffer.read(4))[0],
            "ulUnicodeRange2": unpack('>I', buffer.read(4))[0],
            "ulUnicodeRange3": unpack('>I', buffer.read(4))[0],
            "ulUnicodeRange4": unpack('>I', buffer.read(4))[0],
            "achVendID": buffer.read(4).decode('ascii'),
            "fsSelection": unpack('>H', buffer.read(2))[0],
            "usFirstCharIndex": unpack('>H', buffer.read(2))[0],
            "usLastCharIndex": unpack('>H', buffer.read(2))[0],
            "sTypoAscender": unpack('>h', buffer.read(2))[0],
            "sTypoDescender": unpack('>h', buffer.read(2))[0],
            "sTypoLineGap": unpack('>h', buffer.read(2))[0],
            "usWinAscent": unpack('>H', buffer.read(2))[0],
            "usWinDescent": unpack('>H', buffer.read(2))[0],
            "ulCodePageRange1": unpack('>I', buffer.read(4))[0],
            "ulCodePageRange2": unpack('>I', buffer.read(4))[0]
        }
    elif version == 0:
        return {
            "version": version,
            "xAvgCharWidth": unpack('>h', buffer.read(2))[0],
            "usWeightClass": unpack('>H', buffer.read(2))[0],
            "usWidthClass": unpack('>H', buffer.read(2))[0],
            "fsType": unpack('>H', buffer.read(2))[0],
            "ySubscriptXSize": unpack('>h', buffer.read(2))[0],
            "ySubscriptYSize": unpack('>h', buffer.read(2))[0],
            "ySubscriptXOffset": unpack('>h', buffer.read(2))[0],
            "ySubscriptYOffset": unpack('>h', buffer.read(2))[0],
            "ySuperscriptXSize": unpack('>h', buffer.read(2))[0],
            "ySuperscriptYSize": unpack('>h', buffer.read(2))[0],
            "ySuperscriptXOffset": unpack('>h', buffer.read(2))[0],
            "ySuperscriptYOffset": unpack('>h', buffer.read(2))[0],
            "yStrikeoutSize": unpack('>h', buffer.read(2))[0],
            "yStrikeoutPosition": unpack('>h', buffer.read(2))[0],
            "sFamilyClass": unpack('>h', buffer.read(2))[0],
            "panose": [unpack('>b', buffer.read(1))[0] for i in range(10)],
            "ulUnicodeRange1": unpack('>I', buffer.read(4))[0],
            "ulUnicodeRange2": unpack('>I', buffer.read(4))[0],
            "ulUnicodeRange3": unpack('>I', buffer.read(4))[0],
            "ulUnicodeRange4": unpack('>I', buffer.read(4))[0],
            "achVendID": buffer.read(4).decode('ascii'),
            "fsSelection": unpack('>H', buffer.read(2))[0],
            "usFirstCharIndex": unpack('>H', buffer.read(2))[0],
            "usLastCharIndex": unpack('>H', buffer.read(2))[0],
            "sTypoAscender": unpack('>h', buffer.read(2))[0],
            "sTypoDescender": unpack('>h', buffer.read(2))[0],
            "sTypoLineGap": unpack('>h', buffer.read(2))[0],
            "usWinAscent": unpack('>H', buffer.read(2))[0],
            "usWinDescent": unpack('>H', buffer.read(2))[0]
        }
    else:
        raise FileFormatError(f'An OS/2 table of version {version} was found, which is invalid')


def generate_data_uri(filepath: str) -> str:
    with open(filepath, 'rb') as file:
        encoded_bytes = encodebytes(file.read())
    data = encoded_bytes.decode('utf-8').replace('\n', '')
    data = f'data:font/woff;charset=utf-8;base64,{data}'
    return data


def generate_css(filepath: str) -> str:
    woff_properties = read_woff_properties(filepath)
    try:
        fs_type = woff_properties['os/2']['fsType']
        if fs_type != 0:
            raise Exception(f'This font has an fsType of {fs_type}, meaning that it may not be legal to embed. '
                            f'You can read more about this here: '
                            f'https://docs.microsoft.com/en-us/typography/opentype/spec/os2#fstype '
                            f'(but hey, I\'m an error message, not a cop)')
    except KeyError:
        pass

    css_properties = {}
    width_classes = {
        1: "ultra-condensed",
        2: "extra-condensed",
        3: "condensed",
        4: "semi-condensed",
        5: "normal",
        6: "semi-expanded",
        7: "expanded",
        8: "extra-expanded",
        9: "ultra-expanded"
    }
    weight_words = [w.lower() for w in
                    ('Thin', 'ExtraLight', 'Light', 'Bold', 'SemiBold',
                     'Black', 'Medium', 'Hairline', 'ExtraBold', 'Regular')]

    font_family = woff_properties['name']['Family']
    font_family = font_family.split(' ')
    while font_family[-1].lower() in weight_words:
        font_family.pop(-1)
    css_properties['family'] = ' '.join(font_family)

    css_properties['copyright'] = woff_properties['name']['Copyright']
    css_properties['license'] = woff_properties['name']['License']

    css_properties['subfamily'] = woff_properties['name']['Subfamily']
    css_properties['weight'] = woff_properties['os/2']['usWeightClass']
    css_properties['width'] = width_classes[woff_properties['os/2']['usWidthClass']]
    css_properties['src'] = generate_data_uri(filepath)

    css = '@font-face {'
    for property_name in css_properties:
        if property_name == 'copyright':
            new_line = f"/*Copyright: {css_properties['copyright']}*/"
        elif property_name == 'license':
            new_line = f"/*License: {css_properties['license']}*/"
        elif property_name == 'src':
            new_line = f"src: url(\"{css_properties['src']}\") format(\"woff\")"
        elif property_name == 'family':
            new_line = f"font-family: {css_properties['family']}"
        elif property_name == 'subfamily':
            new_line = f"font-style: {'italic' if 'italic' in css_properties['subfamily'].lower() else 'normal'}"
        elif property_name == 'weight':
            new_line = f"font-weight: {css_properties['weight']}"
        elif property_name == 'width':
            new_line = f"font-stretch: {css_properties['width']}"
        else:
            continue
        css += '\n\t' + new_line + ';'
    css += '\n}\n'

    return css


def generate_and_save(source: str, destination: str) -> None:
    css = generate_css(source)
    with open(destination, 'w', encoding='utf-8') as file:
        file.write(css)


if __name__ == '__main__':
    parser = ArgumentParser(description="Embed fonts in CSS files")

    parser.add_argument('source', nargs=1, type=str, help='Path to the .woff font file')
    parser.add_argument('destination', nargs=1, type=str, help='Path in which to create the CSS file')
    args = parser.parse_args()
    generate_and_save(args.source[0], args.destination[0])
