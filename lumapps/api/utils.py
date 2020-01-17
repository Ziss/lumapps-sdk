import os

try:
    import sqlite3
except ImportError:
    sqlite3 = None

from typing import Any, Dict, List, Optional
from json import loads, dumps
from datetime import datetime, timedelta

from lumapps.api.conf import __pypi_packagename__

CACHE_MAX_AGE = timedelta(seconds=60 * 60 * 24)  # 1 day
GOOGLE_APIS = ("drive", "admin", "groupssettings")
FILTERS = {
    # content/get, content/list, ...
    "content/*": [
        "lastRevision",
        "authorDetails",
        "updatedByDetails",
        "writerDetails",
        "headerDetails",
        "customContentTypeDetails",
        "properties/duplicateContent",
        "excerpt",
    ],
    # community/get, community/list, ...
    "community/*": [
        "lastRevision",
        "authorDetails",
        "updatedByDetails",
        "writerDetails",
        "headerDetails",
        "customContentTypeDetails",
        "adminsDetails",
        "usersDetails",
    ],
    "communitytemplate/*": [
        "lastRevision",
        "authorDetails",
        "updatedByDetails",
        "writerDetails",
        "headerDetails",
        "customContentTypeDetails",
        "adminsDetails",
        "usersDetails",
    ],
    # template/get, template/list, ...
    "template/*": ["properties/duplicateContent"],
    "community/post/*": [
        "authorDetails",
        "updatedByDetails",
        "mentionsDetails",
        "parentContentDetails",
        "headerDetails",
        "tagsDetails",
        "excerpt",
    ],
    "comment/get": ["authorProperties", "mentionsDetails"],
    "comment/list": ["authorProperties", "mentionsDetails"],
}


def pop_matches(dpath, d):
    if not dpath:
        return
    for pth_part in dpath.split("/")[:-1]:
        if not isinstance(d, dict):
            return
        d = d.get(pth_part)
    if not isinstance(d, dict):
        return
    d.pop(dpath.rpartition("/")[2], None)


def get_conf_db_file() -> str:
    if "APPDATA" in os.environ:
        d = os.environ["APPDATA"]
    elif "XDG_CONFIG_HOME" in os.environ:
        d = os.environ["XDG_CONFIG_HOME"]
    else:
        d = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(d, "{}.db".format(__pypi_packagename__))


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_conf_db_file())
    conn.isolation_level = None
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS discovery_cache (
            url TEXT NOT NULL,
            expiry TEXT NOT NULL,
            content TEXT NOT NULL,
            PRIMARY KEY (url)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS config (
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            PRIMARY KEY (name)
        )"""
    )
    return conn


def get_discovery_cache(url: str) -> Optional[Dict[str, Any]]:
    try:
        return (
            _get_conn()
            .execute("SELECT * FROM discovery_cache WHERE url=?", (url,))
            .fetchone()
        )
    except sqlite3.OperationalError:
        return None


def set_discovery_cache(url: str, expiry: Any, content: Any) -> None:
    try:
        _get_conn().execute(
            "INSERT OR REPLACE INTO discovery_cache VALUES (?, ?, ?)",
            (url, expiry, content),
        )
    except sqlite3.OperationalError:
        pass


def get_config(name: str) -> Optional[Dict[str, Any]]:
    try:
        row = (
            _get_conn()
            .execute("SELECT content FROM config WHERE name=?", (name,))
            .fetchone()
        )
    except sqlite3.OperationalError:
        return None
    return loads(row[0]) if row else None


def get_config_names():
    try:
        return [r[0] for r in _get_conn().execute("SELECT name FROM config")]
    except sqlite3.OperationalError:
        return []


def set_config(name: str, content: Any) -> None:
    try:
        _get_conn().execute(
            "INSERT OR REPLACE INTO config VALUES (?, ?)",
            (name, dumps(content, indent=4)),
        )
    except sqlite3.OperationalError:
        pass


class _DiscoveryCacheDict(object):
    _cache = {}

    @staticmethod
    def get(url):
        cached = _DiscoveryCacheDict._cache.get(url)
        if not cached or cached["expiry"] < datetime.now():
            return None
        return cached["content"]

    @staticmethod
    def set(url, content):
        expiry = datetime.now() + CACHE_MAX_AGE
        _DiscoveryCacheDict._cache[url] = {"expiry": expiry, "content": content}


class _DiscoveryCacheSqlite(object):
    @staticmethod
    def get(url):
        cached = get_discovery_cache(url)
        if not cached:
            return None
        expiry_dt = datetime.strptime(cached["expiry"][:19], "%Y-%m-%dT%H:%M:%S")
        if expiry_dt < datetime.now():
            return None
        return cached["content"]

    @staticmethod
    def set(url, content):
        expiry = (datetime.now() + CACHE_MAX_AGE).isoformat()[:19]
        set_discovery_cache(url, expiry, content)


if os.getenv("GAE_ENV") or sqlite3 is None:
    DiscoveryCache = _DiscoveryCacheDict
else:
    DiscoveryCache = _DiscoveryCacheSqlite


def list_prune_filters():
    s = ""
    for f in FILTERS:
        s += "\nMethods " + f + "\n"
        for pth in sorted(FILTERS[f]):
            s += "    " + pth + "\n"
    print("PRUNE FILTERS:\n" + s)


def _parse_endpoint_parts(parts):
    if len(parts) == 1:
        parts = parts[0].split("/")
    return parts


def _extract_from_discovery_spec(
    resources: Dict[str, Any], name_parts: List[str]
) -> Dict[str, Any]:
    getted = None
    for i, part in enumerate(name_parts):
        if i == len(name_parts) - 2:
            getted = resources.get(part, {})
        elif i == len(name_parts) - 1:
            if not getted:
                getted = resources.get(part, {}).get("methods", {})
            getted = getted.get("methods", {}).get(part, {})
        else:
            if not getted:
                getted = resources.get(part, {}).get("resources", {})
            getted = getted.get(part, {}).get("resources", {})
    return getted
