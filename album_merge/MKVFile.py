#!/usr/bin/env python3

import os
import sys
import subprocess
import shutil



import unit
import uid
from timestamp import Timestamp
import markup
import flac
import util
import file_db

############


# req sox
def mergeAudio(files, output='-'):
    return subprocess.Popen(['sox'] + files + ['-t', 'wav', output],
            stdout=subprocess.PIPE, stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)

# req flac
def mergeFlac(files, output='-'):
    sox = mergeAudio(files, '-')
    flac = subprocess.Popen(['flac', '--force', '--ignore-chunk-sizes',
            '--no-preserve-modtime', '--no-padding', '--best',
            '-o', output, '-'],
            stdin=sox.stdout, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)
    sox.wait()
    return flac

# req imagemagick
def imageInfo(filename):
    child = subprocess.Popen(['identify', '-format', '%W %H %C', filename],
            stdout=subprocess.PIPE, stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
    result = child.communicate()[0]
    child.wait()
    return result.decode(sys.stdout.encoding).split(' ')

def imageResize(input_filename, output_filename, width='', height=''):
    if not width and not height:
        raise ValueError('Must provide a width or height.')
    child = subprocess.Popen(['convert', input_filename, '-resize',
            '{}x{}'.format(width, height), output_filename],
            stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
    return (child.wait() == 0)

def prepare_flac_album(dirname, staging_dir):
    picture_db = file_db.FileDB()
    uid_group = uid.Group()

    files = os.listdir(dirname)
    flac_files = []

    picture_file = markup.PictureFile()

    for basename in files:
        lower_name = basename.lower()
        name_noext, ext = os.path.splitext(lower_name)
        if ext == '.flac':
            flac_files.append(basename)
        if ext in ['.jpg', '.jpeg', '.png']:
            filename = os.path.join(dirname, basename)
            # NOTE: copy external cover image as full_cover
            if ext == '.jpeg':
                ext = '.jpg'  # simplify
            if name_noext == 'cover':
                width, height, codec = imageInfo(filename)
                if height >= width:
                    lower_name = 'full_cover' + ext
                else:
                    lower_name = 'full_cover_land' + ext
            picture_file.pictures().append(markup.Picture(
                lower_name, lower_name))
            shutil.copy(filename,
                    os.path.join(staging_dir, lower_name))

    flac_files.sort()

    track_list = {}

    chapter_file = markup.ChapterFile()
    chapter_file.set_uid(uid_group.generate())
    tag_file = markup.TagFile()

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

    tag_file.tags().append(album_tag)

    album_tag.add_comment(dirname)

    album_total_tracks.set_value(str(len(flac_files)))

    sample_offset = 0
    sample_rate = None

    pictures = {}
    for basename in flac_files:
        filename = os.path.join(dirname, basename)
        track = flac.FLAC(filename, picture_db)
        if sample_rate is None:
            sample_rate = track.sample_rate
        else:
            if sample_rate != track.sample_rate:
                raise RuntimeError('Cannot combine different sample rates.')
        timestamp = Timestamp(sample_offset * unit.SEC / sample_rate)
        # Chapters
        chapter = markup.Chapter(
                uid=str(uid_group.generate()),
                start_time=str(timestamp))
        sample_offset += track.total_samples
        chapter.add_comment(basename)
        chapter_file.chapters().append(chapter)

        # Tagging
        track_tag = markup.Tag('30', 'TRACK', chapter.uid())
        track_tag.add_comment(basename)

        track_artist = markup.Field('ARTIST')
        track_number = markup.Field('PART_NUMBER')
        track_title = markup.Field('TITLE')
        track_lyrics = markup.Field('LYRICS')
        track_tag.fields().extend([
            track_artist,
            track_number,
            track_title,
            track_lyrics])
        tag_file.tags().append(track_tag)
        for key, value in track.comments().items():
            if key == 'ALBUMARTIST':
                album_artist.set_value(value)
            elif key == 'ALBUM':
                album_title.set_value(value)
            elif key == 'DATE':
                album_date.set_value(value)
            elif key == 'ARTIST':
                track_artist.set_value(value)
            elif key == 'TRACKNUMBER':
                track_number.set_value(value)
            elif key == 'TITLE':
                track_title.set_value(value)
            elif key == 'UNSYNCEDLYRICS':
                track_lyrics.set_value(value)
            else:
                print('Ignoring tag:', key, '=', value)
        # Pictures
        for picture_type, picture_list in track.pictures().items():
            our_list = pictures.get(picture_type, [])
            for picture in picture_list:
                if picture not in our_list:
                    our_list.append(picture)
            pictures[picture_type] = our_list

    with open(os.path.join(staging_dir, 'chapters.xml'), 'wb') as handle:
        chapter_file.write(handle)
    with open(os.path.join(staging_dir, 'tags.xml'), 'wb') as handle:
        tag_file.write(handle)

    for picture_type, picture_list  in pictures.items():
        i = 0
        for picture in picture_list:
            basename = ('flacgen_' + picture_type.name.lower() +
                    '_' + str(i) + '.' + picture.type())
            i += 1
            util.write_file(os.path.join(staging_dir, basename),
                    picture_db.get(picture.digest))

            picture_file.pictures().append(markup.Picture(
                basename, basename, picture.description))
    with open(os.path.join(staging_dir, 'pictures.xml'), 'wb') as handle:
        picture_file.write(handle)

    mergeFlac(
            [os.path.join(dirname, basename) for basename in flac_files],
            os.path.join(staging_dir, 'merged.flac')).wait()

#cover.jpg              - 600 x [>=600] (portrait/square) first attachment
#small_cover.jpg        - 120 x [>=120] (portrait/square)
#cover_land.jpg         - [>600] x 600 (landscape)
#small_cover_land.jpg   - [>120] x 120 (landscape)
def prepare_covers(dirname):
    picture_file = markup.PictureFile(
            element = markup.loadXML(os.path.join(dirname, 'pictures.xml')))

    pictures = [markup.Picture(element=child) for child in
            picture_file.pictures().children()]

    new_pictures = []
    existing_pictures = []

    for picture in pictures:
        existing_pictures.append(picture.name())
        lower_name = picture.name().lower()
        basename, ext = os.path.splitext(lower_name)
        picture_path = os.path.join(dirname, picture.filename())
        if basename == 'full_cover':
            new_pictures.append('cover'+ext)
            imageResize(picture_path, os.path.join(dirname, new_pictures[-1]),
                    height='600')
            new_pictures.append('small_cover'+ext)
            imageResize(picture_path, os.path.join(dirname, new_pictures[-1]),
                    height='120')
        if basename == 'full_cover_land':
            new_pictures.append('cover_land'+ext)
            imageResize(picture_path, os.path.join(dirname, new_pictures[-1]),
                    width='600')
            new_pictures.append('small_cover_land'+ext)
            imageResize(picture_path, os.path.join(dirname, new_pictures[-1]),
                    width='120')

    for name in new_pictures:
        if name not in existing_pictures:
            picture_file.pictures().append(markup.Picture(name, name))
    if new_pictures:
        with open(os.path.join(dirname, 'pictures.xml'), 'wb') as handle:
            picture_file.write(handle)


def assemble_mkv(dirname):
    output_file = os.path.join(dirname, 'output.mka')
    input_file = os.path.join(dirname, 'merged.flac')
    command = ['mkvmerge', '-o', output_file,
            '--chapters', os.path.join(dirname, 'chapters.xml'),
            '--global-tags', os.path.join(dirname, 'tags.xml'),
            '--language', '0:eng', '--default-track', '0:1',
            input_file]

    picture_file = markup.PictureFile(
            element = markup.loadXML(os.path.join(dirname, 'pictures.xml')))

    pictures = [markup.Picture(element=child) for child in
            picture_file.pictures().children()]

    for picture in pictures:
        if picture.description() is not None:
            command.extend([
                '--attachment-description', picture.description()])
        command.extend([
            '--attachment-name', picture.name(),
            '--attach-file', os.path.join(dirname, picture.filename())])
    print(command)
    child = subprocess.Popen(command)
    child.wait()



# NOTE: still have to do album replay gain scan with foobar2000
def main():
    if False:
        prepare_flac_album('type2', 'staging')
        prepare_covers('staging')
    if False:
        assemble_mkv('staging')

    return 0

if __name__ == '__main__':
  sys.exit(main())


