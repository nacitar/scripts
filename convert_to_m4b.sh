#!/bin/bash

#id3lib, bc, ffmpeg/ffprobe

# TODO: FIX THIS
scriptdir="${0%%/*}"

filename="$1"
float_scale=6


function ffmpeg_local()
{
	# static ffmpeg fixes silly bugs
	if [ -x "$scriptdir/ffmpeg" ]; then
		"$scriptdir/ffmpeg" "$@"
	else
		"$(type -P ffmpeg)" "$@"
	fi
}
function float_eval()
{
    local stat=0
    local result=0.0
    if [[ $# -gt 0 ]]; then
        result=$(echo "scale=$float_scale; $*" | bc -q 2>/dev/null)
        stat=$?
        if [[ $stat -eq 0  &&  -z "$result" ]]; then stat=1; fi
    fi
    echo $result
    return $stat
}


function float_cond()
{
    local cond=0
    if [[ $# -gt 0 ]]; then
        cond=$(echo "$*" | bc -q 2>/dev/null)
        if [[ -z "$cond" ]]; then cond=0; fi
        if [[ "$cond" != 0  &&  "$cond" != 1 ]]; then cond=0; fi
    fi
    local stat=$((cond == 0))
    return $stat
}

# don't need this, but i wrote it.. so it stays
get_m4b_time_base() {
	[ $# -ne 1 ] && return 1
	local filename="$1"
	while read line;
	do
		if [ "${line#*=}" == "audio" ] && read line && [ "${line%%=*}" == "time_base" ]; then
			echo "$(float_eval "${line##*=}")"
			return 0
		fi
	done < <( ffprobe -show_streams "$filename" 2>&1 | grep -E "(^codec_type=|^time_base=)" )
	return 1
}

strip_mpeg_tags()
{
	[ $# -ne 1 ] && return 1
	local filename="$1"
	local tempfile="tmp$filename"
	# git'r'done
	#MP4Box -add "$filename" "$tempfile" -new
	ffmpeg_local -y -i "$filename" -acodec copy -map_chapters -1 -map_metadata -1 -dn "$tempfile" 
	mv -f "$tempfile" "$filename"
	id3convert -s "$filename"
}

get_after_tag() {
	[ $# -ne 2 ] && return 1
	local tag="$1"
	local text="$2"
	local value="${text#*<$tag>}"
	[ "$value" == "$text" ] && return 1
	echo "$value"
	return 0
}

get_before_tag() {
	[ $# -ne 2 ] && return 1
	local tag="$1"
	local text="$2"
	echo "${text%%<$tag>*}"
	return 0
}

get_first_tag() {
	[ $# -ne 2 ] && return 1
	local tag="$1"
	local text="$2"
	local value
	value="$(get_after_tag "$1" "$2")"
	[ $? -ne 0 ] && return 1
	echo "$(get_before_tag "$1" "$value")"
	return 0	
}
# end html stuff
	
get_meta_info() {
	[ $# -ne 1 ] && return 1
	local filename="$1"
	id3info "$filename"
}

get_mp3_accurate_length() {
	[ $# -ne 1 ] && return 1
	local filename="$1"
	local result="$(ffmpeg -i "$filename" -vcodec copy -f wav -y /dev/null 2>&1 | tail -n 2 | head -n 1 | sed 's/.* time=//' | cut -d' ' -f1)"
	echo "$result"
	[ -n "$result" ]
}

get_user_field() {
	[ $# -ne 1 ] && return 1
	local field="$1"
	grep "^=== TXXX (User defined text information): ($field): " | cut -d':' -f3-
}

get_overdrive_chapters() {
	local remaining="$(cat)"
	while [ 0 ];
	do
		remaining="$(get_after_tag "Name" "$remaining")"
		[ $? -ne 0 ] && break
		name="$(get_before_tag "/Name" "$remaining")"
		remaining="$(get_after_tag "/Name" "$remaining")"
		remaining="$(get_after_tag "Time" "$remaining")"
		offset="$(get_before_tag "/Time" "$remaining")"
		echo "$offset $name"
		remaining="$(get_after_tag "/Time" "$remaining")"
	done
}

get_mp3_chapters() {
	[ $# -ne 1 ] && return 1
	local filename="$1"
	get_meta_info "$filename" | get_user_field "OverDrive MediaMarkers" | get_overdrive_chapters
}

# in seconds
get_m4b_chapters() {
	[ $# -ne 1 ] && return 1
	local filename="$1"
	ffprobe "$filename" 2>&1 | sed '/^[[:space:]]*Chapter/ { N; N; s/^.* start \(.*\),.*\n[[:space:]]*Metadata:[[:space:]]*\n[[:space:]]*title[[:space:]]*: \(.*\)[[:space:]]*$/\1 \2/; }; tx; d; :x'
}

append_mp3() {
	destfile="$1"
	shift
	infiles="$1"
	shift
	while [ $# -ne 0 ];
	do
		infiles="$infiles|$1"
		shift
	done
	ffmpeg -y -i "concat:$infiles" -acodec copy "$destfile"
}

add_chapters()
{
	#CHAPTER1=00:00:00.000
	#CHAPTER1NAME=Chapter 001
	#CHAPTER2=00:30:00.139
	#CHAPTER2NAME=Chapter 002
	MP4Box -add "$1" -chap "$2" "tmp$1"
	mp4chaps --convert --chapter-qt "tmp$1"
	mv -f "tmp$1" "$1"
}

doit()
{
	prefix="The Revolution-Part0"
	combined="combined_revolution"
	append_mp3 "$combined.mp3" "${prefix}1.mp3" "${prefix}2.mp3" "${prefix}3.mp3" "${prefix}4.mp3" "${prefix}5.mp3"
	rm -f "$combined.m4a"
	ffmpeg -i "$combined.mp3" -ab 80k "$combined.m4a"
	rm -f "$combined.mp3"

	strip_mpeg_tags "$combined.m4a"

	add_chapters "$combined.m4a" "chapters.txt"

	AtomicParsley "$combined.m4a" --artist "Ron Paul" --title "The Revolution: A Manifesto" --genre "Audiobooks" --artwork cover.png

	# copy temp m4a from AtomicParsley
	mv "$combined"-*.m4a "Ron Paul - The Revolution.m4b"
	# delete source m4a
	rm -f "$combined.m4a"

}

#doit
