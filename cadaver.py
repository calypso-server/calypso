#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# This file is part of Cadaver Server - Calendar Server
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
# along with Cadaver.  If not, see <http://www.gnu.org/licenses/>.

# This file is just a script, allow [a-z0-9]* variable names
# pylint: disable-msg=C0103

# ``import cadaver`` refers to the ``cadaver`` module, not ``cadaver.py`` 
# pylint: disable-msg=W0406

"""
Cadaver Server entry point.

Launch the Cadaver Server according to configuration and command-line
arguments.

"""

# TODO: Manage smart and configurable logs

import os
import sys
import optparse

import cadaver

# Get command-line options
parser = optparse.OptionParser()
parser.add_option(
    "-v", "--version", action="store_true",
    default=False,
    help="show version and exit")
parser.add_option(
    "-d", "--daemon", action="store_true",
    default=cadaver.config.getboolean("server", "daemon"),
    help="launch as daemon")
parser.add_option(
    "-f", "--foreground", action="store_false", dest="daemon",
    help="launch in foreground (opposite of --daemon)")
parser.add_option(
    "-H", "--host",
    default=cadaver.config.get("server", "host"),
    help="set server hostname")
parser.add_option(
    "-p", "--port", type="int",
    default=cadaver.config.getint("server", "port"),
    help="set server port")
parser.add_option(
    "-s", "--ssl", action="store_true",
    default=cadaver.config.getboolean("server", "ssl"),
    help="use SSL connection")
parser.add_option(
    "-S", "--no-ssl", action="store_false", dest="ssl",
    help="do not use SSL connection (opposite of --ssl)")
parser.add_option(
    "-k", "--key",
    default=cadaver.config.get("server", "key"),
    help="private key file ")
parser.add_option(
    "-c", "--certificate",
    default=cadaver.config.get("server", "certificate"),
    help="certificate file ")
options = parser.parse_args()[0]

# Update Cadaver configuration according to options
for option in parser.option_list:
    key = option.dest
    if key:
        value = getattr(options, key)
        cadaver.config.set("server", key, value)

# Print version and exit if the option is given
if options.version:
    print(cadaver.VERSION)
    sys.exit()

# Fork if Cadaver is launched as daemon
if options.daemon:
    if os.fork():
        sys.exit()
    sys.stdout = sys.stderr = open(os.devnull, "w")

# Launch calendar server
server_class = cadaver.HTTPSServer if options.ssl else cadaver.HTTPServer
server = server_class(
    (options.host, options.port), cadaver.CalendarHTTPHandler)
server.serve_forever()
