radiocut2podcast
================

RadioCut is an awesome service, please consider support them by `buying a
premium suscription <http://radiocut.fm/premium/>`_.


Generic syntax
--------------

::

    rc2pc.py [--since][--quiet][--show] pc_dir history_file config_file

where:

- ``--quiet`` (optional): only show anything if warning/error

- ``--since`` (optional): is a timestamp in the format YYYY-MM-DD for
  the program to get stuff from that when

- ``--show``: is the show id as specified in the config (otherwise it will
  work on all the shows from the config)

- ``pc_dir``: is the directory where the podcast stuff will be dump

- ``history_file``: where the timestamp of last run is stored

- ``config_file``: is a yaml with all the proper shows info (see below)

If ``--since`` is given, program will get shows from there and save the
timestamp in the indicated ``history_file``. The ``--since`` timestamp
overrides what is indicated in the history file.


Config file
-----------

The config file should be a YAML file with the show(s) information, each
show having an id and some info (and repeat everything for each show you
want to podcast)::

  show_id:
        name: The Show Name
        description: A description for the show
        station: the station name as appears in radiocut
        cron: a string with crontab info in "m h dom mon dow" format,
              indicating when the show starts
        timezone: the timezone used when writing the cron hours
        duration: the show duration (in seconds)
        author:
            name: the author name
            email: the author email

Example for one show::

    gentedeapie:
        name: La vida en particular
        description: Programa de los Sábados de Mario Wainfeld
        station: nacional870
        cron: "00   10    *     *     6"  # m h dom mon dow
        timezone: America/Buenos_Aires
        duration: 10800  # 3hs in seconds
        author:
            name: rc2pc
            email: rc2pc@nomail.com


How to use
----------

First / eventual manual call::

    rc2pc.py --since=2017-05-23 ./podcast/ rc2pc.hist rc2pc.yaml

Something to put in the crontab::

    rc2pc.py --quiet ./podcast/ rc2pc.hist rc2pc.yaml
