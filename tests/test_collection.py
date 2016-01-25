# vim: set fileencoding=utf-8 :
"""Test L{gbp.command_wrappers.Command}'s tarball unpack"""

import os
import subprocess
import tempfile
import shutil
import unittest

import calypso.config
from calypso.webdav import Collection
from calypso import paths


class TestCollection(unittest.TestCase):
    test_vcard = "tests/data/import.vcard"
    test_resource_with_slash = "tests/data/from-tripsync.ics"

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        calypso.config.set('storage', 'folder', self.tmpdir)
        subprocess.call(["git", "init", self.tmpdir]),

    def tearDown(self):
        if self.tmpdir:
            shutil.rmtree(self.tmpdir)

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
