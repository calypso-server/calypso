# -*- coding: utf-8 -*-
#
# This file is part of Calypso Server - Calendar Server
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
Calypso calendar classes.

Define the main classes of a calendar as seen from the server.

"""

import os
import codecs
import time
import calendar
import hashlib
import glob
import tempfile
import vobject

from calypso import config

FOLDER = os.path.expanduser(config.get("storage", "folder"))
    

# This function overrides the builtin ``open`` function for this module
# pylint: disable=W0622
def open(path, mode="r"):
    """Open file at ``path`` with ``mode``, automagically managing encoding."""
    return codecs.open(path, mode, config.get("encoding", "stock"))
# pylint: enable=W0622

class Item(object):
    """Internal iCal item."""
    def __init__(self, text, name=None, path=None):
        """Initialize object from ``text`` and different ``kwargs``."""

        print ("New item name %s path %s\n" % (name, path))

        lines = text.splitlines(True)
        newlines=""
        for line in lines:
            if line.find(":") >= 0:
                newlines = newlines + line

        try:
            self.object = vobject.readOne(newlines)
        except Exception:
            self.object = None
            print ("parse error\n")

        self.path = path

        h = hashlib.sha1(self.object.serialize())
        self.etag = h.hexdigest()

        for child in self.object.getChildren():
            if child.name == 'VEVENT' or child.name == 'VCARD':
                if child.contents.has_key('uid'):
                    if name:
                        child.uid.value = name
                    self.name = child.uid.value
                else:
                    if not name:
                        name = self.etag
                    child.add('UID').value = name
                    self.name = name
                break
        print ("uid %s\n" % self.name)


    @property
    def text(self):
        """Item text.

        Text is the serialized form of the item.

        """
        return self.object.serialize()

    @property
    def is_event(self):
        """Item events

        Events are vevent objects within the item.

        """
        return self.object.contents.has_key('vevent')
        
    @property
    def is_todo(self):
        """Item todos

        Todos are vtodo objects within the item.

        """
        return self.object.contents.has_key('vtodo')

    @property
    def tzs(self):
        """Item tzs

        Todos are tzid objects within the item.

        """
        if self.object.contents.has_key('tzid'):
            return self.object.tzid_list
        return []

class Calendar(object):
    """Internal calendar class."""
    tag = "VCALENDAR"

    def insert_text(self, text, path):
        new_item = Item(text, None, path)
        self.my_items.append(new_item)
            
    def insert_file(self, path):
        try:
            print ("Insert file %s" % path)
            text = open(path).read()
            self.insert_text(text, path)
        except IOError:
            return

    def remove_file(self, path):
        print ("Remove file %s" % path)
        old_items=[]
        for old_item in self.my_items:
            if old_item.path == path:
                old_items.append(old_item)
                
        for old_item in old_items:
            self.my_items.remove(old_item)
        
    def scan_file(self, path):
        print ("Rescan file %s" % path)
        self.remove_file(path)
        self.insert_file(path)

    def scan_dir(self):
        try:
            mtime = os.path.getmtime(self.path)
            if mtime == self.mtime:
                return
        except OSError:
            return
        self.mtime = mtime
        files = glob.glob(self.pattern)
        for file in files:
            if not file in self.files:
                self.insert_file(file)
        for file in self.files:
            if not file in files:
                self.remove_file(file)
        self.files = files
                
    def __init__(self, path):
        """Initialize the calendar with ``cal`` and ``user`` parameters."""
        print ("New calendar %s" % path)
        
        self.encoding = "utf-8"
        self.owner = path.split("/")[0]
        self.path = os.path.join(FOLDER, path.replace("/", os.path.sep))
        self.pattern = os.path.join(self.path, "*.ics")
        self.files = []
        self.my_items = []
        self.mtime = 0
        self.scan_dir()

    @staticmethod
    def _parse(text, item_types, name=None, path=None):
        """Find items with type in ``item_types`` in ``text`` text.

        If ``name`` is given, give this name to new items in ``text``.

        Return a list of items.

        """
        item_tags = {}
        for item_type in item_types:
            item_tags[item_type.tag] = item_type

        items = []

        jtext = text.replace("\n ", "")

        lines = jtext.splitlines()
        in_item = False

        for line in lines:
            if line.startswith("BEGIN:") and not in_item:
                item_tag = line.replace("BEGIN:", "").strip()
                if item_tag in item_tags:
                    in_item = True
                    item_lines = []

            if in_item:
                item_lines.append(line)
                if line.startswith("END:%s" % item_tag):
                    in_item = False
                    item_type = item_tags[item_tag]
                    item_text = "\n".join(item_lines)
                    item_name = None if item_tag == "VTIMEZONE" else name
                    item = item_type(item_text, item_name, path)
                    items.append(item)

        return items

    def has_git(self):
        return os.path.exists(os.path.join(self.path, ".git"))

    def git_add(self, path):
        if self.has_git():
            command="cd %s && git add %s && git commit -m'Add %s'" % (self.path, os.path.basename(path), "new file")
            print ("Execute git command %s" % command)
            os.system(command)
    
    def git_rm(self, path):
        if self.has_git():
            command="cd %s && git rm %s && git commit -m'Remove %s'" % (self.path, os.path.basename(path), "old file")
            print ("Execute git command %s" % command)
            os.system(command)

    def git_change(self, path):
        if self.has_git():
            command="cd %s && git add %s && git commit -m'Change %s'" % (self.path, os.path.basename(path), "modified file")
            print ("Execute git command %s" % command)
            os.system(command)
            
    def create_file(self, item):
        # Create directory if necessary
        if not os.path.exists(os.path.dirname(self.path)):
            os.makedirs(os.path.dirname(self.path))

        fd, new_path = tempfile.mkstemp(suffix=".ics", prefix="cal", dir=self.path)
        print ("Create item in file %s" % new_path)
        file = open(new_path, 'w')
        file.write(item.text)
        file.close()
        os.close(fd)
        self.git_add(new_path)
        self.scan_dir()

    def destroy_file(self, item):
        print ("Remove item in file %s" % item.path)
        try:
            os.unlink(item.path)
            self.git_rm(item.path)
        except OSError:
            print ("Failed to remove file %s" %item.path)
        self.scan_dir()

    def rewrite_file(self, item, path):
        fd, new_path = tempfile.mkstemp(suffix=".ics", prefix="cal", dir=self.path)
        print ("Rewrite item in file %s (temp %s)" % (path, new_path))
        file = open(new_path, 'w')
        file.write(item.text)
        file.close()
        os.close(fd)
        os.rename(new_path, path)
        self.git_change(path)
        self.scan_file(path)
        self.scan_dir()
        
    def get_item(self, name):
        """Get calendar item called ``name``."""
        print ("get_item %s\n" % name)
        for item in self.my_items:
            print ("item.name %s\n" % item.name)
            if item.name == name:
                return item
        return None

    def get_full(self, base):
        """Get everything that is stored with ``item``."""
        items=[]
        for item in self.my_items:
            if item.path == base.path:
                items.append(item)
        return items
        
    def get_items(self, name):
        """Get calendar items called ``name``."""
        items=[]
        for item in self.my_items:
            if item.name == name:
                items.append(item)
        return items

    def append(self, name, text):
        """Append items from ``text`` to calendar.

        If ``name`` is given, give this name to new items in ``text``.

        """

        new_item = Item(text, name, None)
        if new_item.uid not in (item.uid for item in self.my_items):
                self.create_file(new_item)

    def remove(self, name):
        """Remove object named ``name`` from calendar."""
        for old_item in self.my_items:
            if old_item.name == name:
                self.destroy_file(old_item)
                
#        todos = [todo for todo in self.todos if todo.name != name]
#        events = [event for event in self.events if event.name != name]

#        items = self.timezones + todos + events
#        self.write(items=items)

    def replace(self, name, text):
        """Replace content by ``text`` in objet named ``name`` in calendar."""
        path=None
        for old_item in self.my_items:
            if old_item.name == name:
                path = old_item.path
                break
        new_item = Item(text, name, path)
        if path is not None:
            self.rewrite_file(new_item, path)
        else:
            self.remove(name)
            self.append(name, text)

    def write(self, headers=None, items=None):
        #"""Write calendar with given parameters."""
        #headers = headers or self.headers or (
        #    Header("PRODID:-//Calypso//NONSGML Calypso Server//EN"),
        #    Header("VERSION:2.0"))
        #items = items if items is not None else self.items

        # Create folder if absent
        #if not os.path.exists(os.path.dirname(self.path)):
        #    os.makedirs(os.path.dirname(self.path))
        
        #text = serialize(headers=headers, items=items)
        #return open(self.path, "w").write(text)
        return True

    @property
    def etag(self):
        """Etag from calendar."""
        h = hashlib.sha1()
        for item in self.my_items:
            h.update(item.etag)
        return h.hexdigest()

    @property
    def name(self):
        """Calendar name."""
        return self.path.split(os.path.sep)[-1]

    @property
    def text(self):
        """Calendar as plain text."""
        self.scan_dir()
        headers = []

#        headers.append(Item("PRODID:-//Calypso//NONSGML Calypso Server//EN"))
#        headers.append(Item("VERSION:2.0"))

        return ""

    @property
    def headers(self):
        """Find headers items in calendar."""
        header_lines = []

#        header_lines.append(Item("PRODID:-//Calypso//NONSGML Calypso Server//EN"))
#        header_lines.append(Item("VERSION:2.0"))

        return header_lines

    @property
    def items(self):
        """Get list of all items in calendar."""
        self.scan_dir()
        return self.my_items

    @property
    def last_modified(self):
        """Get the last time the calendar has been modified.

        The date is formatted according to rfc1123-5.2.14.

        """
        self.scan_dir()
        modification_time = time.gmtime(self.mtime)
        return time.strftime("%a, %d %b %Y %H:%M:%S +0000", modification_time)
