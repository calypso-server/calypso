#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# This file is part of Calypso - CalDAV/CardDAV/WebDAV Server
# Copyright © 2011 Keith Packard
# Copyright © 2008-2011 Guillaume Ayoub
# Copyright © 2008 Nicolas Kandel
# Copyright © 2008 Pascal Halter
#
# This library is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Calypso.  If not, see <http://www.gnu.org/licenses/>.

# This file is just a script, allow [a-z0-9]* variable names
# pylint: disable-msg=C0103

# ``import calypso`` refers to the ``calypso`` module, not ``calypso.py`` 
# pylint: disable-msg=W0406

"""
Calypso Server entry point.

Launch the Calypso Server according to configuration and command-line
arguments.

"""

# TODO: Manage smart and configurable logs

import daemon
import lockfile
import logging
import optparse
import os
import sys

import calypso
import calypso.webdav as webdav

# Get command-line options
parser = optparse.OptionParser(version=calypso.VERSION)
parser.add_option(
    "-d", "--daemon", action="store_true",
    default=calypso.config.getboolean("server", "daemon"),
    help="launch as daemon")
parser.add_option(
    "-f", "--foreground", action="store_false", dest="daemon",
    help="launch in foreground (opposite of --daemon)")
parser.add_option(
    "-H", "--host",
    default=calypso.config.get("server", "host"),
    help="set server hostname")
parser.add_option(
    "-p", "--port", type="int",
    default=calypso.config.getint("server", "port"),
    help="set server port")
parser.add_option(
    "-s", "--ssl", action="store_true",
    default=calypso.config.getboolean("server", "ssl"),
    help="use SSL connection")
parser.add_option(
    "-S", "--no-ssl", action="store_false", dest="ssl",
    help="do not use SSL connection (opposite of --ssl)")
parser.add_option(
    "-k", "--key",
    default=calypso.config.get("server", "key"),
    help="private key file ")
parser.add_option(
    "-c", "--certificate",
    default=calypso.config.get("server", "certificate"),
    help="certificate file ")
parser.add_option(
    "-i", "--import", dest="import_dest")
parser.add_option(
    "-g", "--debug", action="store_true",
    default=False,
    help="enable debug logging")
parser.add_option(
    "-P", "--pid-file", dest="pidfile",
    default=calypso.config.get("server", "pidfile"),
    help="set location of process-id file")
    
(options, args) = parser.parse_args()

# Update Calypso configuration according to options
for option in parser.option_list:
    key = option.dest
    if key:
        value = getattr(options, key)
        calypso.config.set("server", key, value)

log = logging.getLogger()
ch = logging.StreamHandler()

# Handle debugging option and log levels
if options.debug:
    log.setLevel(logging.DEBUG)
    ch.setLevel(logging.DEBUG)
    logging.basicConfig(level=logging.DEBUG)
    log.debug("enable debugging")
else:
    log.setLevel(logging.WARN)
    ch.setLevel(logging.WARN)
    logging.basicConfig(level=logging.WARN)
    

# Run import if requested
if options.import_dest:
    try:
        collection = webdav.Collection(options.import_dest)
    except Exception:
        log.error("Cannot open collection %s" % options.import_dest)
        sys.exit(1)
    success = True
    for arg in args:
        if not collection.import_file(arg):
            success = False
    if success:
        sys.exit(0)
    else:
        sys.exit(1)

def run_server():
    try:
        # Launch server
        log.debug("Starting HTTP%s server on %s:%d" % ("S" if options.ssl else "",
                                                       options.host if options.host else "*",
                                                       options.port))
        server_class = calypso.HTTPSServer if options.ssl else calypso.HTTPServer
        server = server_class(
            (options.host, options.port), calypso.CollectionHTTPHandler)
        server.serve_forever(poll_interval=10)
    except KeyboardInterrupt:
        server.socket.close()

# If foreground execution is requested, just run the server
if not options.daemon:
    run_server()
    sys.exit(0)

# Otherwise, daemonize Calypso
context = daemon.DaemonContext()
context.umask = 0o002
if options.pidfile:
    from lockfile import pidlockfile
    # Generate a pidfile where requested
    context.pidfile = pidlockfile.PIDLockFile(options.pidfile)
with context:
    run_server()

# vim: set ts=4 sw=4 et si :
