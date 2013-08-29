#!/usr/bin/python

from pynx import *
import os
import tempfile

def make_chapter(start,name=None,lang="eng"):
  return keyword_object(start=start,name=name,lang=lang)

def chapters_from_tuples(list_of_tuples):
  output=[]
  for values in list_of_tuples:
    values=listize(values)
    output.append(make_chapter(*values))
  return output

def chapter_xml(chapter_list):
  chapter_list = listize(chapter_list)
  xml_lines = []
  xml_lines.extend([
      "<?xml version=\"1.0\" encoding=\"ISO-8859-1\"?>",
      "<!DOCTYPE Chapters SYSTEM \"matroskachapters.dtd\">",
      "<Chapters>",
      "  <EditionEntry>" ])
  for chapter in chapter_list:
    name=getattr(chapter,"name",None)
    lang=getattr(chapter,"lang",None)
    xml_lines.extend([
        ("    <ChapterAtom>"),
        ("      <ChapterTimeStart>%s</ChapterTimeStart>")%(chapter.start) ])
    if name:
      xml_lines.append("      <ChapterDisplay>")
      if name:
        xml_lines.append(
            ("        <ChapterString>%s</ChapterString>")%(chapter.name))
      if lang:
        xml_lines.extend([
            ("        <ChapterLanguage>%s</ChapterLanguage>")%(chapter.lang) ])
      xml_lines.append("      </ChapterDisplay>")
    xml_lines.append("    </ChapterAtom>")
  xml_lines.extend([
      "  </EditionEntry>",
      "</Chapters>" ])

  return os.linesep.join(xml_lines)

def get_subseconds_from_parts(hour, minute, second, subsecond):
  return ((int(hour) * 60 + int(minute)) * 60 + int(second)) * 1000 + int(subsecond)

def get_timestamp(subseconds):
  subs=subseconds % 1000
  subseconds /= 1000

  secs=subseconds % 60
  subseconds /= 60

  mins=subseconds % 60
  subseconds /= 60

  hours = subseconds

  return ("%02d:%02d:%02d.%03d") % (hours, mins, secs, subs)


def get_subseconds(timestamp):
  parts=timestamp.split(':')
  seconds=parts[-1]
  del parts[-1]
  lastparts=seconds.split('.')
  args=[]
  while len(parts) < 2:
    parts.insert(0,"0")

  if len(lastparts) == 1:
    lastparts.append("0")
  # 3 digits
  while len(lastparts[1]) != 3:
    lastparts[1] = lastparts[1]+"0"

  parts.extend(lastparts)
  return get_subseconds_from_parts(*parts)

def join_files(output,files,vlc_fix=False):
  cmd = [ 'mkvmerge', '-o', output ]
  if vlc_fix:
    raise Exception("Are you sure you want this VLC fix?!")
    cmd.extend(["--engage", "no_cue_duration", "--engage", "no_cue_relative_position"])
  first = True
  for filename in files:
    if not first:
      cmd.append('+')
    else:
      first = False
    cmd.append(filename)
  return ExecuteCommand(cmd).returnCode()

def clear_tags(filename):
  return ExecuteCommand([ 'mkvpropedit', '--tags', "global:", filename]).returnCode()

def set_tags(filename,tagdict):

  tag_lines = [
    "<?xml version=\"1.0\" encoding=\"ISO-8859-1\"?>",
    "<!DOCTYPE Tags SYSTEM \"matroskatags.dtd\">",
    "<Tags>",
    "  <Tag>" ]
  for key, value in tagdict.iteritems():
    tag_lines.extend([
      "    <Simple>",
      ("      <Name>%s</Name>") % (key),
      ("      <String>%s</String>") % (value),
      "    </Simple>" ])
  tag_lines.extend([
    "  </Tag>",
    "</Tags>" ])

  tfile=tempfile.mkstemp()
  os.write(tfile[0],os.linesep.join(tag_lines))
  os.close(tfile[0])

  ret=ExecuteCommand([ 'mkvpropedit', '--tags', "global:"+tfile[1], filename]).returnCode()
  os.remove(tfile[1])
  return ret

def set_cover(filename,cover_filename):

  ext=os.path.splitext(cover_filename)[1].lower()
  if ext != ".jpg" and ext != ".jpeg" and ext != ".png":
    raise Exception("Invalid cover format!")

  big_cover=tempfile.mkstemp()
  os.close(big_cover[0])
  small_cover=tempfile.mkstemp()
  os.close(small_cover[0])

  ExecuteCommand(['convert', cover_filename, '-resize', 'x600', big_cover[1]])
  ExecuteCommand(['convert', cover_filename, '-resize', 'x120', small_cover[1]])

  ExecuteCommand([
    'mkvpropedit',
    '--attachment-name', 'cover'+ext,
    '--replace-attachment', big_cover[1],
    filename])
  ExecuteCommand([
    'mkvpropedit',
    '--attachment-name', 'cover_small'+ext,
    '--replace-attachment', small_cover[1],
    filename])

  os.remove(big_cover[1])
  os.remove(small_cover[1])

def set_audio_language(filename,language="eng"):
  return ExecuteCommand(['mkvpropedit', 'filename', '--edit', 'track:a1', '--set', ('language=%s')%(language)]).returnCode()
