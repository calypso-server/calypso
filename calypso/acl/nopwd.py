# -*- coding: utf-8 -*-
#
# This file is part of Calypso Server - Calendar Server
# Copyright © 2016 Guido Günther <agx@sigxcpu.org>
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

"""
nopwd ACL.

only verify the user has access, ignore password
"""
import logging
from calypso import config

log = logging.getLogger()


def has_right(owner, user, password):
    """Check if ``user`` is valid."""
    log.debug("owner %s user %s", owner, user)
    if user == owner or not PERSONAL:
        return True
    return False

PERSONAL = config.getboolean("acl", "personal")
