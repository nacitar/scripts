#!/usr/bin/env python3

import subprocess

import util

class MP3Meta(object):
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
        channels = None
        comments = {}
        pictures = {}
        info = util.sox_info(filename)
        sample_rate = info['Sample Rate']
        total_samples = info['Total Samples']
        channels = info['Channels']
        # TODO: tags and stuff
        return MP3Meta(sample_rate, total_samples, channels, comments, pictures)

def strip_all_metadata(input_filename, output_filename):
    retval = False
    with open(input_filename, 'rb') as infile, open(output_filename, 'wb') as outfile:
        child = subprocess.Popen(['extract_frames', '--noinfo'],
                stdin=infile, stdout = outfile, stderr = subprocess.DEVNULL)
        retval = (child.wait() == 0)
    return retval

