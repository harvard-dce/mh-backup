mh-backup
=========

scripts to clone mh shared-storage in zadara vpsa
see:
    * http://vpsa-api.zadarastorage.com/
    * https://bitbucket.org/opencast-community/matterhorn


* Free software: Apache license
* Github: https://github.com/harvard-dce/mh-backup


overview
--------

the script clones a volume base on a given snapshot, changes the export path of the cloned
volume to be the same as the source volume, and attaches the same snapshot policies to the
cloned volume as the source volume.

set values for the zadara cloud console url and the export path of the volume to be cloned
in the config.yml file

the script will ask for the zadara cloud console token and the vpsa token (the vpsa where
the volume you want to clone is located) or you can define them in the enviroment like
below:

    export ZADARA_CONSOLE_ACCESS_TOKEN="CLEARLY123FAKE456TOKEN"
    export ZADARA_VPSA_ACCESS_TOKEN="ANOTHER789FAKE012TOKEN"


requirements
------------

    * access token for zadara cloud console
    * access token for zadara vpsa
    * export path of volume to be cloned
    * the script assumes no one is mounting the export path

usage
-----

    $> git clone git@github.com:harvard-dce/mh-backup.git
    $> cd mh-backup
    $> ./clone-zadara-volume.py


license
-------

apache 2.0


contributors
------------

* nmaekawa \<<nmaekawa@g.harvard.edu>\> [@nmaekawa](http://github.com/nmaekawa), maintainer


copyright
---------

2015-2016 President and Fellows of Harvard College



