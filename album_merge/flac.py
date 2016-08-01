#!/usr/bin/env python3

import enum
import sys
import subprocess

class PictureType(enum.IntEnum):
    OTHER = 0
    FILE_ICON_32 = 1
    FILE_ICON_OTHER = 2
    COVER_FRONT = 3
    COVER_BACK = 4
    LEAFLET_PAGE = 5
    MEDIA = 6 # label side of cd
    LEAD_ARTIST = 7
    ARTIST = 8
    CONDUCTOR = 9
    BAND = 10
    COMPOSER = 11
    LYRICIST = 12
    LOCATION = 13 # recording location
    DURING_RECORDING = 14
    DURING_PERFORMANCE = 15
    SCREEN_CAPTURE = 16
    BRIGHT_FISH = 17 # "a bright coloured fish"
    ILLUSTRATION = 18
    LOGO = 19 # band/artist logo
    STUDIO_LOGO = 20 # publisher/studio logo

class BlockType(enum.IntEnum):
    STREAMINFO = 0
    PADDING = 1
    APPLICATION = 2
    SEEKTABLE = 3
    VORBIS_COMMENT = 4
    CUESHEET = 5
    PICTURE = 6

class Picture(object):
    def __init__(self, digest, description, mime):
        self.digest = digest
        self.description = description
        self.mime = mime.lower()


    def type(self):
        mime = self.mime.split('/',1)[1]
        if mime in [ 'jpg', 'jpeg' ]:
            return 'jpg'
        elif mime == 'png':
            return 'png'
        raise ValueError('Unsupported MIME: ' + self.mime)

    def __eq__(self, other):
        return (self.digest == other.digest and
                self.description == other.description and
                self.mime == other.mime)

    def __ne__(self, other):
        return not self.eq(other)

    def __hash__(self):
        return hash((self.digest, self.description, self.mime))

BLOCK_PREFIX = 'METADATA block #'

class MetaField(object):
    def __init__(self, level=0, key=None, value=None):
        self.level = level
        self.key = key
        self.value = value

    def int_value(self):
        parts = self.value.split(' ', 1)
        return int(parts[0])

    def __repr__(self):
        # prints it in a debug-friendly manner
        return str((self.level, self.key, self.value))

    def __str__(self):
        # prints it just like the metaflac output line
        if self.level == 0 and self.key == BLOCK_PREFIX:
            return self.key + self.value
        else:
            return (' ' * self.level * 2) + self.key + ': ' + self.value

class MetaListParser(object):

    DEFAULT_STATE = (0, None, None) 

    def __init__(self):
        self.current_field = MetaField()

    def process_line(self, line):
        completed_field = None
        next_field = MetaField()

        if line is None:
            terminate = True
        else:
            terminate = False
            if line.endswith('\r\n'):
                # convert any windows line ending to a unix one
                line = line[:-2] + '\n'
            elif not line.endswith('\n'):
                # if our line came from something other than readline, make
                # sure there's a trailing '\n' to trim off later.  When
                # appending multi-line values, we expect the \n to be at the
                # end of the prior line's text.
                line += '\n'

            # store the current line length, strip leading spaces, then
            # calculate the indentation level, given 2-space indents.
            next_field.level = (len(line) - len(line.lstrip(' '))) // 2
            # NOTE: hack to make a special case to only allow one level-0 key.
            # because metaflac doesn't output in a very clear way for
            # multi-line values.  Without this, any line with a colon
            # in something such as an unsyncedlyrics tag would be seen as a
            # key/value and we would terminate early.
            if next_field.level == 0:
                # Only support one level-0 key, so comments with newlines and
                # lines that start with "bla:" don't get parsed here.
                if line.startswith(BLOCK_PREFIX):
                    next_field = MetaField(
                            0, BLOCK_PREFIX, line[len(BLOCK_PREFIX):])
                    terminate = True
            # NOTE: hack to only allow key/value pairs that accompany level
            # changes to move up or down a single level at a time.  This is
            # how the format works anyway.  All of the blocks that contain
            # long lists of things, such as seek points, data bytes, or
            # comments are the final entries in their block.  So, though these
            # are two-levels deep, and returning to the outer level would be a
            # step-up of 2, we don't have to deal with this case.  This is yet
            # another way of handling multi-line values, trying to
            # differentiate between additional data and key/value pairs.
            elif abs(self.current_field.level - next_field.level) <= 1:
                # If only changing depth by < 1, this is considered a new field
                parts = line.split(':', 1)
                if len(parts) == 2:
                    next_field.key = parts[0].strip()
                    next_field.value = parts[1]
                    if next_field.value.startswith(' '): # remove ' ' from ': '
                        next_field.value = next_field.value[1:]
                    terminate = True

        if not terminate:
            # The line is part of prior data
            if self.current_field.key:
                self.current_field.value += line
            else:
                # Got a free-line, without prior data... bad format?
                raise ValueError('Unexpected line: ' + line)
        else:
            # For the first key, we won't have a prior key to terminate
            if self.current_field.key is not None:
                # Terminate/return it 
                if not self.current_field.value.endswith('\n'):
                    # This is just a sanity check
                    raise ValueError('Parser error, no LF: {}'.format(
                        self.current_field.value))
                self.current_field.value = self.current_field.value[:-1]
                completed_field = self.current_field
            # store the new key for processing
            self.current_field = next_field
        return completed_field
                

class FLAC(object):

    def __init__(self, filename, picture_db = None):
        self.filename = filename
        self.sample_rate = None
        self.total_samples = None
        self._comments = {}
        self._pictures = {}
        self._picture_db = picture_db

        self._parser = MetaListParser()

        desired = [BlockType.STREAMINFO, BlockType.VORBIS_COMMENT]
        if picture_db is not None:
            desired.append(BlockType.PICTURE)

        child = subprocess.Popen(['metaflac',
                '--list', '--no-utf8-convert',
                '--block-type=' + ','.join([value.name for value in desired]),
                self.filename],
                stdout = subprocess.PIPE, stderr = subprocess.DEVNULL)

        block_type = None

        while True:
            # boilerplate
            line = child.stdout.readline().decode(sys.getdefaultencoding())
            if line == '':
                line = None # will flush the parser

            field = self._parser.process_line(line)
            if field is not None:
                # processing
                if field.level == 0 and field.key == BLOCK_PREFIX:
                    block_type = None  # num = field.int_value()
                elif block_type is None and field.key == 'type':
                    block_type = BlockType(field.int_value())
                    if block_type == BlockType.PICTURE:
                        picture_bytes = 0
                        picture_type = None
                        picture_data = None
                        picture_mime = None
                        picture_description = None
                elif block_type == BlockType.STREAMINFO:
                    if field.key == 'sample_rate':
                        self.sample_rate = field.int_value()
                    elif field.key == 'total samples':
                        self.total_samples = field.int_value()
                elif block_type == BlockType.VORBIS_COMMENT:
                    if (field.key.startswith('comment[') and
                            field.key.endswith(']')):
                        key, value = field.value.split('=', 1)
                        self._comments[key] = value
                elif block_type == BlockType.PICTURE:
                    if field.key == 'data length':
                        picture_bytes = field.int_value()
                    elif field.key == 'type':
                        picture_type = PictureType(field.int_value())
                    elif field.key == 'data':
                        picture_data = bytearray()
                    elif field.key == 'MIME type':  # TODO: keep?
                        picture_mime = field.value
                    elif field.key == 'description':
                        picture_description = field.value
                    elif (picture_bytes != 0 and field.key ==
                            '{:08X}'.format(len(picture_data))):
                        picture_data += bytearray.fromhex(
                                field.value[:3 * min(16,
                                        picture_bytes - len(picture_data))])
                        if len(picture_data) == picture_bytes:
                            # Add the image to the database, storing the digest
                            digest = self._picture_db.add(picture_data)
                            picture_bytes = 0
                            picture_data = None # allow freeing
                            # append the digest to the list if not present
                            # using list instead of set for defined order.
                            picture = Picture(digest, picture_description,
                                    picture_mime)
                            picture_list = self._pictures.get(picture_type, [])
                            if picture not in picture_list:
                                picture_list.append(picture)
                            self._pictures[picture_type] = picture_list
            # boilerplate
            if line is None:
                break
        child.wait()

    def comments(self):
        return dict(self._comments)
    
    def pictures(self):
        return dict(self._pictures)

def main():
    import file_db
    picture_db = file_db.FileDB()
    filename = 'type2/Greydon Square - Type II - The Mandelbrot Set - 01 Galaxy Rise.flac'
    filename = 'out/test.flac'
    flac = FLAC(filename, picture_db)
    return 0

if __name__ == '__main__':
  sys.exit(main())


