import pathlib
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts/build'))
from complete_m2_workspace import missing_projects


class WorkspaceCompletionTest(unittest.TestCase):
    def setUp(self):
        self.manifest = ET.fromstring('<manifest><project path="external/pogreb" name="platform/external/pogreb" revision="pinned"/><project path="system/core" name="platform/system/core"/></manifest>')

    def test_missing_absolute_path_retains_pinned_revision(self):
        nodes = missing_projects('Failed to find deps: open /tmp/aosp/external/pogreb: no such file or directory', self.manifest, {'system/core'})
        self.assertEqual([p.attrib for p in nodes], [{'path': 'external/pogreb', 'name': 'platform/external/pogreb', 'revision': 'pinned'}])

    def test_does_not_retry_missing_file_inside_selected_project(self):
        self.assertEqual(missing_projects('system/core/init/missing.cpp: not found', self.manifest, {'system/core'}), [])

    def test_unknown_path_or_module_does_not_add_source(self):
        self.assertEqual(missing_projects('external/unknown/Android.bp: missing; module pogreb not found', self.manifest, set()), [])

    def test_successful_output_and_similar_prefix_are_ignored(self):
        self.assertEqual(missing_projects('Compiled external/pogreb\nexternal/pogreb-extra: not found', self.manifest, set()), [])
