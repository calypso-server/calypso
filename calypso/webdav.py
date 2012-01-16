# -*- coding: utf-8 -*-
#
# This file is part of Calypso - CalDAV/CardDAV/WebDAV Server
# Copyright © 2008-2011 Guillaume Ayoub
# Copyright © 2008 Nicolas Kandel
# Copyright © 2008 Pascal Halter
# Copyright © 2011 Keith Packard
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
Calypso collection classes.

Define the main classes of a collection as seen from the server.

"""

import os
import codecs
import time
import calendar
import hashlib
import glob
import logging
import tempfile
import vobject
import string
import re
import logging

from . import config

log = logging.getLogger()

#
# Recursive search for 'name' within 'vobject'
#

def find_vobject_value(vobject, name):

    if vobject.name == name:
        return vobject.value

    for child in vobject.getChildren():
        value = find_vobject_value(child, name)
        if value:
            return value
    return None

class Item(object):

    """Internal item. Wraps a vObject"""

    def __init__(self, text, name=None, path=None):
        """Initialize object from ``text`` and different ``kwargs``."""

        try:
            text = text.encode('utf8')
        except UnicodeDecodeError:
            text = text.decode('latin1').encode('utf-8')

        # Strip out control characters

        text = re.sub(r"[\x01-\x09\x0b-\x1F\x7F]","",text)

        try:
            self.object = vobject.readOne(text)
        except Exception:
            self.log.exception("Parse error in %s %s", name, path)
            raise


        if not self.object.contents.has_key('x-calypso-name'):
            if not name:
                if self.object.name == 'VCARD' or self.object.name == 'VEVENT':
                    if not self.object.contents.has_key('uid'):
                        self.object.add('UID').value = hashlib.sha1(text).hexdigest()
                    name = self.object.uid.value
                else:
                    for child in self.object.getChildren():
                        if child.name == 'VEVENT' or child.name == 'VCARD':
                            if not child.contents.has_key('uid'):
                                child.add('UID').value = hashlib.sha1(text).hexdigest()
                            name = child.uid.value
                            break
                    if not name:
                        name = hashlib.sha1(text).hexdigest()
                
            self.object.add("X-CALYPSO-NAME").value = name
        else:
            names = self.object.contents[u'x-calypso-name']
            if len(names) > 1:
                self.object.contents[u'x-calypso-name'] = [names[0]]

        self.path = path
        self.name = self.object.x_calypso_name.value
        self.tag = self.object.name
        self.etag = hashlib.sha1(text).hexdigest()

    @property
    def text(self):
        """Item text.

        Text is the serialized form of the item.

        """
        return self.object.serialize().decode('utf-8')

    @property
    def length(self):
        return "%d" % len(self.text)

    @property
    def last_modified(self):
        value = find_vobject_value(self.object, "LAST-MODIFIED")
        if value:
            return value.utctimetuple()
        return time.gmtime()

class Pathtime(object):
    """Path name and timestamps"""

    def __init__(self, path):
    	self.path = path
        self.mtime = self.curmtime

    @property
    def curmtime(self):
        return os.path.getmtime(self.path)

    def is_up_to_date(self):
        newmtime = self.curmtime
        if newmtime == self.mtime:
            return True
        self.mtime = newmtime
        return False

class Collection(object):
    """Internal collection class."""

    def read_file(self, path):
        text = codecs.open(path,encoding='utf-8').read()
        item = Item(text, None, path)
        return item

    def insert_file(self, path):
        try:
            item = self.read_file(path)
            self.my_items.append(item)
        except Exception, ex:
            self.log.exception("Insert %s failed", path)
            return

    def remove_file(self, path):
        old_items=[]
        for old_item in self.my_items:
            if old_item.path == path:
                old_items.append(old_item)
        for old_item in old_items:
            self.my_items.remove(old_item)
        
    def scan_file(self, path):
        self.remove_file(path)
        self.insert_file(path)

    def scan_dir(self):
        try:
            mtime = os.path.getmtime(self.path)
            if mtime == self.mtime:
                return
        except OSError:
            return
        self.log.debug("Scan %s", self.path)
        self.mtime = mtime
        filenames = glob.glob(self.pattern)
        newfiles = []
        for filename in filenames:
            for file in self.files:
                if filename == file.path:
                    newfiles.append(file)
                    if not file.is_up_to_date():
                        self.log.debug("Changed %s", filename)
                        self.scan_file(filename)
                    break
            else:
                self.log.debug("New %s", filename)
                newfiles.append(Pathtime(filename))
                self.insert_file(filename)
        for file in self.files:
            if not file.path in filenames:
                self.log.debug("Removed %s", file.path)
                self.remove_file(file.path)
        h = hashlib.sha1()
        for item in self.my_items:
            h.update(item.etag)
        self._ctag = '%d-' % self.mtime + h.hexdigest()
        self.files = newfiles
                
    def __init__(self, path):
        """Initialize the collection with ``cal`` and ``user`` parameters."""
        
        self.log = logging.getLogger(__name__)
        folder = os.path.expanduser(config.get("storage", "folder"))

        self.encoding = "utf-8"
        self.owner = path.split("/")[0]
        self.path = os.path.join(folder, path.replace("/", os.path.sep))
        self.pattern = os.path.join(self.path, "*")
        self.files = []
        self.my_items = []
        self.mtime = 0
        self._ctag = ''
        self.etag = hashlib.sha1(self.path).hexdigest()
        self.scan_dir()
        self.tag = "Collection"

    def __str__(self):
        return "Calendar-%s (at %s)" % (self.name, self.path)

    def __repr__(self):
        return "<Calendar %s>" % (self.name)
        
    def has_git(self):
        return os.path.exists(os.path.join(self.path, ".git"))

    def git_add(self, path):
        if self.has_git():
            command="cd %s && git add %s && git commit -m'Add %s'" % (self.path, os.path.basename(path), "new file")
            os.system(command)
    
    def git_rm(self, path):
        if self.has_git():
            command="cd %s && git rm %s && git commit -m'Remove %s'" % (self.path, os.path.basename(path), "old file")
            os.system(command)

    def git_change(self, path):
        if self.has_git():
            command="cd %s && git add %s && git commit -m'Change %s'" % (self.path, os.path.basename(path), "modified file")
            os.system(command)
            # Touch directory so that another running instance will update
            try:
                os.utime(self.path, None)
            except Exception, ex:
                self.log.exception("Failed to set directory mtime")
            
    def write_file(self, item):
        fd, path = tempfile.mkstemp(suffix=".ics", prefix="cal", dir=self.path)
        self.log.debug('Trying to write to %s', path)
        file = os.fdopen(fd, 'w')
        file.write(item.text.encode('utf-8'))
        file.close()
        self.log.debug('Wrote %s to %s', file, path)
        return path

    def create_file(self, item):
        # Create directory if necessary
        self.log.debug("Add %s", item.name)
        if not os.path.exists(os.path.dirname(self.path)):
            try:
                os.makedirs(os.path.dirname(self.path))
            except OSError, ose:
                self.log.exception("Failed to make collection directory %s: %s", self.path, ose)
                return

        try:
            path = self.write_file(item)
            self.scan_file(path)
            self.git_add(path)
            self.scan_dir()
        except OSError, ex:
            self.log.exception("Error writing file")
        except Exception, ex:
            self.log.exception("Caught Exception")
            self.log.debug("Failed to create %s: %s", path,  ex)

    def destroy_file(self, item):
        self.log.debug("Remove %s", item.name)
        try:
            os.unlink(item.path)
            self.git_rm(item.path)
            self.scan_dir()
        except Exception, ex:
            self.log.exception("Failed to remove %s", item.path)

    def rewrite_file(self, item):
        self.log.debug("Change %s", item.name)
        try:
            new_path = self.write_file(item)
            os.rename(new_path, item.path)
            self.scan_file(item.path)
            self.git_change(item.path)
            self.scan_dir()
        except Exception, ex:
            self.log.exception("Failed to rewrite %s", item.path)
        
    def get_item(self, name):
        """Get collection item called ``name``."""
        for item in self.my_items:
            if item.name == name:
                return item
        return None

    def get_items(self, name):
        """Get collection items called ``name``."""
        items=[]
        for item in self.my_items:
            if item.name == name:
                items.append(item)
        return items

    def append(self, name, text):
        """Append items from ``text`` to collection.

        If ``name`` is given, give this name to new items in ``text``.

        """

        try:
            new_item = Item(text, name, None)
        except Exception, e:
            self.log.exception("Cannot create new item")
            return False
        if new_item.name not in (item.name for item in self.my_items):
            self.log.debug("New item %s", new_item.name)
            self.create_file(new_item)
            return True
        self.log.debug("Item %s already present %s" , new_item.name, self.get_item(new_item.name).path)
        return False

    def remove(self, name):
        """Remove object named ``name`` from collection."""
        self.log.debug("Remove object %s", name)
        for old_item in self.my_items:
            if old_item.name == name:
                self.destroy_file(old_item)
                
    def replace(self, name, text):
        """Replace content by ``text`` in objet named ``name`` in collection."""

        path=None
        old_item = self.get_item(name)
        if old_item:
            path = old_item.path

        try:
            new_item = Item(text, name, path)
        except Exception:
            self.log.exception("Failed to replace %s", name)
            return

        if path is not None:
            self.rewrite_file(new_item)
        else:
            self.remove(name)
            self.append(name, text)

    def import_file(self, path):
        """Merge items from ``path`` to collection.
        """

        try:
            new_item = self.read_file(path)
            old_item = self.get_item(new_item.name)
            if old_item:
                new_item.path = old_item.path
                self.rewrite_file(new_item)
                self.log.debug("Updated %s from %s", new_item.name, path)
            else:
                self.create_file(new_item)
                self.log.debug("Added %s from %s", new_item.name, path)
        except Exception, ex:
            self.log.exception("Failed to import: %s", path)
            return False
        return True
        
    def write(self, headers=None, items=None):
        return True

    @property
    def ctag(self):
        self.scan_dir()
        """Ctag from collection."""
        return self._ctag

    @property
    def name(self):
        """Collection name."""
        return self.path.split(os.path.sep)[-1]

    @property
    def text(self):
        """Collection as plain text."""
        self.scan_dir()
        _text = ""
        for item in self.my_items:
            _text = _text + item.text
        return _text

    @property
    def headers(self):
        """Find headers items in collection."""
        return []

    @property
    def items(self):
        """Get list of all items in collection."""
        self.scan_dir()
        return self.my_items

    @property
    def last_modified(self):
        """Get the last time the collection has been modified.

        The date is formatted according to rfc1123-5.2.14.

        """
        self.scan_dir()
        return time.gmtime(self.mtime)

    @property
    def length(self):
        return "%d" % len(self.text)
