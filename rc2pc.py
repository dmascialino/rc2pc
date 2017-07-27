#!/usr/bin/env python

import argparse
import datetime
import glob
import os
import subprocess

import bunch
import croniter
import dateutil.parser
import dateutil.tz
import pytz
import yaml
from feedgen.feed import FeedGenerator


# TODO:
# - read the yaml from disk (given in command line)
# - add an mp3 tag to the generated files (??)
# - support logging (with --quiet)
# - support receiving the podcast dir
# - put the BASE_PUBLIC_URL as part of the config


BASE_PUBLIC_URL = "http://localhost:8000/"


RADIOCUT_CMD = (
    'radiocut http://radiocut.fm/radiostation/{station}/listen/{dt:%Y/%m/%d/%H/%M/%S}/ '
    '"{fname}" --duration={duration}'
)


# how many minutes will get from the show before the regular start and after the regular end,
# so we don't miss anything if the show didn't respect exactly its schedule
BORDER_DELTA = datetime.timedelta(minutes=3)


SHOWS = """
gentedeapie:
    name: La vida en particular
    description: El programa de Wainfeld
    station: nacional870
    cron: "00   10    *     *     6"  # m h (local) dom mon dow
    timezone: America/Buenos_Aires
    duration: 10800  # 3hs in seconds
    author:
        name: RC
        email: dmascialino@gmail.com
"""


def download(show, start_datetime):
    """Download a given show at a specific hour."""
    # build the filename with the show id and the show hours
    fname = "{name}_{date:%Y-%m-%d}".format(date=start_datetime, name=show.id)

    # start to download a little before the show begins, and finish a little later
    dtime = start_datetime - BORDER_DELTA
    duration = show.duration + BORDER_DELTA.seconds * 2

    # build the command and download
    cmd = RADIOCUT_CMD.format(station=show.station, dt=dtime, duration=duration, fname=fname)
    print("Downloading show with cmd", repr(cmd))
    subprocess.run(cmd, shell=True, check=True)


def get_episodes(show, last_process):
    """Get episodes for a given show."""
    # get a timezone for the show, and a "now" for that timezone
    showlocal_tz = pytz.timezone(show.timezone)
    utc_now = datetime.datetime.now(dateutil.tz.tzutc())
    showlocal_now = utc_now.astimezone(showlocal_tz)

    from_cron = croniter.croniter(show.cron, last_process)
    while True:
        next_date = from_cron.get_next(datetime.datetime)
        showlocal_next_date = showlocal_tz.localize(next_date)
        print("Checking next date", showlocal_next_date)
        if showlocal_next_date > showlocal_now:
            print("Next date is after now, quit")
            break

        if showlocal_next_date + datetime.timedelta(seconds=show.duration) > showlocal_now:
            print("Show currently in the air, quit")
            break

        print("Downloading")
        download(show, showlocal_next_date)
        last_process = showlocal_next_date

    write_podcast(show)
    return last_process


def write_podcast(show):
    """Create the podcast file."""
    fg = FeedGenerator()
    fg.load_extension('podcast')

    url = "{}{}.xml".format(BASE_PUBLIC_URL, show.id)
    fg.id(url.split('.')[0])
    fg.title(show.name)
    fg.author(show.author)
    fg.description(show.description)
    fg.link(href=url, rel='self')

    # collect all mp3s for the given show
    all_mp3s = glob.glob("{}_*.mp3".format(show.id))

    for fname in all_mp3s:
        fe = fg.add_entry()
        fe.id(url.split('.')[0])
        fe.title(fname.split('.')[0])
        fe.enclosure('{}{}'.format(BASE_PUBLIC_URL, fname), 0, 'audio/mpeg')

    fg.rss_str(pretty=True)
    fg.rss_file('{}.xml'.format(show.id))


class HistoryFile:
    """Manage the history file."""
    def __init__(self, history_file):
        self.history_file = history_file

        # (try to) open it
        if os.path.exists(history_file):
            with open(history_file, 'rt', encoding='utf8') as fh:
                self.data = data = {}
                for line in fh:
                    show_id, last_timestamp = line.strip().split()
                    data[show_id] = dateutil.parser.parse(last_timestamp)
        else:
            self.data = {}

    def get(self, show_id):
        """Get the last process for given show_id (if any)."""
        return self.data.get(show_id)

    def _save(self):
        """Save the content to disk."""
        temp_path = self.history_file + ".temp"
        with open(temp_path, 'wt', encoding='utf8') as fh:
            for show_id, last_time in sorted(self.data.items()):
                fh.write("{} {}\n".format(show_id, last_time.isoformat()))

        os.rename(temp_path, self.history_file)

    def set(self, show_id, last_run):
        """Set the last process for the given show_id to 'now' and save."""
        self.data[show_id] = last_run
        self._save()


def main(history_file_path, since=None, selected_show=None):
    """Main entry point."""
    # open the history file
    history_file = HistoryFile(history_file_path)

    # open the config file
    # FIXME: handle a real file here!!
    # FIXME: validate format!!
    config_data = []
    from_config_file = yaml.load(SHOWS)
    for show_id, show_data in from_config_file.items():
        if not show_id.isalnum():
            print("Bad format for show id (must be alphanumerical)", repr(show_id))
            exit()

        if selected_show is not None and selected_show != show_id:
            print("Ignoring config because not selected show:", repr(show_id))
            continue

        config_data.append(bunch.Bunch(show_data, id=show_id))
    print("Loaded config for shows", sorted(x.id for x in config_data))

    for show_data in config_data:
        print("Processing show", show_data.id)
        last_process = history_file.get(show_data.id)
        print("  last process: ", last_process)
        if since is not None:
            last_process = since
            print("  overridden by:", last_process)
        if last_process is None:
            print("ERROR: Must indicate a start point in time "
                  "(through history file or --since parameter")
            exit()
        last_run = get_episodes(show_data, last_process)
        history_file.set(show_id, last_run)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--since', help="A date (YYYY-MM--DD) to get stuff since.")
    parser.add_argument('--show', help="Work with this show only.")
    parser.add_argument('history_file', metavar='history-file', help="The file to store last run")
    args = parser.parse_args()

    # parse input
    since = None if args.since is None else dateutil.parser.parse(args.since)

    main(args.history_file, since, args.show)
