import shutil
import subprocess
import tempfile
import unittest

import calypso.config


class CalypsoTestCase(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        calypso.config.set('storage', 'folder', self.tmpdir)
        subprocess.call(["git", "init", self.tmpdir])
        subprocess.call(["git", "config", "user.email", "calypso@example.com"], cwd=self.tmpdir)
        subprocess.call(["git", "config", "user.name", "cal Ypso"], cwd=self.tmpdir)

    def tearDown(self):
        if self.tmpdir:
            shutil.rmtree(self.tmpdir)
