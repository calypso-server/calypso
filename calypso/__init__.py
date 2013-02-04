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
Calypso Server module.

This module offers 3 useful classes:

- ``HTTPServer`` is a simple HTTP server;
- ``HTTPSServer`` is a HTTPS server, wrapping the HTTP server in a socket
  managing SSL connections;
- ``CollectionHTTPHandler`` is a WebDAV request handler for HTTP(S) servers.

To use this module, you should take a look at the file ``calypso.py`` that
should have been included in this package.

"""

import os
import os.path
import posixpath
import base64
import socket
import time
import datetime
import email.utils
import logging
import rfc822
import urllib

# Manage Python2/3 different modules
# pylint: disable=F0401
try:
    from http import client, server
except ImportError:
    import httplib as client
    import BaseHTTPServer as server
# pylint: enable=F0401

from . import acl, config, webdav, xmlutils, paths

log = logging.getLogger()
ch = logging.StreamHandler()
formatter = logging.Formatter("%(message)s")
ch.setFormatter (formatter)
log.addHandler(ch)

VERSION = "0.5"

def _check(request, function):
    """Check if user has sufficient rights for performing ``request``."""
    # ``_check`` decorator can access ``request`` protected functions
    # pylint: disable=W0212

    authorization = request.headers.get("Authorization", None)
    if authorization:
        challenge = authorization.lstrip("Basic").strip().encode("ascii")
        plain = request._decode(base64.b64decode(challenge))
        user, password = plain.split(":")
    else:
        user = password = None

    owner = None
    if request._collection:
        owner = request._collection.owner

    # Also send UNAUTHORIZED if there's no collection. Otherwise one
    # could probe the server for (non-)existing collections.
    if request.server.acl.has_right(owner, user, password):
        function(request, context={"user": user, "user-agent": request.headers.get("User-Agent", None)})
    else:
        request.send_response(client.UNAUTHORIZED)
        request.send_header(
            "WWW-Authenticate",
            "Basic realm=\"Calypso Server - Password Required\"")
        request.end_headers()
    # pylint: enable=W0212


class HTTPServer(server.HTTPServer):
    """HTTP server."""
    PROTOCOL = "http"

    # Maybe a Pylint bug, ``__init__`` calls ``server.HTTPServer.__init__``
    # pylint: disable=W0231
    def __init__(self, address, handler):
        """Create server."""
        server.HTTPServer.__init__(self, address, handler)
        self.acl = acl.load()
    # pylint: enable=W0231


class HTTPSServer(HTTPServer):
    """HTTPS server."""
    PROTOCOL = "https"

    def __init__(self, address, handler):
        """Create server by wrapping HTTP socket in an SSL socket."""
        # Fails with Python 2.5, import if needed
        # pylint: disable=F0401
        import ssl
        # pylint: enable=F0401

        HTTPServer.__init__(self, address, handler)
        self.socket = ssl.wrap_socket(
            socket.socket(self.address_family, self.socket_type),
            server_side=True,
            certfile=os.path.expanduser(config.get("server", "certificate")),
            keyfile=os.path.expanduser(config.get("server", "key")),
            ssl_version=ssl.PROTOCOL_SSLv23)
        self.server_bind()
        self.server_activate()


class CollectionHTTPHandler(server.BaseHTTPRequestHandler):
    """HTTP requests handler for WebDAV collections."""
    _encoding = config.get("encoding", "request")

    # Decorator checking rights before performing request
    check_rights = lambda function: lambda request: _check(request, function)
        
    def address_string(self):
        return str(self.client_address[0])

    def handle_one_request(self):
        """Handle a single HTTP request.

        You normally don't need to override this method; see the class
        __doc__ string for information on how to handle specific HTTP
        commands such as GET and POST.

        """
        try:
            self.raw_requestline = self.rfile.readline(4000000)
            if len(self.raw_requestline) > 65536:
                self.requestline = ''
                self.request_version = ''
                self.command = ''
                self.send_error(414)
                return
            if not self.raw_requestline:
                self.close_connection = 1
                return
            if not self.parse_request():
                # An error code has been sent, just exit
                return
            mname = 'do_' + self.command
            if not hasattr(self, mname):
                self.send_error(501, "Unsupported method (%r)" % self.command)
                return
            method = getattr(self, mname)
            method()
            self.wfile.flush() #actually send the response if not already done.
        except socket.timeout as e:
            #a read or a write timed out.  Discard this connection
            log.error("Request timed out: %r", e)
            self.close_connection = 1
            return


    collections = {}

    @property
    def _collection(self):
        """The ``webdav.Collection`` object corresponding to the given path."""
        path = paths.collection_from_path(self.path)
        if not path:
            return None
        if not path in CollectionHTTPHandler.collections:
            CollectionHTTPHandler.collections[path] = webdav.Collection(path)
        return CollectionHTTPHandler.collections[path]

    def _decode(self, text):
        """Try to decode text according to various parameters."""
        # List of charsets to try
        charsets = []

        # First append content charset given in the request
        content_type = self.headers.get("Content-Type", None)
        if content_type and "charset=" in content_type:
            charsets.append(content_type.split("charset=")[1].strip())
        # Then append default Calypso charset
        charsets.append(self._encoding)
        # Then append various fallbacks
        charsets.append("utf-8")
        charsets.append("iso8859-1")

        # Try to decode
        for charset in charsets:
            try:
                return text.decode(charset)
            except UnicodeDecodeError:
                pass
        raise UnicodeDecodeError

    # Naming methods ``do_*`` is OK here
    # pylint: disable=C0103

    @check_rights
    def do_GET(self, context):
        """Manage GET request."""
        self.do_HEAD()
        if self._answer:
            self.wfile.write(self._answer)

    @check_rights
    def do_HEAD(self, context):
        """Manage HEAD request."""
        try:
            item_name = paths.resource_from_path(self.path)
            if item_name:
                # Get collection item
                item = self._collection.get_item(item_name)
                if item:
                    answer_text = item.text
                    etag = item.etag
                else:
                    self._answer = None
                    self.send_response(client.GONE)
                    self.end_headers()
                    return
            elif self._collection:
                # Get whole collection
                answer_text = self._collection.text
                etag = self._collection.etag
            else:
                self._answer = None
                self.send_response(client.NOT_FOUND)
                self.end_headers()
                return
                
            try:
                self._answer = answer_text.encode(self._encoding,"xmlcharrefreplace")
            except UnicodeDecodeError:
                answer_text = answer_text.decode(errors="ignore")
                self._answer = answer_text.encode(self._encoding,"ignore")
            
            self.send_response(client.OK)
            self.send_header("Content-Length", len(self._answer))
            self.send_header("Content-Type", "text/calendar")
            self.send_header("Last-Modified", email.utils.formatdate(time.mktime(self._collection.last_modified)))
            self.send_header("ETag", etag)
            self.end_headers()
        except Exception, ex:
            log.exception("Failed HEAD")
            self.send_response(client.BAD_REQUEST)
            self.end_headers()

    def if_match(self, item):
        header = self.headers.get("If-Match", item.etag)
        header = rfc822.unquote(header)
        if header == item.etag:
            return True
        quoted = '"' + item.etag + '"'
        if header == quoted:
            return True
        extraquoted = rfc822.quote(quoted)
        if header == extraquoted:
            return True
        return False

    @check_rights
    def do_DELETE(self, context):
        """Manage DELETE request."""
        try:
            item_name = paths.resource_from_path(self.path)
            item = self._collection.get_item(item_name)

            if item and self.if_match(item):
                # No ETag precondition or precondition verified, delete item
                self._answer = xmlutils.delete(self.path, self._collection, context=context)
                
                self.send_response(client.NO_CONTENT)
                self.send_header("Content-Length", len(self._answer))
                self.end_headers()
                self.wfile.write(self._answer)
            else:
                # No item or ETag precondition not verified, do not delete item
                self.send_response(client.PRECONDITION_FAILED)
                self.end_headers()
        except Exception, ex:
            log.exception("Failed DELETE")
            self.send_response(client.BAD_REQUEST)
            self.end_headers()

    @check_rights
    def do_MKCALENDAR(self, context):
        """Manage MKCALENDAR request."""
        self.send_response(client.CREATED)
        self.end_headers()

    @check_rights
    def do_OPTIONS(self, context):
        """Manage OPTIONS request."""
        self.send_response(client.OK)
        self.send_header(
            "Allow", "DELETE, HEAD, GET, MKCALENDAR, "
            "OPTIONS, PROPFIND, PUT, REPORT")
        self.send_header("DAV", "1, access-control, calendar-access, addressbook")
        self.end_headers()

    @check_rights
    def do_PROPFIND(self, context):
        """Manage PROPFIND request."""
        try:
            xml_request = self.rfile.read(int(self.headers["Content-Length"]))
            log.debug("PROPFIND %s", xml_request)
            self._answer = xmlutils.propfind(
                self.path, xml_request, self._collection,
                self.headers.get("depth", "infinity"))
            log.debug("PROPFIND ANSWER %s", self._answer)

            self.send_response(client.MULTI_STATUS)
            self.send_header("DAV", "1, calendar-access")
            self.send_header("Content-Length", len(self._answer))
            self.send_header("Content-Type", "text/xml")
            self.end_headers()
            self.wfile.write(self._answer)
        except Exception, ex:
            log.exception("Failed PROPFIND")
            self.send_response(client.BAD_REQUEST)
            self.end_headers()

    @check_rights
    def do_SEARCH(self, context):
        """Manage SEARCH request."""
        try:
            xml_request = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(client.NO_CONTENT)
            self.end_headers()
        except Exception, ex:
            log.exception("Failed SEARCH")
            self.send_response(client.BAD_REQUEST)
            self.end_headers()
        
    @check_rights
    def do_PUT(self, context):
        """Manage PUT request."""
        try:
            item_name = paths.resource_from_path(self.path)
            item = self._collection.get_item(item_name)
            if not item or self.if_match(item):

                # PUT allowed in 3 cases
                # Case 1: No item and no ETag precondition: Add new item
                # Case 2: Item and ETag precondition verified: Modify item
                # Case 3: Item and no Etag precondition: Force modifying item
                webdav_request = self._decode(
                    self.rfile.read(int(self.headers["Content-Length"])))
                xmlutils.put(self.path, webdav_request, self._collection, context=context)
                
                # We need to double get this item, because it just got created
                etag = self._collection.get_item(item_name).etag
                #log.debug("replacement etag %s", etag)

                self.send_response(client.CREATED)
                self.send_header("ETag", etag)
                self.end_headers()
            else:
                #log.debug("Precondition failed")
                # PUT rejected in all other cases
                self.send_response(client.PRECONDITION_FAILED)
        except Exception, ex:
            log.exception('Failed PUT')
            self.send_response(client.BAD_REQUEST)
            self.end_headers()


    @check_rights
    def do_REPORT(self, context):
        """Manage REPORT request."""
        try:
            xml_request = self.rfile.read(int(self.headers["Content-Length"]))
            log.debug("REPORT %s %s", self.path, xml_request)
            self._answer = xmlutils.report(self.path, xml_request, self._collection)
            log.debug("REPORT ANSWER %s", self._answer)
            self.send_response(client.MULTI_STATUS)
            self.send_header("Content-Length", len(self._answer))
            self.end_headers()
            self.wfile.write(self._answer)
        except Exception, ex:
            log.exception("Failed REPORT")
            self.send_response(client.BAD_REQUEST)
            self.end_headers()

    # pylint: enable=C0103
