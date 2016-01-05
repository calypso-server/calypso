# vim: set fileencoding=utf-8 :
"""Test L{gbp.command_wrappers.Command}'s tarball unpack"""

import os
import subprocess
import tempfile
import shutil
import unittest

import calypso.config
from calypso.webdav import Collection


class TestCollection(unittest.TestCase):
    test_vcard = "tests/data/import.vcard"

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
        self.assertEqual(len(collection.items), 1)
