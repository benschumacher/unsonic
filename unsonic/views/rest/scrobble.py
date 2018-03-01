import time
import logging

from sqlalchemy.orm.exc import NoResultFound

from . import Command, registerCmd, bool_t, track_t, int_t, NotFound
from ...models import PlayCount, Track, dbinfo
from ...models import Scrobble as DBScrobble

log = logging.getLogger(__name__)


@registerCmd
class Scrobble(Command):
    name = "scrobble.view"
    param_defs = {
        "id": {"required": True, "type": track_t},
        "time": {"type": int_t},
        "submission": {"type": bool_t, "default": True},
    }
    dbsess = True

    def handleReq(self, session):
        # Check track id
        try:
            track = session.query(Track)\
                           .filter(Track.id == self.params["id"]).one()
        except NoResultFound:
            raise NotFound("Track not found")

        lastfm = self.req.authed_user.lastfm
        if not self.params["submission"]:
            # User is listening, not scrobbling yet
            dbinfo.users[self.req.authed_user.name]\
                  .listening = self.params["id"]

            if lastfm.is_user:
                log.info(f"last.fm now playing: {track.artist} - {track.title}")
                lastfm.update_now_playing(track.artist, track.title,
                                          album=track.album.title,
                                          album_artist=track.album_artist,
                                          duration=track.time_secs,
                                          track_number=track.track_num)
            else:
                log.info(f"No LastFM user, skipping LastFM")
        else:
            # Inc play count
            try:
                pcount = session.query(PlayCount). \
                    filter(PlayCount.track_id == self.params["id"],
                           PlayCount.user_id ==
                           self.req.authed_user.id).one()
                pcount.count = pcount.count + 1
            except NoResultFound:
                pcount = PlayCount(track_id=self.params["id"],
                                   user_id=self.req.authed_user.id,
                                   count=1)
                session.add(pcount)
            session.flush()

            # Local scrobble
            scrobble = DBScrobble(user_id=self.req.authed_user.id,
                                  track_id=self.params["id"])
            session.add(scrobble)

            if lastfm.is_user:
                log.info(f"last.fm scrobbling: {track.artist} - {track.title}")
                lastfm.scrobble(track.artist.name, track.title,
                                int(time.time()),
                                album=track.album.title,
                                album_artist=track.album.artist.name,
                                track_number=track.track_num,
                                duration=track.time_secs)
            else:
                log.info(f"No LastFM user, skipping LastFM")

        return self.makeResp()
