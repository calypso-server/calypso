#!/bin/sh

set -e

git checkout debian

VERSION=`python ./calypso.py --version`

git-buildpackage --git-debian-branch=debian

git archive --format=tar.gz -o ../calypso-$VERSION.tar.gz $VERSION
