#!/bin/bash

get_chapters()
{
  local filename="$1"
  shift
  local chapters="$(mkvinfo "$filename" | grep ChapterTimeStart | sed -e "s/.*ChapterTimeStart: //" | cut -c1-11 | sort | uniq)"
  echo "$chapters"
}

add_chapters()
{
  echo "$@" | tr " " "\n" | sort
}

at_least_one_chapter()
{
  local chapters="$1"
  if [ -z "$chapters" ]; then
    chapters="00:00:00.00"
  fi
  echo -n "$chapters"
}

chapter_xml()
{
  local chapter_list="$1"
  shift
  echo "<?xml version=\"1.0\" encoding=\"ISO-8859-1\"?>"
  echo "<!DOCTYPE Chapters SYSTEM \"matroskachapters.dtd\">"
  echo "<Chapters>"
  echo "  <EditionEntry>"

  for chapter in $chapter_list;
  do
    echo "    <ChapterAtom>"
    echo "      <ChapterTimeStart>$chapter</ChapterTimeStart>"
    #echo "      <ChapterDisplay>"
    #echo "        <ChapterString>Chapter $RANDOM</ChapterString>"
    #echo "        <ChapterLanguage>eng</ChapterLanguage>"
    #echo "      </ChapterDisplay>"
    echo "    </ChapterAtom>"
  done
  echo "  </EditionEntry>"
  echo "</Chapters>"
}
comma_delimit()
{
  local fields="$1"
  shift
  echo -n "$fields" | tr '\n' ',' | sed -e "s/,$//"
}
split_mkv()
{
  local output_filename="$1"
  shift
  local input_filename="$1"
  shift
  local offsets="$1"
  shift
  mkvmerge -o "$output_filename" --split "timecodes:$(comma_delimit "$offsets")" "$input_filename"
}
set_chapters()
{
  local video_file="$1"
  shift
  local xml_file="$1"
  shift
  mkvpropedit --chapters "$xml_file" "$video_file"
}
is_zero_offset()
{
  local offset="$1"
  shift
  [ -z "$(echo "$offset" | sed 's/[:.0]//g')" ]
}
remove_zero_chapter()
{
  local chapter_list="$1"
  shift
  for chapter in $chapter_list;
  do
    if ! is_zero_offset "$chapter"; then
      echo "$chapter"
    fi
  done
}
remove_chapter_names()
{
  local video_file="$1"
  shift
  local tempfile="tmpChapter.xml"
  chapters="$(at_least_one_chapter "$(get_chapters "$video_file")")"
  if [ -n "$chapters" ]; then  #impossible to be false due to at_least_one_chapter
    chapter_xml "$chapters" > "$tempfile" 
  else
    tempfile=""
  fi
  set_chapters "$video_file" "$tempfile" 
  rm -f "$tempfile"
}
      
split_chapters()
{
  local output_filename="$1"
  shift
  local input_filename="$1"
  shift
  local chapters="$1"
  shift
  if [ -z "$chapters" ]; then
    chapters="$(get_chapters "$input_filename")"
  fi
  chapters="$(remove_zero_chapter "$chapters")"
  if [ -z "$chapters" ]; then
    cp -f "$input_filename" "$output_filename"
  else
    chapters="$(comma_delimit "$chapters")"
    echo mkvmerge -o "$output_filename" --split "timecodes:$chapters" "$input_filename"
    mkvmerge -o "$output_filename" --split "timecodes:$chapters" "$input_filename"
  fi
}

join_files()
{
  local output_filename="$1"
  shift
  local cmd_line=""
  local prefix=""
  for filename in "$@"; do
    cmd_line="$cmd_line $prefix$filename" 
    prefix="+"
  done
  mkvmerge -o "$output_filename" $cmd_line
}
list_files()
{
  local prefix="$1"
  shift
  local index="$1"
  shift
  local last="$1"
  shift
  for num in $(seq -f "%03g" "$index" "$last"); do
    echo "$prefix$num.mkv"
  done
}
#comma_delimit "$(get_chapters "input.mkv")"
#remove_chapter_names "output/Opening.mkv"
#list_files "output-" 10 20

make_episode()
{
  local output_filename="$1"
  shift
  local index="$1"
  shift
  local last="$1"
  shift
  if [ -z "$last" ]; then
    last="$index"
  fi

  files="$(list_files "output-" "$index" "$last")"
  for filename in $files;
  do
    remove_chapter_names "$filename"
  done
  join_files "$output_filename" "output/Opening_V1.mkv" $files
  remove_chapter_names "$output_filename"
  get_chapters "$output_filename" > last_chapters.xml
  echo -n "$output_filename" > last_filename.txt
}

add_chapters_to_episode()
{
  local filename="$(cat last_filename.txt)"
  local tempfile="tmpChapter.xml"
  chapter_xml "$(add_chapters "$(cat last_chapters.xml)" $@)" > "$tempfile"
  set_chapters "$filename" "$tempfile"
}

remove_first_chapter()
{
  input_filename="$1"
  shift
  old_chapters="$(get_chapters "$input_filename")"
  dividing_chapter="$(echo "$old_chapters" | head -n 2 | tail -n 1)"

  if [ "$dividing_chapter" == "00:01:01.01" ]; then
    dividing_offset="00:01:00.00"
  elif [ "$dividing_chapter" == "00:01:01.15" ]; then
    dividing_offset="00:01:01.15"
  else
    echo "BAD TEST FOR $input_filename"
    return 1
  fi
  old_chapters="$(echo "$old_chapters" | grep -v "$dividing_chapter")"
  if [ -z "$old_chapters" ]; then
    echo "fuck"
    return 1
  fi
  chapter_xml "$old_chapters" > tmp.xml
  set_chapters "$input_filename" tmp.xml
  rm -f tmp.xml
  split_chapters tmpRemoveChap.mkv "$input_filename" "$dividing_offset" 
  rm -f tmpRemoveChap-001.mkv
  mv -f tmpRemoveChap-002.mkv "$input_filename"
}
  
#for filename in output/*.mkv;
#do
#  remove_chapter_names "$filename"
#done

#make_episode "output/Chip 'N Dale - Rescue Rangers - S02E07 - The Luck Stops Here.mkv" 6 9 

encode_ffmpeg()
{
  local input_filename="$1"
  shift
  local output_filename="$1"
  shift
  ffmpeg -i "$input_filename" \
      -c:v libx264 -preset veryslow -crf 22 -async 1 \
      -c:a libfdk_aac -vbr 3 "$output_filename"
}
