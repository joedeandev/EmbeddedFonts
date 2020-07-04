import unittest
from os.path import isfile
try:
    from embedder import read_woff_properties, generate_css
except ImportError:
    from .embedder import read_woff_properties, generate_css
from hashlib import sha1

test_filepath = 'embedder/roboto.woff'


def get_hash(string: str) -> str:
    return str(sha1(string.encode('utf-8')).hexdigest())


class EmbedderTest(unittest.TestCase):

    def test_woff_properties(self):
        properties = read_woff_properties(test_filepath)
        # if the properties worked right, this should be the SHA1 hash:
        #   fb7ccc62f67c99f18d2d5bbf4592bf8329b2b4fa
        # but we can check a few specifics just in case
        self.assertEqual(properties['name']['Full'], 'Roboto')
        self.assertEqual(properties['name']['PostScript'], 'Roboto-Regular')
        self.assertEqual(properties['os/2']['version'], 3)
        self.assertEqual(properties['os/2']['panose'][0], 2)
        self.assertEqual(properties['os/2']['ulUnicodeRange1'], 2147483687)
        self.assertEqual(
            'fb7ccc62f67c99f18d2d5bbf4592bf8329b2b4fa',
            get_hash(str(properties)))

    def test_css(self):
        css = generate_css(test_filepath)
        self.assertEqual(
            'ce154191418e5b6c8ea99467fb156ae429c76f0c',
            get_hash(css))


if __name__ == '__main__':
    if not isfile(test_filepath):
        raise FileNotFoundError(f'The test file {test_filepath} was not found in its expected location')
    unittest.main()
