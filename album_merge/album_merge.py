#!/usr/bin/env python3

import os
import sys
import subprocess
import shutil

import unit
import uid
import markup
import flac
import util

class ImageMeta(object):
    def __init__(self, format, width, height):
        self.format = format
        self.width = width
        self.height = height

    def extension(self):
        ext = '.' + self.format.lower()
        if ext == '.jpeg':
            return '.jpg'
        return ext

    def landscape(self):
        return self.width > self.height

    # NOTE: requires imagemagick
    @staticmethod
    def __identify(filename, stdin = subprocess.DEVNULL):
        return subprocess.Popen(
                ['identify', '-format', '%W %H %m', filename],
                stdout=subprocess.PIPE, stdin=stdin,
                stderr=subprocess.DEVNULL)

    @staticmethod
    def __process_output(child):
        result = next(util.line_reader(child.stdout))  # one line
        child.stdout.close()
        if child.wait() != 0:
            raise RuntimeError('Could not identify image properties.')
        parts = result.split(' ', 2)
        return ImageMeta(format = parts[2].lower(),
                width = int(parts[0]), height = int(parts[1]))

    @staticmethod
    def from_file(filename):
        child = ImageMeta.__identify(filename)
        return ImageMeta.__process_output(child)

    @staticmethod
    def from_data(data):
        child = ImageMeta.__identify('-', subprocess.PIPE)
        child.stdin.write(data)
        child.stdin.close()
        return ImageMeta.__process_output(child)

class Image(object):
    def __init__(self, data):
        self.set_data(data)

    def set_data(self, data):
        self._data = data
        self._meta = None

    def data(self):
        return self._data

    def meta(self):
        if self._meta is None:
            self._meta = ImageMeta.from_data(self._data)
        return self._meta

    @staticmethod
    def from_file(filename):
        data = bytearray()
        with open(filename, 'rb') as handle:
            for block in util.block_reader(handle):
                data += block
        return Image(data)


# image has changed, need to update things
# flac needs to have meta/from approach too?


class FileMeta(object):
    def __init__(self, filename, meta):
        self.filename = filename
        self.meta = meta

def scanDirectory(dirname, db):
    files = os.listdir(dirname)
    files.sort()  # relying on file names to be sorted
    tracks = []
    images = []

    for basename in files:
        filename = os.path.join(dirname, basename)
        ext = os.path.splitext(basename)[1].lower()
        if ext == '.flac':
            tracks.append(FileMeta(filename,
                    flac.FLACMeta.from_file(filename, db)))
        if ext in ['.jpg', '.jpeg', '.png']:
            images.append(FileMeta(filename,
                    ImageMeta.from_file(filename)))

    return (tracks, images)

#cover.jpg              - 600 x [>=600] (portrait/square) first attachment
#small_cover.jpg        - 120 x [>=120] (portrait/square)
#cover_land.jpg         - [>600] x 600 (landscape)
#small_cover_land.jpg   - [>120] x 120 (landscape)

COVER_OPTIONS = [
        [('cover', '', 600), ('small_cover', '', 120)],  # portrait
        [('cover', 600, ''), ('small_cover', 120, '')]]  # landscape
def prepare_flac_album(source_dir, dest_dir, sample_rate = None,
        channels = None):
    picture_db = {}
    uid_group = uid.Group()

    files = os.listdir(source_dir)

    picture_xml = markup.PictureFile()


    tracks, images = scanDirectory(source_dir, picture_db)

    image_names = set()
    for image in images:
        name = os.path.splitext(os.path.basename(image.filename))[0]
        suffix = '_land' if image.meta.landscape() else ''
        ext = image.meta.extension()
        if name.lower() == 'cover' + suffix:
            name = 'full_cover' + suffix
        if name.lower() in ['full_cover', 'full_cover_land']:
            for gen_name, width, height in COVER_OPTIONS[image.meta.landscape()]:
                dest_name = gen_name + suffix + ext
                # req imagemagick
                convert = subprocess.Popen(['convert', image.filename,
                        '-resize', '{}x{}'.format(width, height),
                        os.path.join(dest_dir, dest_name)])
                if convert.wait() != 0:
                    raise RuntimeError('Error generating image:'
                            ' {}'.format(dest_name))
                image_names.add(dest_name)
        dest_name = name + ext
        shutil.copy(image.filename, os.path.join(dest_dir, dest_name))
        image_names.add(dest_name)

    for name in sorted(list(image_names)):
        picture_xml.pictures().append(markup.Picture(name, name))

    chapter_xml = markup.ChapterFile()
    chapter_xml.set_uid(uid_group.generate())
    tag_xml = markup.TagFile()

    album_tag = markup.Tag('50', 'ALBUM')
    album_artist = markup.Field('ARTIST')
    album_title = markup.Field('TITLE')
    album_date = markup.Field('DATE_RELEASED')
    album_total_tracks = markup.Field('TOTAL_PARTS')
    album_tag.fields().extend([
        album_artist,
        album_title,
        album_date,
        album_total_tracks])

    album_field_map = {
        'ALBUMARTIST': album_artist,
        'ALBUM': album_title,
        'DATE': album_date
    }

    tag_xml.tags().append(album_tag)

    album_tag.add_comment(source_dir)

    album_total_tracks.set_value(str(len(tracks)))

    sample_offset = 0

    # Used in a comment later
    accompaniment = markup.Field('ACCOMPANIMENT')
    accompaniment.prettify()

    pictures = {}
    seekpoints = []

    # highest sample rate
    if sample_rate is None:
        sample_rate = max([track.meta.sample_rate for track in tracks])
        print('Highest sample rate: {}'.format(sample_rate))

    if channels is None:
        channels = max([track.meta.channels for track in tracks])
        print('Highest channels: {}'.format(channels))

    for track in tracks:
        if (sample_rate != track.meta.sample_rate or
                channels != track.meta.channels):
            print('Resampling track from {}:{} to {}:{}'.format(
                    track.meta.sample_rate, track.meta.channels,
                    sample_rate, channels))
            newfile = os.path.join(dest_dir, os.path.basename(track.filename))
            # Resample
            sox = subprocess.Popen(['sox', track.filename, newfile,
                    'channels', str(channels), 'rate', str(sample_rate)],
                    stdout=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL)  # print errors to terminal
            if sox.wait() != 0:
                raise RuntimeError('Error upsampling ' + track.filename)
            # Read new file
            newtrack = flac.FLACMeta.from_file(newfile)
            # update to refer to resampled file instead, but keeping original
            # comments/pictures
            track.filename = newfile
            track.meta.sample_rate = newtrack.sample_rate
            track.meta.total_samples = newtrack.total_samples

        # Seek points
        seekpoints.append(sample_offset)  # start of track

        # Chapters
        chapter = markup.Chapter(
                uid=str(uid_group.generate()),
                start_time=sample_offset * unit.SEC / sample_rate)
        sample_offset += track.meta.total_samples
        chapter.add_comment(track.filename)
        chapter_xml.chapters().append(chapter)

        # Tagging
        track_tag = markup.Tag('30', 'TRACK', chapter.uid())
        track_tag.add_comment(track.filename)

        track_artist = markup.Field('ARTIST')
        track_number = markup.Field('PART_NUMBER')
        track_title = markup.Field('TITLE')
        track_lyrics = markup.Field('LYRICS')
        track_tag.fields().extend([
            track_artist,
            track_number,
            track_title,
            track_lyrics])
        # for editing convenience
        track_tag.add_comment('\n{}'.format(accompaniment))

        track_field_map = {
            'ARTIST': track_artist,
            'TRACKNUMBER': track_number,
            'TITLE': track_title,
            'UNSYNCEDLYRICS': track_lyrics,
        }

        tag_xml.tags().append(track_tag)
        for key, value in track.meta.comments.items():
            field = album_field_map.get(key.upper())
            if field is not None:
                orig_value = field.value()
                if orig_value and orig_value != value:
                    raise ValueError('Conflicting album field values: '
                            ' {}: {} != {}'.format(key, orig_value, value))
                field.set_value(value)
            else:
                field = track_field_map.get(key.upper())
                if field is not None:
                    if key.upper() == 'ARTIST':
                        album_value = album_artist.value()
                        if not album_value:
                            # set album artist
                            album_artist.set_value(value)
                        if value == album_value:
                            track_artist.set_value('')
                    else:
                        if field.value():
                            raise ValueError('Multiple field values on single'
                                    ' track: {}'.format(key))
                        field.set_value(value)
                else:
                    print('Ignoring tag:', key, '=', value)
        # Remove empty fields
        for field in track_field_map.values():
            if not field.value():
                track_tag.fields().remove(field)

                        
        # Pictures
        for picture_type, picture_list in track.meta.pictures.items():
            our_list = pictures.get(picture_type, [])
            for picture in picture_list:
                if picture not in our_list:
                    our_list.append(picture)
            pictures[picture_type] = our_list

    with open(os.path.join(dest_dir, 'chapters.xml'), 'wb') as handle:
        chapter_xml.write(handle)
    with open(os.path.join(dest_dir, 'tags.xml'), 'wb') as handle:
        tag_xml.write(handle)

    for picture_type, picture_list  in pictures.items():
        i = 0
        for picture in picture_list:
            data = picture_db.get(picture.digest)
            meta = ImageMeta.from_data(data)
            basename = ('flacgen_' + picture_type.name.lower() +
                    '_' + str(i) + meta.extension())
            i += 1
            util.write_file(os.path.join(dest_dir, basename), data)

            picture_xml.pictures().append(markup.Picture(
                basename, basename, picture.description))
    with open(os.path.join(dest_dir, 'pictures.xml'), 'wb') as handle:
        picture_xml.write(handle)

    # req sox
    sox = subprocess.Popen(['sox'] + [track.filename for track in tracks] +
            ['-t', 'wav', '-'], stdout=subprocess.PIPE,
            stdin=subprocess.DEVNULL)  # print errors to terminal

    flac_options = ['--force', '--no-preserve-modtime', '--best']
    flac_seekpoints = ['--seekpoint={}'.format(sample)
                    for sample in seekpoints]
    output = os.path.join(dest_dir, 'merged.flac')
    # req flac
    flac_encoder = subprocess.Popen(
            ['flac'] + flac_options + flac_seekpoints + ['-o', output, '-'],
            stdin=sox.stdout)  # print status to terminal
    flac_ret = flac_encoder.wait()
    sox_ret = sox.wait()
    if flac_ret != 0:
        print("ERROR: FLAC encoder exited with code {}".format(flac_ret),
                file=sys.stderr)
    if sox_ret != 0:
        print("ERROR: SOX exited with code {}".format(sox_ret),
                file=sys.stderr)
    return int(not (flac_ret == 0 and sox_ret == 0))  # 0 == success

def assemble_mkv(source_dir, dest_dir):
    input_file = os.path.join(source_dir, 'merged.flac')
    output_file = os.path.join(dest_dir, 'output.mka')
    command = ['mkvmerge', '-o', output_file,
            '--chapters', os.path.join(source_dir, 'chapters.xml'),
            '--global-tags', os.path.join(source_dir, 'tags.xml'),
            '--language', '0:eng', '--default-track', '0:1',
            input_file]

    picture_xml = markup.PictureFile(
            element = markup.loadXML(os.path.join(source_dir, 'pictures.xml')))

    pictures = [markup.Picture(element=child) for child in
            picture_xml.pictures().children()]

    for picture in pictures:
        if picture.description() is not None:
            command.extend([
                '--attachment-description', picture.description()])
        command.extend([
            '--attachment-name', picture.name(),
            '--attach-file', os.path.join(source_dir, picture.filename())])
    print(command)
    child = subprocess.Popen(command)
    return child.wait()

def check_split_accuracy(source_dir, split_dir):
    tracks, images = scanDirectory(source_dir, None)
    split_files = os.listdir(split_dir)
    split_files.sort()

    if len(tracks) != len(split_files):
        raise RuntimeError('Number of tracks/files does not match.')

    for i in range(len(tracks)):
        sox = subprocess.Popen(['sox', '--info', os.path.join(split_dir,
                split_files[i])], stdout = subprocess.PIPE)
        output = sox.communicate()[0].decode(sys.getdefaultencoding())
        sox.wait()
        
        start = output.find('=', output.find('\nDuration')) + 2
        end = output.find(' samples', start)

        if tracks[i].total_samples != int(output[start:end]):
            raise ValueError('Mismatch in {}'.format(tracks[i].filename))
        print('MATCH: {}'.format(tracks[i].filename))

    return 0



    


# ./album_merge.py prepare input/ staging/
# # check xml and files
# ./album_merge.py assemble staging/ output/  
# NOTE: still have to do album replay gain scan with foobar2000, because
# metaflac uses an older inferior algorithm
def main():
    PREPARE, ASSEMBLE, CHECKSPLIT = range(3)
    fail = False
    sample_rate = None
    channels = None
    if len(sys.argv) in [4, 5, 6]:
        arg = sys.argv[1].lower()
        if arg == 'prepare':
            command = PREPARE
        elif arg == 'assemble':
            command = ASSEMBLE
        elif arg == 'checksplit':
            command = CHECKSPLIT
        else:
            raise ValueError('Unknown command: {}'.format(command))
        source_dir = sys.argv[2]
        dest_dir = sys.argv[3]

        if len(sys.argv) >= 5:
            if command != PREPARE:
                fail = True
            else:
                sample_rate = int(sys.argv[4])
                if len(sys.argv) >= 6:
                    channels = int(sys.argv[5])
    else:
        fail = True

    if fail:
        raise ValueError('Invalid arguments.')

    if command == PREPARE: 
        exit_code = prepare_flac_album(source_dir, dest_dir, sample_rate,
                channels)
    elif command == ASSEMBLE:
        exit_code = assemble_mkv(source_dir, dest_dir)
    elif command == CHECKSPLIT:
        split_dir = dest_dir
        exit_code = check_split_accuracy(source_dir, split_dir)

    return exit_code

if __name__ == '__main__':
  sys.exit(main())


