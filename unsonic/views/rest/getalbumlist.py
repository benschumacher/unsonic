import xml.etree.ElementTree as ET
from  sqlalchemy.sql.expression import func as dbfunc

from . import Command, MissingParam, addCmd, fillAlbum, fillArtist, fillSong
from ...models import (DBSession, Artist, Album, AlbumRating, PlayCount, Track,
                       Scrobble)


class GetAlbumList(Command):
    name = "getAlbumList.view"
    param_defs = {
        "size": {"default": 10, "type": int},
        "offset": {"default": 0, "type": int},
        "type": {"required": True,
                 "values": ["alphabeticalByName", "alphabeticalByArtist",
                            "frequent", "highest", "newest", "random",
                            "recent", "starred",]},
        }

    def processRows(self, alist, result):
        for row in result:
            album = fillAlbum(row)
            alist.append(album)
            if row.artist:
                album.set("parent", "ar-%d" % row.artist.id)
            else:
                album.set("parent", "UNKNOWN")
            album.set("title", album.get("name"))
            album.set("isDir", "true")
        
    def handleReq(self):
        alist = ET.Element("albumList")
        size = self.params["size"]
        offset = self.params["offset"]
        limit = offset + size
        if self.params["type"] == "random":
            result = DBSession.query(Album). \
                         order_by(dbfunc.random()). \
                         offset(offset). \
                         limit(limit)
            self.processRows(alist, result)
        elif self.params["type"] == "newest":
            result = DBSession.query(Album). \
                         order_by(Album.date_added). \
                         offset(offset). \
                         limit(limit)
            self.processRows(alist, result)
        elif self.params["type"] == "highest":
            result = DBSession.query(AlbumRating). \
                         filter(AlbumRating.user_id ==
                                self.req.authed_user.id). \
                         order_by(AlbumRating.rating). \
                         offset(offset). \
                         limit(limit)
            albums = []
            for arate in result:
                albums.append(arate.album)
            self.processRows(alist, albums)
        elif self.params["type"] == "frequent":
            pcounts = DBSession.query(PlayCount). \
                         join(Track). \
                         filter(PlayCount.user_id ==
                                self.req.authed_user.id). \
                         order_by(PlayCount.count). \
                         offset(offset). \
                         limit(limit)
            albums = []
            for pcount in pcounts:
                if not pcount.track.album:
                    continue
                if pcount.track.album not in albums:
                    albums.append(pcount.track.album)
                if len(albums) >= size:
                    break
            self.processRows(alist, albums)
        elif self.params["type"] == "recent":
            result = DBSession.query(Scrobble). \
                        filter(Scrobble.user_id ==
                               self.req.authed_user.id). \
                        order_by(Scrobble.tstamp.desc()). \
                        offset(offset). \
                        limit(limit)
            albums = []
            for scrobble in result:
                if not scrobble.track.album:
                    continue
                if scrobble.track.album not in albums:
                    albums.append(scrobble.track.album)
                if len(albums) >= size:
                    break
            self.processRows(alist, albums)
        elif self.params["type"] == "starred":
            result = DBSession.query(AlbumRating). \
                         filter(AlbumRating.user_id ==
                                self.req.authed_user.id). \
                         filter(AlbumRating.starred is not None). \
                         order_by(AlbumRating.starred). \
                         offset(offset). \
                         limit(limit)
            albums = []
            for arate in result:
                albums.append(arate.album)
            self.processRows(alist, albums)
        elif self.params["type"] == "alphabeticalByName":
            result = DBSession.query(Album). \
                         order_by(Album.title). \
                         offset(offset). \
                         limit(limit)
            self.processRows(alist, result)
        elif self.params["type"] == "alphabeticalByArtist":
            size = self.params["size"]
            artists = DBSession.query(Artist). \
                          order_by("name"). \
                          limit(limit)
            for artist in artists:
                albums = DBSession.query(Album). \
                             filter(Album.artist_id == artist.id). \
                             order_by(Album.title). \
                             offset(offset). \
                             limit(limit)
                self.processRows(alist, artist.albums)
        else:
            # FIXME: Implement the rest once play tracking is done
            raise MissingParam("Unsupported type")

        return self.makeResp(child=alist)


addCmd(GetAlbumList)
