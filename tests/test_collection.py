# vim: set fileencoding=utf-8 :

import subprocess
import tempfile
import shutil
import unittest

from calypso.webdav import Collection
from calypso import paths

from .testutils import CalypsoTestCase


class TestCollection(CalypsoTestCase):
    test_vcard = "tests/data/import.vcard"
    test_resource_with_slash = "tests/data/from-tripsync.ics"

    def test_import_file(self):
        collection = Collection("")
        self.assertTrue(collection.import_file(self.test_vcard))
        self.assertEqual(len(collection.items), 2)
        org = u'Universitetet i Tromsø'
        self.assertTrue(org == collection.items[0].object.org.value[0])

    def test_uid_with_slash(self):
        collection = Collection("/")
        self.assertTrue(collection.import_file(self.test_resource_with_slash))
        self.assertEqual(len(collection.items), 1)
        veventuid = collection.items[0].object.vevent.uid.value
        r = paths.resource_from_path(veventuid)
        c = paths.collection_from_path(veventuid)
        self.assertTrue(r == veventuid)
        self.assertTrue("/" == c)
