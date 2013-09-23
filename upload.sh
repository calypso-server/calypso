#!/bin/sh

set -e

VERSION=`python ./calypso.py --version`

(cd ../build-area && dput calypso_$VERSION_*.changes)

scp ../calypso-$VERSION.tar.gz keithp.com:/var/www/calypso
