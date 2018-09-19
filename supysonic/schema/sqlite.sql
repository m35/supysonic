CREATE TABLE IF NOT EXISTS folder (
    id CHAR(36) PRIMARY KEY,
    root BOOLEAN NOT NULL,
    name VARCHAR(256) NOT NULL COLLATE NOCASE,
    path VARCHAR(4096) NOT NULL,
    path_hash BLOB NOT NULL,
    created DATETIME NOT NULL,
    cover_art VARCHAR(256),
    last_scan INTEGER NOT NULL,
    parent_id CHAR(36) REFERENCES folder
);

CREATE UNIQUE INDEX IF NOT EXISTS index_folder_path ON folder(path_hash);

CREATE TABLE IF NOT EXISTS artist (
    id CHAR(36) PRIMARY KEY,
    name VARCHAR(256) NOT NULL COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS album (
    id CHAR(36) PRIMARY KEY,
    name VARCHAR(256) NOT NULL COLLATE NOCASE,
    artist_id CHAR(36) NOT NULL REFERENCES artist
);

CREATE TABLE IF NOT EXISTS track (
    id CHAR(36) PRIMARY KEY,
    disc INTEGER NOT NULL,
    number INTEGER NOT NULL,
    title VARCHAR(256) NOT NULL COLLATE NOCASE,
    year INTEGER,
    genre VARCHAR(256),
    duration INTEGER NOT NULL,
    album_id CHAR(36) NOT NULL REFERENCES album,
    artist_id CHAR(36) NOT NULL REFERENCES artist,
    bitrate INTEGER NOT NULL,
    path VARCHAR(4096) NOT NULL,
    path_hash BLOB NOT NULL,
    content_type VARCHAR(32) NOT NULL,
    created DATETIME NOT NULL,
    last_modification INTEGER NOT NULL,
    play_count INTEGER NOT NULL,
    last_play DATETIME,
    root_folder_id CHAR(36) NOT NULL REFERENCES folder,
    folder_id CHAR(36) NOT NULL REFERENCES folder
);

CREATE UNIQUE INDEX IF NOT EXISTS index_track_path ON track(path_hash);

CREATE TABLE IF NOT EXISTS user (
    id CHAR(36) PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    mail VARCHAR(256),
    password CHAR(40) NOT NULL,
    salt CHAR(6) NOT NULL,
    admin BOOLEAN NOT NULL,
    lastfm_session CHAR(32),
    lastfm_status BOOLEAN NOT NULL,
    last_play_id CHAR(36) REFERENCES track,
    last_play_date DATETIME
);

CREATE TABLE IF NOT EXISTS client_prefs (
    user_id CHAR(36) NOT NULL,
    client_name VARCHAR(32) NOT NULL,
    format VARCHAR(8),
    bitrate INTEGER,
    PRIMARY KEY (user_id, client_name)
);

CREATE TABLE IF NOT EXISTS starred_folder (
    user_id CHAR(36) NOT NULL REFERENCES user,
    starred_id CHAR(36) NOT NULL REFERENCES folder,
    date DATETIME NOT NULL,
    PRIMARY KEY (user_id, starred_id)
);

CREATE TABLE IF NOT EXISTS starred_artist (
    user_id CHAR(36) NOT NULL REFERENCES user,
    starred_id CHAR(36) NOT NULL REFERENCES artist,
    date DATETIME NOT NULL,
    PRIMARY KEY (user_id, starred_id)
);

CREATE TABLE IF NOT EXISTS starred_album (
    user_id CHAR(36) NOT NULL REFERENCES user,
    starred_id CHAR(36) NOT NULL REFERENCES album,
    date DATETIME NOT NULL,
    PRIMARY KEY (user_id, starred_id)
);

CREATE TABLE IF NOT EXISTS starred_track (
    user_id CHAR(36) NOT NULL REFERENCES user,
    starred_id CHAR(36) NOT NULL REFERENCES track,
    date DATETIME NOT NULL,
    PRIMARY KEY (user_id, starred_id)
);

CREATE TABLE IF NOT EXISTS rating_folder (
    user_id CHAR(36) NOT NULL REFERENCES user,
    rated_id CHAR(36) NOT NULL REFERENCES folder,
    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    PRIMARY KEY (user_id, rated_id)
);

CREATE TABLE IF NOT EXISTS rating_track (
    user_id CHAR(36) NOT NULL REFERENCES user,
    rated_id CHAR(36) NOT NULL REFERENCES track,
    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    PRIMARY KEY (user_id, rated_id)
);

CREATE TABLE IF NOT EXISTS track_extra_meta_data (
    track_id CHAR(36) NOT NULL REFERENCES track,
    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    PRIMARY KEY (track_id)
);

CREATE TABLE IF NOT EXISTS chat_message (
    id CHAR(36) PRIMARY KEY,
    user_id CHAR(36) NOT NULL REFERENCES user,
    time INTEGER NOT NULL,
    message VARCHAR(512) NOT NULL
);

CREATE TABLE IF NOT EXISTS playlist (
    id CHAR(36) PRIMARY KEY,
    user_id CHAR(36) NOT NULL REFERENCES user,
    name VARCHAR(256) NOT NULL COLLATE NOCASE,
    comment VARCHAR(256),
    public BOOLEAN NOT NULL,
    created DATETIME NOT NULL,
    tracks TEXT
);

CREATE TABLE meta (
    key CHAR(32) PRIMARY KEY,
    value CHAR(256) NOT NULL
);

