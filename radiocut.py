"""radiocut.fm downloader

Usage:
  radiocut <audiocut_or_podcast> [<output-file-name>]
                        [--verbose] [--background=<path-to-image>] [--join] [--duration=<duration>]

Options:
  -h --help                         Show this screen.
  --background=<path-to-image>      If given, produce a video with this image as background
  --join                            Concatenate podcast's cuts as a single file
  --duration=<duration>             The length to download (in seconds)
"""

import base64
import re
import sys
import tempfile

import requests
from moviepy.editor import AudioFileClip, ImageClip, concatenate_audioclips
from pyquery import PyQuery

__version__ = '0.3'

AUDIOCUT_PATTERN = re.compile(r'https?://radiocut\.fm/audiocut/[-\w]+/?')
PODCAST_PATTERN = re.compile(r'https?://radiocut\.fm/pdc/[-\w]+/[-\w]+/?')
RADIOSTATION_PATTERN = re.compile(r'https?://radiocut\.fm/radiostation/.*')

NOT_VALID_MSG = """
The given URL is not a valid audiocut, podcast or timestamp from radiocut.fm.
Examples:
    - http://radiocut.fm/audiocut/macri-gato/
    - http://radiocut.fm/pdc/tin_nqn_/test
    - http://radiocut.fm/radiostation/nacional870/listen/2017/07/01/10/00/00/
"""

HEADERS_JSON = {
    'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:74.0) Gecko/20100101 Firefox/74.0',
}
HEADERS_MP3 = {
    'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:74.0) Gecko/20100101 Firefox/74.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
}


def get_chunks_url(base_url, station, start_folder):
    station = station.encode("ascii")
    start_folder = str(start_folder).encode("ascii")
    raw_token = b"andaa" + station + b"|" + start_folder + b"cagar"
    token = base64.b64encode(raw_token).decode("ascii")
    transformed = token.replace("=", "~").replace("+", "-").replace("/", "_")
    return "{}/server/gec/www/{}/".format(base_url, transformed)


def get_audiocut(url, verbose=False, duration=None):
    """
    Given an "audio cut" url, return a moviepy's AudioClip instance with the cut
    """

    if verbose:
        print('Retrieving {}'.format(url))

    pq = PyQuery(url)
    seconds = pq('li.audio_seconds').text()
    if duration is None:
        duration = float(pq('li.audio_duration').text())
    station = pq('li.audio_station').text()
    base_url = pq('li.audio_base_url').text()

    start_folder = int(seconds[:6])
    chunks = []

    while True:
        chunks_url = get_chunks_url(base_url, station, start_folder)
        if verbose:
            print('Getting chunks index {}'.format(chunks_url))
        chunks_json = requests.get(chunks_url, headers=HEADERS_JSON).json()[str(start_folder)]
        for chunk_data in chunks_json['chunks']:
            # set the base_url if isnt defined
            chunk_data['base_url'] = chunk_data.get('base_url', chunks_json['baseURL'])
            chunks.append(chunk_data)
        c = chunks[-1]
        if verbose:
            print("Deciding len! seconds={!r} duration={!r} c={}".format(seconds, duration, c))
        if c['start'] + c['length'] > float(seconds) + float(duration):
            break
        # if the last chunk isn't in this index, get the next one
        start_folder += 1

    if verbose:
        print("Retrieved {} chunks".format(len(chunks)))
        print('Looking for first chunk')
    for i, c in enumerate(chunks):
        if c['start'] + c['length'] > float(seconds):
            first_chunk = i
            break
    if verbose:
        print('    first:', first_chunk)
        print('Looking for last chunk')
    for i, c in enumerate(chunks[first_chunk:]):
        if c['start'] + c['length'] > float(seconds) + float(duration):
            last_chunk = min(len(chunks), first_chunk + i + 1)
            break
    if verbose:
        print('    last:', last_chunk)

    audios = [get_mp3(chunk, verbose=verbose) for chunk in chunks[first_chunk:last_chunk]]
    start_offset = float(seconds) - chunks[first_chunk]['start']
    cut = concatenate_audioclips(audios)
    return cut


def get_urls_from_podcast(url, verbose=False):
    """given the url to a podcast, return the list of urls to each audiocut"""
    pq = PyQuery(url)
    pq.make_links_absolute()
    return [PyQuery(a).attr('href') for a in pq('.cut_brief h4 a')]


def get_mp3(chunk, verbose=False):
    url = chunk['base_url'] + '/' + chunk['filename']
    _, temppath = tempfile.mkstemp('.mp3')
    if verbose:
        print('Downloading chunk {} to {}'.format(url, temppath))
    r = requests.get(url, stream=True, headers=HEADERS_MP3)
    if r.status_code == 200:
        with open(temppath, 'wb') as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
        return AudioFileClip(temppath)
    else:
        print('Error {} when trying to download chunk {}'.format(r.status_code, url))


def output_file_names(urls, given_filename=None, extension='mp3'):

    filenames = []
    for i, url in enumerate(urls):
        filename = given_filename or url.rstrip('/').split('/')[-1]
        if i and given_filename:
            filename = '{}_{}'.format(filename, i)
        filenames.append('{}.{}'.format(filename, extension))
    return filenames


def write_output(audio_clip, output_filename, background=None, verbose=False):
    if verbose:
        print("Storing clip {} to {} (background={})".format(
            audio_clip, output_filename, background))

    if not background:
        audio_clip.write_audiofile(
            output_filename,
            fps=16000,
            nbytes=2,
            bitrate='16k',
            verbose=verbose
        )
    else:
        clip = ImageClip(background, duration=audio_clip.duration)
        clip = clip.set_audio(audio_clip)
        clip.write_videofile(
            output_filename,
            fps=1,
            audio_fps=16000,
            audio_nbytes=2,
            audio_bitrate='16k',
            verbose=verbose
        )


def main():
    from docopt import docopt
    arguments = docopt(__doc__, version=__version__)

    url = arguments['<audiocut_or_podcast>'].partition('#')[0]
    is_audiocut = re.match(AUDIOCUT_PATTERN, url)
    is_podcast = re.match(PODCAST_PATTERN, url)
    is_radiostation = re.match(RADIOSTATION_PATTERN, url)
    if not any([is_audiocut, is_podcast, is_radiostation]):
        print(NOT_VALID_MSG)
        sys.exit(1)
    if is_audiocut and not url.endswith('/'):
        url += '/'
    verbose = bool(arguments['--verbose'])
    duration = arguments['--duration']
    if duration is not None:
        duration = int(duration)

    if is_podcast:
        urls = get_urls_from_podcast(url, verbose)
    else:
        urls = [url]

    audioclips = [get_audiocut(url, verbose, duration) for url in urls]
    background = arguments['--background']
    extension = 'mp4' if background else 'mp3'

    if arguments['--join'] or is_audiocut:
        if verbose:
            print("Joining clips")
        audioclips = [concatenate_audioclips(audioclips)]
        output_filenames = output_file_names(
            [url],
            given_filename=arguments['<output-file-name>'],
            extension=extension)
    else:
        output_filenames = output_file_names(
            urls,
            given_filename=arguments['<output-file-name>'],
            extension=extension)

    for clip, filename in zip(audioclips, output_filenames):
        write_output(clip, filename, background, verbose=verbose)


if __name__ == '__main__':
    main()
