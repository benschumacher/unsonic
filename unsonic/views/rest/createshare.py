import xml.etree.ElementTree as ET
import shortuuid
from . import (Command, registerCmd, playable_id_t, datetime_t, str_t, fillShare,
               MissingParam, NotFound)
from ...models import Album, Track, PlayList, Share, ShareEntry


@registerCmd
class CreateShare(Command):
    name = "createShare.view"
    param_defs = {
        "id": {"type": playable_id_t, "required": True, "multi": True},
        "description": {"type": str_t},
        "expires": {"type": datetime_t},
        }
    dbsess = True


    def handleReq(self, session):
        db_share = Share()
        db_share.user_id = self.req.authed_user.id
        db_share.uuid = shortuuid.uuid()
        db_share.description = self.params["description"]
        db_share.expires = self.params["expires"]
        session.add(db_share)

        for pid in self.params["id"]:
            if pid.startswith("al-"):
                klass = Album
            elif pid.startswith("tr-"):
                klass = Track
            elif pid.startswith("pl-"):
                klass = PlayList
            else:
                raise MissingParam(
                    f"Invalid id, must be an album or track: {pid}")
            id = int(pid[3:])
            row = session.query(klass).filter(klass.id == id).one_or_none()
            if not row:
                raise NotFound(f"Invalid id: {pid}")

            db_share_entry = ShareEntry()
            db_share_entry.share_id = db_share.id
            db_share_entry.uuid = shortuuid.uuid()
            if pid.startswith("al-"):
                db_share_entry.album_id = id
            elif pid.startswith("tr-"):
                db_share_entry.track_id = id
            elif pid.startswith("pl-"):
                db_share_entry.playlist_id = id
            session.add(db_share_entry)

        session.flush()

        shares = ET.Element("shares")
        shares.append(fillShare(session, self.req, db_share))

        return self.makeResp(child=shares)
