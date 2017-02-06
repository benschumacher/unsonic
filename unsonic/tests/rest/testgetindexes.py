import unittest
from pyramid import testing

from . import RestTestCase, setUpModule
from ...models import Session
from ...views.rest.getindexes import GetIndexes
from ...views.rest import Command


class TestIndexes(RestTestCase):
    @unittest.skip("Fix the extra protocol bits")
    def testBasic(self):
        cmd = self.buildCmd(GetIndexes)
        resp = cmd()
        sub_resp = self.checkResp(cmd.req, resp)
        indexes = sub_resp.find("{http://subsonic.org/restapi}indexes")
        for index in indexes.iter("{http://subsonic.org/restapi}index"):
            index_name = index.get("name")
            for artist in index.iter("{http://subsonic.org/restapi}artist"):
                self.assertTrue(artist.get("id").startswith("ar-"))
                self.assertTrue(len(artist.get("name")) > 0)
                self.assertEqual(artist.get("name")[0].upper(), index_name)