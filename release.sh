#!/bin/sh

set -e

VERSION=`python ./calypso.py --version`

git-buildpackage --git-debian-branch=debian

git archive --format=tar.gz --prefix=calypso-$VERSION/ -o ../calypso-$VERSION.tar.gz master
