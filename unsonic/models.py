import os
import datetime
from argparse import Namespace
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config

import sqlalchemy
from sqlalchemy import (Table, Column, Integer, Text, ForeignKey, String,
                        DateTime, Index, Boolean, UniqueConstraint)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import relation
from sqlalchemy.orm.exc import NoResultFound

import mishmash.orm
from mishmash.orm import Base, Artist, Album, Meta, Track   # noqa: F401
from mishmash.orm import Image, Tag, artist_images          # noqa: F401
from mishmash.orm import album_images, track_tags           # noqa: F401
from mishmash.database import init as dbinit

import unsonic.config


db_url = None
db_engine = None
session_maker = None
dbinfo = Namespace()
ALL = object()


@sqlalchemy.event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Allows foreign keys to work in sqlite."""
    import sqlite3
    if dbapi_connection.__class__ is sqlite3.Connection:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@contextmanager
def Session():
    """Provide a transactional scope around a series of operations."""
    session = session_maker()
    try:
        yield session
        if hasattr(session, "failed"):
            session.rollback()
        else:
            session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


# DB models
class OrmObject(mishmash.orm.OrmObject):
    @staticmethod
    def loadTable(session):
        pass


class DBInfo(Base, OrmObject):
    __tablename__ = 'un_dbinfo'

    version = Column(String(32), nullable=False, primary_key=True)
    last_sync = Column(DateTime)


    @staticmethod
    def loadTable(session):
        dbinfo.version = None
        dbinfo.old_versions = []
        for dbi in session.query(DBInfo).order_by(DBInfo.version).all():
            if dbinfo.version is None:
                dbinfo.version = dbi.version
            else:
                dbinfo.old_versions.append(dbi.version)


class User(Base, OrmObject):
    __tablename__ = 'un_users'

    # Columns
    id = Column(Integer, primary_key=True)
    name = Column(Text, unique=True)
    password = Column(Text)
    email = Column(Text)
    maxbitrate = Column(Integer, default=0, nullable=False)
    scrobbling = Column(Boolean, default=True, nullable=False)
    playqueue_cur = Column(Integer, ForeignKey("tracks.id"))
    playqueue_pos = Column(Integer, default=0, nullable=False)
    playqueue_mtime = Column(sqlalchemy.DateTime())
    playqueue_mby = Column(Text)

    # Roles
    roles = relation("Role", cascade="all, delete-orphan",
                      passive_deletes=True)
    playqueue = relation("PlayQueue", cascade="all, delete-orphan",
                         passive_deletes=True)
    playlists = relation("PlayList", cascade="all, delete-orphan",
                         passive_deletes=True)
    avatar = Column(Integer, ForeignKey("images.id", ondelete='CASCADE'))


    @staticmethod
    def loadTable(session):
        try:
            dbinfo.users = {}
            for user in session.query(User).all():
                u = Namespace()
                u.name = user.name
                u.listening = None
                dbinfo.users[u.name] = u
        finally:
            session.close()


class Role(Base, OrmObject):
    __tablename__ = 'un_roles'
    __table_args__ = (UniqueConstraint("user_id", "name"), {})

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("un_users.id", ondelete='CASCADE'),
                     nullable=False)
    name = Column(Text, nullable=False)
    user = relation("User")


class PlayQueue(Base, OrmObject):
    __tablename__ = "un_playqueues"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("un_users.id", ondelete='CASCADE'),
                     nullable=False)
    track_id = Column(Integer, ForeignKey("tracks.id"), nullable=False)
    user = relation("User")
    track = relation("Track")


playlist_images = Table("un_playlist_images", Base.metadata,
                        Column("playlist_id", Integer,
                               ForeignKey("un_playlists.id")),
                        Column("img_id", Integer,
                               ForeignKey("images.id")))
'''Pivot table 'playlist_images' for mapping a playlist ID to a value in the
`images` table.'''


class PlayList(Base, OrmObject):
    __tablename__ = 'un_playlists'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("un_users.id", ondelete='CASCADE'),
                      nullable=False)
    name = Column(Text)
    comment = Column(Text)
    public = Column(Integer, default=0)
    created = sqlalchemy.Column(sqlalchemy.DateTime(), nullable=False,
                                default=datetime.datetime.now)
    changed = sqlalchemy.Column(sqlalchemy.DateTime(), nullable=False,
                                default=datetime.datetime.now)
    users = relation("PlayListUser", cascade="all, delete-orphan",
                     passive_deletes=True)
    tracks = relation("PlayListTrack", cascade="all, delete-orphan",
                      passive_deletes=True)
    owner = relation("User")
    images = relation("Image", secondary=playlist_images, cascade="all")
    '''one-to-many playlist images.'''


class PlayListUser(Base, OrmObject):
    __tablename__ = 'un_playlistusers'

    id = Column(Integer, primary_key=True)
    playlist_id = Column(Integer, ForeignKey("un_playlists.id",
                                             ondelete='CASCADE'),
                         nullable=False)
    user_id = Column(Integer, ForeignKey("un_users.id"), nullable=False)
    playlist = relation("PlayList")
    user = relation("User")


class PlayListTrack(Base, OrmObject):
    __tablename__ = 'un_playlisttracks'

    id = Column(Integer, primary_key=True)
    playlist_id = Column(Integer, ForeignKey("un_playlists.id",
                                             ondelete='CASCADE'),
                         nullable=False)
    track_id = Column(Integer, ForeignKey("tracks.id"), nullable=False)
    track = relation("Track")
    playlist = relation("PlayList")


# Modify the Track to include a relation to PlayListTrack
Track.playlist = relation("PlayListTrack")


class ArtistRating(Base, OrmObject):
    __tablename__ = "un_artistratings"

    artist_id = Column(Integer, ForeignKey("artists.id"), nullable=False,
                       primary_key=True)
    user_id = Column(Integer, ForeignKey("un_users.id"), nullable=False,
                     primary_key=True)
    rating = Column(Integer, default=None, nullable=True)
    pseudo_rating = Column(Boolean, default=True, nullable=False)
    starred = Column(DateTime, default=None, nullable=True)
    pseudo_starred = Column(Boolean, default=True, nullable=False)
    artist = relation("Artist")
    user = relation("User")


Artist.rating = relation("ArtistRating")


class AlbumRating(Base, OrmObject):
    __tablename__ = "un_albumratings"

    album_id = Column(Integer, ForeignKey("albums.id"), nullable=False,
                      primary_key=True)
    user_id = Column(Integer, ForeignKey("un_users.id"), nullable=False,
                     primary_key=True)
    rating = Column(Integer, default=None, nullable=True)
    pseudo_rating = Column(Boolean, default=True, nullable=False)
    starred = Column(DateTime, default=None, nullable=True)
    pseudo_starred = Column(Boolean, default=True, nullable=False)
    album = relation("Album")
    user = relation("User")


Album.rating = relation("AlbumRating")


class TrackRating(Base, OrmObject):
    __tablename__ = "un_trackratings"

    track_id = Column(Integer, ForeignKey("tracks.id"), nullable=False,
                      primary_key=True)
    user_id = Column(Integer, ForeignKey("un_users.id"), nullable=False,
                     primary_key=True)
    rating = Column(Integer, default=None, nullable=True)
    starred = Column(DateTime, default=None, nullable=True)
    track = relation("Track")
    user = relation("User")


Track.rating = relation("TrackRating")


class PlayCount(Base, OrmObject):
    __tablename__ = "un_playcounts"

    track_id = Column(Integer, ForeignKey("tracks.id"), nullable=False,
                      primary_key=True)
    user_id = Column(Integer, ForeignKey("un_users.id"), nullable=False,
                     primary_key=True)
    count = Column(Integer, nullable=False)
    track = relation("Track")
    user = relation("User")


Track.play_count = relation("PlayCount")


class Scrobble(Base, OrmObject):
    __tablename__ = "un_scrobbles"

    id = Column(Integer, primary_key=True)
    track_id = Column(Integer, ForeignKey("tracks.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("un_users.id"), nullable=False)
    tstamp = Column(DateTime, default=None, nullable=False)
    track = relation("Track")
    user = relation("User")

    @declared_attr
    def __table_args__(cls):
        return (Index("scrobble_user_index", "user_id"), )


Track.scrobbles = relation("Scrobble")


# Utility functions
def init(settings, webapp=False):
    global db_url, db_engine, session_maker
    settings["sqlalchemy.url"] = web.CONFIG.get("mishmash", "sqlalchemy.url")
    settings["sqlalchemy.convert_unicode"] = \
        web.CONFIG.get("mishmash", "sqlalchemy.convert_unicode")
    settings["sqlalchemy.encoding"] = web.CONFIG.get("mishmash",
                                                     "sqlalchemy.encoding")
    db_url = settings["sqlalchemy.url"]
    config = Namespace()
    config.db_url = db_url
    config.various_artists_name = web.CONFIG.get("mishmash",
                                                 "various_artists_name")
    db_engine, session_maker = dbinit(config)
    initAlembic()


def initAlembic():
    # Upgrade to head (i.e. this) revision, or no-op if they match
    db_url = unsonic.config.CONFIG.get("mishmash", "sqlalchemy.url")
    alembic_d = Path(__file__).parent.parent / "alembic"
    alembic_cfg = Config(str(alembic_d / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")


def load():
    with Session() as session:
        for table in UN_TYPES:
            table.loadTable(session)


def asdict(value):
    ret = {}
    for line in [x.strip() for x in value.splitlines()]:
        if len(line):
            key, val = line.split(":")
            ret[key.strip()] = val.strip()
    return ret


def getMashPaths(settings):
    paths = asdict(web.CONFIG.get("mishmash", "paths"))
    for key in list(paths.keys()):
        paths[key] = os.path.expandvars(os.path.expanduser(paths[key]))
    return paths


# Table utilities

def addUser(session, username, password, roles):
    try:
        user = User(name=username, password=password)
        session.add(user)
        session.flush()
        for name in roles:
            role = Role(name=name, user_id=user.id)
            session.add(role)
        session.flush()
    except IntegrityError:
        session.failed = True
        return "Failed to add user. User already exists."
    return True


def delUser(session, username):
    session.query(User).filter(User.name == username).delete()
    session.flush()


def listUsers(session):
    users = []
    for user in session.query(User).all():
        users.append((user.name, [g.name for g in user.roles]))
    return users


def setUserPassword(session, uname, password):
    user = getUserByName(session, uname, False)
    if not user:
        return False
    session.add(user)
    user.password = password
    session.flush()
    return True


def getUserByName(session, username, wrap=True):
    try:
        urow = session.query(User).filter(User.name == username).one()
        if wrap:
            return auth.User(urow)
        else:
            return urow
    except NoResultFound:
        return None


def getUserByID(session, id):
    try:
        return auth.User(session.query(User).filter(User.id == id).one())
    except NoResultFound:
        return None


def rateItem(session, user_id, item_id, rating=None, starred=None):
    num = int(item_id[3:])
    artist_id = None
    album_id = None
    if item_id.startswith("ar-"):
        row = session.query(ArtistRating).filter(
            ArtistRating.artist_id == num,
            ArtistRating.user_id == user_id).one_or_none()
        if row is None:
            row = ArtistRating(artist_id=num, user_id=user_id)
            session.add(row)
    elif item_id.startswith("al-"):
        row = session.query(AlbumRating).filter(
            AlbumRating.album_id == num,
            AlbumRating.user_id == user_id).one_or_none()
        if row is None:
            row = AlbumRating(album_id=num, user_id=user_id)
            session.add(row)
            session.flush()
        artist_id = row.album.artist_id
    elif item_id.startswith("tr-"):
        row = session.query(TrackRating).filter(
            TrackRating.track_id == num,
            TrackRating.user_id == user_id).one_or_none()
        if row is None:
            row = TrackRating(track_id=num, user_id=user_id)
            session.add(row)
            session.flush()
        album_id = row.track.album_id
    if rating is not None:
        if rating == 0:
            row.rating = None
            row.pseudo_rating = True
        else:
            row.rating = rating
            row.pseudo_rating = False
    if isinstance(starred, datetime.datetime):
        row.starred = starred
        row.pseudo_starred = False
    elif starred is True:
        row.starred = None
        row.pseudo_starred = True
    session.flush()
    if artist_id or album_id:
        updatePseudoRatings(session=session, user_id=user_id, album_id=album_id,
                            artist_id=artist_id)


def updatePseudoRatings(session, user_id=None, album_id=ALL, artist_id=ALL):
    # Update albums first
    albums = None
    if album_id is ALL:
        albums = session.query(Album).all()
    elif album_id is not None:
        albums = session.query(Album).filter(Album.id == album_id).all()

    if albums:
        for album in albums:
            alrating = session.query(AlbumRating).filter(
                AlbumRating.album_id == album.id,
                AlbumRating.user_id == user_id).one_or_none()
            if alrating is None:
                alrating = AlbumRating(album_id=album.id, user_id=user_id)
                session.add(alrating)
            tracks = session.query(Track). \
                         filter(Track.album_id == album.id).all()
            pseudo = 0
            count = 0
            starred = None
            for track in tracks:
                trating = session.query(TrackRating).filter(
                    TrackRating.track_id == track.id,
                    TrackRating.user_id == user_id).one_or_none()
                if trating:
                    if trating.rating is not None:
                        pseudo += trating.rating
                    if trating.starred is not None:
                        if starred is None or starred > trating.starred:
                            # Extract the oldest starred date
                            starred = trating.starred
                # Down rank for unrated tracks
                count += 1
            if count and alrating.pseudo_rating:
                pseudo = round(float(pseudo) / float(count))
                alrating.rating = pseudo
                alrating.pseudo_rating = True
            if starred and alrating.pseudo_starred:
                alrating.starred = starred
                alrating.pseudo_starred = True

    # Update artists last
    artists = None
    if artist_id is ALL:
        artists = session.query(Artist).all()
    elif artist_id is not None:
        artists = session.query(Artist).filter(Artist.id == artist_id).all()

    if artists:
        for artist in artists:
            arrating = session.query(ArtistRating).filter(
                    ArtistRating.artist_id == artist.id,
                    ArtistRating.user_id == user_id).one_or_none()
            if arrating is None:
                arrating = ArtistRating(user_id=user_id, artist_id=artist.id)
                session.add(arrating)
            if arrating.rating is None or not arrating.pseudo_rating:
                continue
            albums = session.query(Album). \
                         filter(Album.artist_id == artist.id).all()
            pseudo = 0
            count = 0
            starred = None
            for album in albums:
                alrating = session.query(AlbumRating).filter(
                    AlbumRating.album_id == album.id,
                    AlbumRating.user_id == user_id).one_or_none()
                if alrating:
                    if alrating.rating is not None:
                        pseudo += alrating.rating
                    if alrating.starred is not None:
                        if starred is None or starred > alrating.starred:
                            # Extract the oldest starred date
                            starred = alrating.starred

                # Down rank for unrated albums
                count += 1
            if count:
                pseudo = round(float(pseudo) / float(count))
                arrating.rating = pseudo
                arrating.pseudo_rating = True
            if starred and arrating.pseudo_starred:
                arrating.starred = starred
                arrating.pseudo_starred = True


from . import auth, web   # noqa: E402


UN_TYPES = [DBInfo, User, Role, PlayQueue, PlayList, PlayListUser,
            PlayListTrack, ArtistRating, AlbumRating, TrackRating,
            PlayCount, Scrobble]

# insinuate self into mishmash's table lists so schema is setup correctly
mishmash.orm.TYPES.extend(UN_TYPES)
mishmash.orm.TABLES.extend([T.__table__ for T in UN_TYPES])
