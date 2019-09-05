#!/usr/bin/env python

import argparse
import datetime
import glob
import logging
import os
import subprocess

import bunch
import croniter
import dateutil.parser
import pytz
import yaml
from feedgen.feed import FeedGenerator

logger = logging.getLogger()
h = logging.StreamHandler()
h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-10s %(message)s"))
logger.addHandler(h)
logger.setLevel(logging.INFO)


RADIOCUT_CMD = (
    'python3 radiocut.py --verbose http://radiocut.fm/radiostation/{station}/listen/{dt:%Y/%m/%d/%H/%M/%S}/ '
    '"{filepath}" --duration={duration}'
)


# how many minutes will get from the show before the regular start and after the regular end,
# so we don't miss anything if the show didn't respect exactly its schedule
BORDER_DELTA = datetime.timedelta(minutes=3)


def download(show, start_datetime, podcast_dir):
    """Download a given show at a specific hour."""
    # build the filename with the show id and the show hours
    fname = "{name}_{date:%Y-%m-%d}".format(date=start_datetime, name=show.id)
    filepath = os.path.join(podcast_dir, fname)

    # finish to download a little later, just in case the show extends
    dtime = start_datetime
    duration = show.duration + BORDER_DELTA.seconds

    # build the command and download
    cmd = RADIOCUT_CMD.format(station=show.station, dt=dtime, duration=duration, filepath=filepath)
    logger.info("Downloading show with cmd %r", cmd)
    subprocess.run(cmd, shell=True, check=True)


def get_episodes(show, last_process, podcast_dir, base_public_url):
    """Get episodes for a given show."""
    # get a timezone for the show, and a "now" for that timezone
    showlocal_tz = pytz.timezone(show.timezone)
    utc_now = pytz.utc.localize(datetime.datetime.utcnow())
    showlocal_now = utc_now.astimezone(showlocal_tz)

    if last_process.tzinfo is None:
        # need to localize
        last_process = showlocal_tz.localize(last_process)

    from_cron = croniter.croniter(show.cron, last_process)
    while True:
        next_date = from_cron.get_next(datetime.datetime)
        logger.info("Checking next date: %s", next_date)
        if next_date > showlocal_now:
            logger.info("Next date is after now, quit")
            break

        if next_date + datetime.timedelta(seconds=show.duration) > showlocal_now:
            logger.info("Show currently in the air, quit")
            break

        logger.info("Downloading")
        download(show, next_date, podcast_dir)
        last_process = next_date

    write_podcast(show, podcast_dir, base_public_url, showlocal_tz)
    return last_process


def _get_date_from_mp3_path(filepath, showlocal_tz):
    """Parse the mp3 filepath (which we build) and retrieve the date."""
    date_str = os.path.basename(filepath).split(".")[0].split("_")[-1]
    date = dateutil.parser.parse(date_str)
    return showlocal_tz.localize(date)


def write_podcast(show, podcast_dir, base_public_url, showlocal_tz):
    """Create the podcast file."""
    fg = FeedGenerator()
    fg.load_extension('podcast')

    url = "{}{}.xml".format(base_public_url, show.id)
    fg.id(url.split('.')[0])
    fg.title(show.name)
    fg.image(show.image_url)
    fg.description(show.description)
    fg.link(href=url, rel='self')

    # collect all mp3s for the given show
    all_mp3s = glob.glob(os.path.join(podcast_dir, "{}_*.mp3".format(show.id)))

    for filepath in all_mp3s:
        filename = os.path.basename(filepath)
        mp3_date = _get_date_from_mp3_path(filepath, showlocal_tz)
        mp3_size = os.stat(filepath).st_size
        mp3_url = base_public_url + filename
        mp3_id = filename.split('.')[0]
        title = "Programa del {0:%d}/{0:%m}/{0:%Y}".format(mp3_date)

        # build the rss entry
        fe = fg.add_entry()
        fe.id(mp3_id)
        fe.pubdate(mp3_date)
        fe.title(title)
        fe.enclosure(mp3_url, str(mp3_size), 'audio/mpeg')

    fg.rss_str(pretty=True)
    fg.rss_file(os.path.join(podcast_dir, '{}.xml'.format(show.id)))


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


def load_config(config_file_path, selected_show):
    """Load the configuration file and validate format."""
    with open(config_file_path, 'rt', encoding='utf8') as fh:
        from_config_file = yaml.load(fh)

    if not isinstance(from_config_file, dict):
        raise ValueError("Bad general config format, must be a dict/map.")

    base_keys = {'name', 'description', 'station', 'cron', 'timezone', 'duration', 'image_url'}

    config_data = []
    for show_id, show_data in from_config_file.items():
        if not show_id.isalnum():
            raise ValueError(
                "Bad format for show id {!r} (must be alphanumerical)".format(show_id))

        if selected_show is not None and selected_show != show_id:
            logger.warning("Ignoring config because not selected show: %r", show_id)
            continue

        missing = base_keys - set(show_data)
        if missing:
            raise ValueError("Missing keys {} for show id {}".format(missing, show_id))

        config_data.append(bunch.Bunch(show_data, id=show_id))

    return config_data


def main(history_file_path, podcast_dir, config_file_path, base_public_url,
         since=None, selected_show=None):
    """Main entry point."""
    # open the history file
    history_file = HistoryFile(history_file_path)

    # open the config file
    try:
        config_data = load_config(config_file_path, selected_show)
    except ValueError as exc:
        logger.error("Problem loading config: %s", exc)
        exit()

    logger.info("Loaded config for shows %s", sorted(x.id for x in config_data))

    for show_data in config_data:
        logger.info("Processing show %s", show_data.id)
        last_process = history_file.get(show_data.id)
        logger.info("  last process: %s", last_process)
        if since is not None:
            last_process = since
            logger.info("  overridden by: %s", last_process)
        if last_process is None:
            logger.error("Parameters problem: Must indicate a start point in time "
                         "(through history file or --since parameter")
            exit()
        last_run = get_episodes(show_data, last_process, podcast_dir, base_public_url)
        history_file.set(show_data.id, last_run)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--since', help="A date (YYYY-MM--DD) to get stuff since.")
    parser.add_argument('--show', help="Work with this show only.")
    parser.add_argument('--quiet', action='store_true', help="Be quiet, unless any issue is found")
    parser.add_argument('podcast_dir', help="The directory where podcast files will be stored")
    parser.add_argument('history_file', help="The file to store last run")
    parser.add_argument('config_file', help="The configuration file")
    parser.add_argument('base_public_url', help="The public URL from where the podcast is served")
    args = parser.parse_args()

    # parse input
    since = None if args.since is None else dateutil.parser.parse(args.since)
    if args.quiet:
        logger.setLevel(logging.WARNING)

    main(args.history_file, args.podcast_dir, args.config_file, args.base_public_url,
         since, args.show)
