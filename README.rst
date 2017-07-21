radiocut2podcast
================

RadioCut is an awesome service, please consider support them by `buying a
premium suscription <http://radiocut.fm/premium/>`_.


Generic syntax
--------------

::

    rc2pc.py [--since][--quiet] pc_dir history_file config_file

where:

- ``--quiet`` (optional): only show anything if warning/error

- ``--since`` (optional): is a timestamp in the format YYYY-MM-DD for
  the program to get stuff from that when

- ``pc_dir``: is the directory where the podcast stuff will be dump

- ``history_file``: where the timestamp of last run is stored

- ``config_file``: is a yaml with all the proper shows info (see below)

If ``--since`` is given, program will get shows from there and save the
timestamp in the indicated ``history_file``. To avoid mistakes, if ``--since``
is given and the history file exists, it will error out. Of course, the
history file needs to be present if no ``--since`` is indicated.


How to use
----------

First / eventual manual call::

    rc2pc.py --since=2017-05-23 ./podcast/ rc2pc.hist rc2pc.yaml

Something to put in the crontab::

    rc2pc.py --quiet ./podcast/ rc2pc.hist rc2pc.yaml
