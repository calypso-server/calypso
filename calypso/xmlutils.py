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

"""
XML and iCal requests manager.

Note that all these functions need to receive unicode objects for full
iCal requests (PUT) and string objects with charset correctly defined
in them for XML requests (all but PUT).

"""

import xml.etree.ElementTree as ET
import time
import dateutil
import dateutil.parser
import dateutil.rrule
import dateutil.tz
import datetime
import email.utils
import logging
import urllib
import os.path

from . import client, config, webdav, paths

__package__ = 'calypso.xmlutils'

NAMESPACES = {
    "C": "urn:ietf:params:xml:ns:caldav",
    "A": "urn:ietf:params:xml:ns:carddav",
    "D": "DAV:",
    "CS": "http://calendarserver.org/ns/"}

log = logging.getLogger(__name__)

def _tag(short_name, local):
    """Get XML Clark notation {uri(``short_name``)}``local``."""
    return "{%s}%s" % (NAMESPACES[short_name], local)


def _response(code):
    """Return full W3C names from HTTP status codes."""
    return "HTTP/1.1 %i %s" % (code, client.responses[code])

def delete(path, collection, context):
    """Read and answer DELETE requests.

    Read rfc4918-9.6 for info.

    """
    # Reading request
    collection.remove(paths.resource_from_path(path), context=context)

    # Writing answer
    multistatus = ET.Element(_tag("D", "multistatus"))
    response = ET.Element(_tag("D", "response"))
    multistatus.append(response)

    href = ET.Element(_tag("D", "href"))
    href.text = path
    response.append(href)

    status = ET.Element(_tag("D", "status"))
    status.text = _response(200)
    response.append(status)

    return ET.tostring(multistatus, config.get("encoding", "request"))


def propfind(path, xml_request, collection, depth):
    """Read and answer PROPFIND requests.

    Read rfc4918-9.1 for info.

    """

    item_name = paths.resource_from_path(path)
    collection_name = paths.collection_from_path(path)

    # Reading request
    root = ET.fromstring(xml_request)

    prop_element = root.find(_tag("D", "prop"))
    if prop_element is not None:
        prop_list = prop_element.getchildren()
        props = [prop.tag for prop in prop_list]
    else:
        props = [_tag("D", "resourcetype"),
                 _tag("D", "owner"),
                 _tag("D", "getcontenttype"),
                 _tag("D", "getetag"),
                 _tag("D", "principal-collection-set"),
                 _tag("C", "supported-calendar-component-set"),
                 _tag("D", "supported-report-set"),
                 _tag("D", "current-user-privilege-set"),
                 _tag("D", "getcontentlength"),
                 _tag("D", "getlastmodified")]

    
    # Writing answer
    multistatus = ET.Element(_tag("D", "multistatus"))

    if collection:
        if item_name:
            item = collection.get_item(item_name)
            print "item_name %s item %s" % (item_name, item)
            if item:
                items = [item]
            else:
                items = []
        else:
            if depth == "0":
                items = [collection]
            else:
                # depth is 1, infinity or not specified
                # we limit ourselves to depth == 1
                items = [collection] + collection.items
    else:
        items = []

    for item in items:
        is_collection = isinstance(item, webdav.Collection)

        response = ET.Element(_tag("D", "response"))
        multistatus.append(response)

        href = ET.Element(_tag("D", "href"))
        href.text = collection_name if is_collection else "/".join([collection_name, item.name])
        response.append(href)

        propstat = ET.Element(_tag("D", "propstat"))
        response.append(propstat)

        prop = ET.Element(_tag("D", "prop"))
        propstat.append(prop)

        for tag in props:
            element = ET.Element(tag)
            if tag == _tag("D", "resourcetype") and is_collection:
                tag = ET.Element(_tag("C", "calendar"))
                element.append(tag)
                tag = ET.Element(_tag("A", "addressbook"))
                element.append(tag)
                tag = ET.Element(_tag("D", "collection"))
                element.append(tag)
            elif tag == _tag("D", "owner"):
                element.text = collection.owner
            elif tag == _tag("D", "getcontenttype"):
                if item.tag == 'VCARD':
                    element.text = "text/vcard"
                else:
                    element.text = "text/calendar"
            elif tag == _tag("CS", "getctag") and is_collection:
                element.text = item.ctag
            elif tag == _tag("D", "getetag"):
                element.text = item.etag
            elif tag == _tag("D", "displayname") and is_collection:
                element.text = collection.name
            elif tag == _tag("D", "principal-URL"):
                # TODO: use a real principal URL, read rfc3744-4.2 for info
                tag = ET.Element(_tag("D", "href"))
                tag.text = path
                element.append(tag)
            elif tag in (
                _tag("D", "principal-collection-set"),
                _tag("C", "calendar-user-address-set"),
                _tag("C", "calendar-home-set"),
                _tag("A", "addressbook-home-set")):
                tag = ET.Element(_tag("D", "href"))
                tag.text = path
                element.append(tag)
            elif tag == _tag("C", "supported-calendar-component-set"):
                comp = ET.Element(_tag("C", "comp"))
                comp.set("name", "VTODO") # pylint: disable=W0511
                element.append(comp)
                comp = ET.Element(_tag("C", "comp"))
                comp.set("name", "VEVENT")
                element.append(comp)
            elif tag == _tag("D", "supported-report-set"):
                tag = ET.Element(_tag("C", "calendar-multiget"))
                element.append(tag)
                tag = ET.Element(_tag("C", "filter"))
                element.append(tag)
            elif tag == _tag("D", "current-user-privilege-set"):
                privilege = ET.Element(_tag("D", "privilege"))
                privilege.append(ET.Element(_tag("D", "all")))
                element.append(privilege)
            elif tag == _tag("D", "getcontentlength"):
                element.text = item.length
            elif tag == _tag("D", "getlastmodified"):
#                element.text = time.strftime("%a, %d %b %Y %H:%M:%S +0000", item.last_modified)
#                element.text = email.utils.formatdate(item.last_modified)
                element.text = email.utils.formatdate(time.mktime(item.last_modified))
            prop.append(element)

        status = ET.Element(_tag("D", "status"))
        status.text = _response(200)
        propstat.append(status)

    return ET.tostring(multistatus, config.get("encoding", "request"))


def put(path, webdav_request, collection, context):
    """Read PUT requests."""
    name = paths.resource_from_path(path)
    if name in (item.name for item in collection.items):
        # PUT is modifying an existing item
        collection.replace(name, webdav_request, context=context)
    else:
        # PUT is adding a new item
        log.debug('Putting a new item, because name %s is not known', name)
        collection.append(name, webdav_request, context=context)


def match_filter_element(vobject, fe):
    if fe.tag == _tag("C", "comp-filter"):
        comp = fe.get("name")
        if comp:
            if comp == vobject.name:
                hassub = False
                submatch = False
                for fc in fe.getchildren():
                    if match_filter_element(vobject, fc):
                        submatch = True
                        break
                    for vc in vobject.getChildren():
                        hassub = True
                        if match_filter_element (vc, fc):
                            submatch = True
                            break
                    if submatch:
                        break
                if not hassub or submatch:
                    return True
        return False
    elif fe.tag == _tag("C", "time-range"):
        try:
            rruleset = vobject.rruleset
        except AttributeError:
            return False
        start = fe.get("start")
        end = fe.get("end")
        if rruleset is None:
            rruleset = dateutil.rrule.rruleset()
            dtstart = vobject.dtstart.value
            try:
                dtstart = datetime.datetime.combine(dtstart, datetime.time())
            except Exception:
                0
            if dtstart.tzinfo is None:
                dtstart = dtstart.replace(tzinfo = dateutil.tz.tzlocal())
            rruleset.rdate(dtstart)
        start_datetime = dateutil.parser.parse(start)
        if start_datetime.tzinfo is None:
            start_datetime = start_datetime.replace(tzinfo = dateutil.tz.tzlocal())
        end_datetime = dateutil.parser.parse(end)
        if end_datetime.tzinfo is None:
            end_datetime = end_datetime.replace(tzinfo = dateutil.tz.tzlocal())
        try:
            if rruleset.between(start_datetime, end_datetime, True):
                return True
        except TypeError:
            start_datetime = start_datetime.replace(tzinfo = None)
            end_datetime = end_datetime.replace(tzinfo = None)
            try:
                if rruleset.between(start_datetime, end_datetime, True):
                    return True
            except TypeError:
                return True
        return False
    return True

def match_filter(item, filter):
    if filter is None:
        return True
    if filter.tag != _tag("C", "filter"):
        return True
    for fe in filter.getchildren():
        if match_filter_element(item.object, fe):
            return True

def report(path, xml_request, collection):
    """Read and answer REPORT requests.

    Read rfc3253-3.6 for info.

    """
    # Reading request
    root = ET.fromstring(xml_request)

    prop_element = root.find(_tag("D", "prop"))
    prop_list = prop_element.getchildren()
    props = [prop.tag for prop in prop_list]

    filter_element = root.find(_tag("C", "filter"))

    if collection:
        if root.tag == _tag("C", "calendar-multiget"):
            # Read rfc4791-7.9 for info
            hreferences = set((href_element.text for href_element
                               in root.findall(_tag("D", "href"))))
        else:
            hreferences = (path,)
    else:
        hreferences = ()

    # Writing answer
    multistatus = ET.Element(_tag("D", "multistatus"))

    for hreference in hreferences:
        # Check if the reference is an item or a collection
        name = paths.resource_from_path(hreference)
        if name:
            # Reference is an item
            path = paths.collection_from_path(hreference) + "/"
            items = (item for item in collection.items if item.name == name)
        else:
            # Reference is a collection
            path = hreference
            items = collection.items

        
        for item in items:
            if not match_filter(item, filter_element):
                continue

            response = ET.Element(_tag("D", "response"))
            multistatus.append(response)

            href = ET.Element(_tag("D", "href"))
            href.text = path.rstrip('/') + '/' + item.name
            response.append(href)

            propstat = ET.Element(_tag("D", "propstat"))
            response.append(propstat)

            prop = ET.Element(_tag("D", "prop"))
            propstat.append(prop)

            for tag in props:
                element = ET.Element(tag)
                if tag == _tag("D", "getetag"):
                    element.text = item.etag
                elif tag == _tag("C", "calendar-data"):
                    element.text = item.text
                prop.append(element)

            status = ET.Element(_tag("D", "status"))
            status.text = _response(200)
            propstat.append(status)

    reply = ET.tostring(multistatus, config.get("encoding", "request"))
        
    return reply
