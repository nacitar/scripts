#!/usr/bin/env python3

import enum
import sys
import subprocess

import util
import hashlib

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
    def __init__(self, digest, description):
        self.digest = digest
        self.description = description

    def __eq__(self, other):
        return (self.digest == other.digest and
                self.description == other.description)

    def __ne__(self, other):
        return not self.eq(other)

    def __hash__(self):
        return hash((self.digest, self.description))

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

# perhaps do picture meta separately

class FLACMeta(object):

    def __init__(self, sample_rate, total_samples, channels,
            comments = None, pictures = None):
        self.sample_rate = sample_rate
        self.total_samples = total_samples
        self.channels = channels
        self.comments = comments
        self.pictures = pictures

    @staticmethod
    def from_file(filename, digest_map = None):
        sample_rate = None
        total_samples = None
        comments = {}
        pictures = {}
        channels = 0

        parser = MetaListParser()

        desired = [BlockType.STREAMINFO, BlockType.VORBIS_COMMENT]
        if digest_map is not None:
            desired.append(BlockType.PICTURE)

        child = subprocess.Popen(['metaflac',
                '--list', '--no-utf8-convert',
                '--block-type=' + ','.join([value.name for value in desired]),
                filename], stdin = subprocess.DEVNULL,
                stdout = subprocess.PIPE, stderr = subprocess.DEVNULL)

        block_type = None

        for line in util.line_reader(child.stdout, terminate=True):
            # after last line, we'll get None because terminate is True
            field = parser.process_line(line)  # None will flush
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
                        sample_rate = field.int_value()
                    elif field.key == 'total samples':
                        total_samples = field.int_value()
                    elif field.key == 'channels':
                        channels = field.int_value()
                elif block_type == BlockType.VORBIS_COMMENT:
                    if (field.key.startswith('comment[') and
                            field.key.endswith(']')):
                        key, value = field.value.split('=', 1)
                        comments[key] = value
                elif block_type == BlockType.PICTURE:
                    if field.key == 'data length':
                        picture_bytes = field.int_value()
                    elif field.key == 'type':
                        picture_type = PictureType(field.int_value())
                    elif field.key == 'data':
                        picture_data = bytearray()
                    elif field.key == 'description':
                        picture_description = field.value
                    elif (picture_bytes != 0 and field.key ==
                            '{:08X}'.format(len(picture_data))):
                        picture_data += bytearray.fromhex(
                                field.value[:3 * min(16,
                                        picture_bytes - len(picture_data))])
                        if len(picture_data) == picture_bytes:
                            # Add the image to the database, storing the digest
                            digest = hashlib.sha1(picture_data).digest()
                            if digest not in digest_map:
                                digest_map[digest] = picture_data
                            picture_bytes = 0
                            picture_data = None # allow freeing
                            # append the digest to the list if not present
                            # using list instead of set for defined order.
                            picture = Picture(digest, picture_description)
                            picture_list = pictures.get(picture_type, [])
                            if picture not in picture_list:
                                picture_list.append(picture)
                            pictures[picture_type] = picture_list
        child.wait()
        return FLACMeta(sample_rate, total_samples, channels, comments, pictures)

def main():
    digest_map = {}
    filename = 'type2/Greydon Square - Type II - The Mandelbrot Set - 01 Galaxy Rise.flac'
    filename = 'out/test.flac'
    flac = FLACMeta(filename, digest_map)
    return 0

if __name__ == '__main__':
  sys.exit(main())


