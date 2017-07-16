#!/usr/bin/env python

import datetime
import dateutil.parser
import glob
import os
import subprocess

import croniter
import yaml

from feedgen.feed import FeedGenerator

from slugify import slugify


# TODO:
# - Leer shows de un YAML
# - Agregar mp3 tag a los archivos generados.


DIR_PATH = os.path.dirname(os.path.realpath(__file__))

BASE_DIR = DIR_PATH

BASE_PUBLIC_URL = "http://localhost:8000/"


LAST_EXECUTED_PATH = os.path.join(BASE_DIR, 'last_executed_date')


CMD = 'radiocut  http://radiocut.fm/radiostation/{station}/listen/{dt:%Y/%m/%d/%H/%M/%S}/ "{fname}" --duration={duration}'


DELTA = datetime.timedelta(minutes=5)

# m h  dom mon dow
SHOWS = [
    {'name': 'La vida en particular',
     'station': 'nacional870',
     'cron': '00     10      *       *       6',
     'duration_s': 3*60*60,
     'author': {'name': 'RC', 'email': 'dmascialino@gmail.com'},
     'description': 'Programa de los Sábados',
     }
]


def read_last_executed_date():
    try:
        fh = open(LAST_EXECUTED_PATH)
    except FileNotFoundError:
        fh = None

    if fh:
        date = dateutil.parser.parse(fh.read())
        fh.close()
    else:
        date = datetime.datetime.today() - datetime.timedelta(days=28)

    print("Readed date: %r" % date)
    return date


def save_last_executed_date():
    with open(LAST_EXECUTED_PATH, 'w') as fh:
        fh.write(datetime.date.today().isoformat())


def downloader_cmd(show, start_datetime):
    fname = "{name}_{date:%Y-%m-%d}.mp3".format(date=start_datetime, name=show['name'])
    dtime = start_datetime - DELTA
    duration = show['duration_s'] + DELTA.seconds * 2
    cmd = CMD.format(station=show['station'], dt=dtime, duration=duration, fname=fname)
    print(cmd)
    subprocess.run(cmd, shell=True)


def get_episodes(show, start_date):
    now = datetime.datetime.now()
    it = croniter.croniter(show['cron'], start_date)
    date = it.get_next(datetime.datetime)
    while date < now:
        # que pasa si el show todavía esta al aire? (es decir start + duration >
        # now?)
        downloader_cmd(show, date)
        date = it.get_next(datetime.datetime)
    write_podcast(show)


def write_podcast(show):
    fg = FeedGenerator()
    fg.load_extension('podcast')

    slug = slugify(show['name'])
    url = "{}{}.xml".format(BASE_PUBLIC_URL, slug)
    fg.id(url.split('.')[0])
    fg.title(show['name'])
    fg.author(show.get('author'))
    fg.description(show.get('description'))
    fg.link(href=url, rel='self')

    for fname in glob.glob('*.mp3'):
        fe = fg.add_entry()
        fe.id(url.split('.')[0])
        fe.title(fname.split('.')[0])
        fe.enclosure('{}{}'.format(BASE_PUBLIC_URL, fname), 0, 'audio/mpeg')

    fg.rss_str(pretty=True)
    fg.rss_file('{}.xml'.format(slug))


get_episodes(SHOWS[0], read_last_executed_date())
save_last_executed_date()
