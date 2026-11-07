#
# partcad-sketchfab, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""Tests of the Sketchfab plugin, with Sketchfab answered from a table.

The answers have the shape Sketchfab's Data API v3 answers with - models/<uid>,
search?type=models, models/<uid>/download, me - with the fields this reads and
some it does not, and values made up. Nothing here touches the network.
"""

import base64
import importlib.util
import io
import json
import os
import re
import runpy
import urllib.parse
import zipfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN = os.path.join(_HERE, "sketchfab_repo.py")
_SPEC = importlib.util.spec_from_file_location("sketchfab_repo_under_test", _PLUGIN)
plugin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(plugin)
rm = plugin.rm

API = "https://api.sketchfab.com/v3"
UID = "d3af66e9f74040508937b1dc81964f26"
OTHER = "83610a696ff64c7599ad65e9efd2d07c"
GLB_LINK = "https://sketchfab-prod-media.s3.amazonaws.com/archives/x/glb/model.glb?X-Amz-Signature=s"
SOURCE_LINK = "https://sketchfab-prod-media.s3.amazonaws.com/archives/x/source/bracket.zip?X-Amz-Signature=s"
GLB_BYTES = b"glTF\x02\x00\x00\x00 the rest of a binary glTF"
USER = {"uid": "u1", "username": "sinnervoncrawsz", "displayName": "Younique Idea Studio"}
LICENSE = {
    "uri": API + "/licenses/322a749bcfa841b29dff1e8a1bb74b0b",
    "label": "CC Attribution",
    "fullName": "Creative Commons Attribution",
    "url": "http://creativecommons.org/licenses/by/4.0/",
    "slug": "by",
}

DETAIL = {
    "uid": UID,
    "name": "Bracket for Nema 17",
    "viewerUrl": "https://sketchfab.com/3d-models/bracket-for-nema-17-" + UID,
    "user": USER,
    "license": LICENSE,
    "isDownloadable": True,
    "faceCount": 2616,
    "tags": [{"name": "nema17", "slug": "nema17"}],
}


def _hit(uid, name, glb=True, tags=()):
    archives = {"gltf": {"faceCount": 5232}, "usdz": {"faceCount": None}, "source": {"faceCount": None}}
    if glb:
        archives["glb"] = {"faceCount": 5232, "size": 163396, "type": "glb"}
    return {
        "uid": uid,
        "name": name,
        "viewerUrl": "https://sketchfab.com/3d-models/none-" + uid,
        "user": USER,
        "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b", "label": "CC Attribution"},
        "isDownloadable": True,
        "archives": archives,
        "tags": [{"name": t, "slug": t} for t in tags],
    }


def search_url(**fields):
    query = [("type", "models")]
    for key in ("q", "user", "downloadable", "file_format", "count", "archives_max_face_count"):
        if key in fields:
            query.append((key, fields[key]))
    return API + "/search?" + urllib.parse.urlencode(query)


def found_as(fmt, *hits):
    """What Sketchfab's search answers when the model is looked for by name and author, in a format."""
    return search_url(q=DETAIL["name"], user=USER["username"], downloadable="true", file_format=fmt, count=24), (
        200,
        {"results": list(hits), "next": None},
    )


def _zip(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buffer.getvalue()


class Wire:
    def __init__(self, table):
        self.table = table
        self.asked = []

    def __call__(self, url, headers=None, data=None, method=None, timeout=60):
        self.asked.append((url, dict(headers or {})))
        if url not in self.table:
            return rm.Response(404, {}, b'{"detail": "Not found."}', url)
        status, body = self.table[url]
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        return rm.Response(status, {}, body, url)


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setenv("PARTCAD_SKETCHFAB_CACHE", str(tmp_path))
    monkeypatch.delenv("SKETCHFAB_TOKEN", raising=False)
    monkeypatch.delenv("SKETCHFAB_OAUTH_TOKEN", raising=False)

    def make(token="", **parameters):
        made = plugin.Sketchfab({"parameters": {"token": token, **parameters}})
        made.http.request = Wire(
            dict(
                [
                    (API + "/models/" + UID, (200, DETAIL)),
                    found_as("stl", _hit(UID, DETAIL["name"])),
                    found_as("obj"),
                    (API + "/models/%s/download" % UID, (200, {"glb": {"url": GLB_LINK, "size": 1, "expires": 300}})),
                    (GLB_LINK, (200, GLB_BYTES)),
                ]
            )
        )
        return made

    return make


def test_a_model_is_the_gltf_binary_sketchfab_made_of_it(site):
    config = site().get("objects/part/" + UID)
    assert config["type"] == "gltf"
    assert config["path"].endswith("/sketchfab.glb")
    assert config["desc"] == "Bracket for Nema 17, on Sketchfab: the glTF binary Sketchfab made of it"
    assert config["url"] == "https://sketchfab.com/3d-models/bracket-for-nema-17-" + UID
    assert config["author"] == "Younique Idea Studio (@sinnervoncrawsz)"
    assert config["license"] == "CC BY 4.0"
    assert config["parameters"]["file"]["default"] == "glb"
    assert config["parameters"]["source"]["default"] == "preview"


def test_the_upload_is_had_by_asking_for_it(site):
    """Sketchfab's search says the model was uploaded as an STL; the glTF binary is still the default."""
    made = site()
    for name in (UID + ";format=stl", UID + ";source=original", UID + ";file=source.stl"):
        config = made.get("objects/part/" + name)
        assert config["type"] == "stl", name
        assert config["desc"] == "Bracket for Nema 17, on Sketchfab: the designer's upload, as STL"
        assert config["parameters"]["source"]["default"] == "original"


def test_what_the_model_was_not_uploaded_as_is_not_had(site, capsys):
    assert rm.serve(site(), "objects/part/%s;format=obj" % UID) is None
    assert "has no obj file (it has stl, glb (preview))" in capsys.readouterr().err


def test_the_plugins_formats_and_source_are_every_parts_default(site):
    assert site(formats="stl,obj").get("objects/part/" + UID)["type"] == "stl"
    assert site(source="original").get("objects/part/" + UID)["type"] == "stl"
    assert site(source="preview").get("objects/part/" + UID)["type"] == "gltf"
    # And a part's own asks for what the plugin's leave out.
    assert site(formats="stl").get("objects/part/%s;file=glb" % UID)["type"] == "gltf"


def test_an_upload_the_search_does_not_find_is_not_offered(site, capsys):
    made = site()
    made.http.request.table.update([found_as("stl")])
    assert rm.serve(made, "objects/part/%s;source=original" % UID) is None
    assert "has no original file" in capsys.readouterr().err


def test_a_model_its_author_tagged_noai_says_what_that_means(site):
    made = site()
    made.http.request.table[API + "/models/" + UID] = (200, {**DETAIL, "tags": [{"name": "noai", "slug": "noai"}]})
    desc = made.get("objects/part/" + UID)["desc"]
    assert desc.endswith(
        "Tagged NoAI by its author: Sketchfab's terms forbid using it in a generative AI's datasets "
        "or development, or as an input to one."
    )


def test_a_model_that_is_not_downloadable_says_so(site, capsys):
    made = site()
    made.http.request.table[API + "/models/" + UID] = (200, {**DETAIL, "isDownloadable": False})
    assert rm.serve(made, "objects/part/" + UID) is None
    assert "is not downloadable: its author has not made it so" in capsys.readouterr().err


def test_nonsense_costs_no_request(site, capsys):
    made = site()
    assert rm.serve(made, "objects/part/bracket-for-nema-17") is None
    assert made.http.request.asked == []
    assert "is not a Sketchfab model id" in capsys.readouterr().err


def test_the_details_and_the_search_are_asked_without_the_token(site):
    made = site(token="secret")
    made.get("objects/part/%s;format=stl" % UID)
    assert made.http.request.asked and all(headers == {} for _, headers in made.http.request.asked)


# --- downloading ---------------------------------------------------------------


def test_without_a_token_a_download_says_what_it_needs(site, capsys):
    made = site()
    config = made.get("objects/part/" + UID)
    assert rm.serve(made, "files/" + config["path"]) is None
    err = capsys.readouterr().err
    assert "takes a Sketchfab account, as every download from Sketchfab does" in err
    assert "https://sketchfab.com/settings/password" in err
    assert not any("/download" in url for url, _ in made.http.request.asked)


def test_the_gltf_binary_is_downloaded_with_the_api_token(site):
    made = site(token="secret")
    config = made.get("objects/part/" + UID)
    assert base64.b64decode(made.get("files/" + config["path"])) == GLB_BYTES
    asked = made.http.request.asked
    assert (API + "/models/%s/download" % UID, {"Authorization": "Token secret"}) in asked
    # The signed link is fetched without it.
    assert (GLB_LINK, {}) in asked


def test_an_oauth_token_is_sent_as_a_bearer_token(site):
    made = site(oauth_token="granted")
    config = made.get("objects/part/" + UID)
    made.get("files/" + config["path"])
    assert (API + "/models/%s/download" % UID, {"Authorization": "Bearer granted"}) in made.http.request.asked


def test_the_download_links_are_asked_for_every_time(site):
    """They are signed, and good for minutes."""
    made = site(token="secret")
    path = made.get("objects/part/" + UID)["path"]
    made.get("files/" + path)
    made.get("files/" + path)
    assert [url for url, _ in made.http.request.asked].count(API + "/models/%s/download" % UID) == 2


def test_the_upload_is_the_largest_file_of_its_format_in_its_archive(site):
    made = site(token="secret")
    made.http.request.table[API + "/models/%s/download" % UID] = (
        200,
        {"glb": {"url": GLB_LINK}, "source": {"url": SOURCE_LINK, "size": 3, "expires": 300}},
    )
    made.http.request.table[SOURCE_LINK] = (
        200,
        _zip({"bracket/bracket.stl": b"solid big" * 10, "bracket/screw.STL": b"solid", "readme.txt": b"hi"}),
    )
    config = made.get("objects/part/%s;format=stl" % UID)
    assert base64.b64decode(made.get("files/" + config["path"])) == b"solid big" * 10


def test_an_upload_that_is_not_an_archive_is_taken_as_it_is_when_its_name_agrees(site, capsys):
    made = site(token="secret")
    link = "https://media.example/source/bracket.stl?sig=1"
    made.http.request.table[API + "/models/%s/download" % UID] = (200, {"source": {"url": link}})
    made.http.request.table[link] = (200, b"solid bracket")
    path = made.get("objects/part/%s;format=stl" % UID)["path"]
    assert base64.b64decode(made.get("files/" + path)) == b"solid bracket"
    other = "https://media.example/source/bracket.blend?sig=1"
    made.http.request.table[API + "/models/%s/download" % UID] = (200, {"source": {"url": other}})
    made.http.request.table[other] = (200, b"BLENDER")
    assert rm.serve(made, "files/" + path) is None
    assert "the upload of model %s is 'bracket.blend', not STL" % UID in capsys.readouterr().err


def test_an_upload_sketchfab_does_not_hand_over_says_so(site, capsys):
    made = site(token="secret")
    path = made.get("objects/part/%s;format=stl" % UID)["path"]
    assert rm.serve(made, "files/" + path) is None
    err = capsys.readouterr().err
    assert "did not hand over the designer's upload of model %s (it offered glb)" % UID in err
    assert "'%s;file=glb' is the glTF binary" % UID in err


def test_a_token_sketchfab_does_not_take_is_said_so(site, capsys):
    made = site(token="stale")
    made.http.request.table[API + "/models/%s/download" % UID] = (401, {"detail": "Invalid API token"})
    path = made.get("objects/part/" + UID)["path"]
    assert rm.serve(made, "files/" + path) is None
    err = capsys.readouterr().err
    assert "Invalid API token" in err and "was not accepted" in err


def test_what_is_not_a_gltf_binary_is_not_handed_on(site, capsys):
    made = site(token="secret")
    made.http.request.table[GLB_LINK] = (200, b"<html>not a model</html>")
    path = made.get("objects/part/" + UID)["path"]
    assert rm.serve(made, "files/" + path) is None
    assert "is not a glTF binary" in capsys.readouterr().err


# --- searching -----------------------------------------------------------------


def test_a_search_needs_no_token_and_names_the_gltf_binaries(site):
    made = site()
    made.http.request.table[search_url(q="nema bracket", downloadable="true", count=24)] = (
        200,
        {
            "results": [
                _hit(UID, "Bracket for Nema 17"),
                _hit("0" * 32, "Not converted", glb=False),
                _hit(OTHER, "NEMA17 Plastic Bracket", tags=("noai",)),
            ],
            "next": None,
        },
    )
    hits = made.get("search/part?q=nema+bracket")
    assert list(hits) == [UID + ";file=glb", OTHER + ";file=glb"]
    first = hits[UID + ";file=glb"]
    assert first["type"] == "gltf" and first["license"] == "CC BY 4.0"
    assert first["url"] == "https://sketchfab.com/3d-models/bracket-for-nema-17-" + UID
    assert "Tagged NoAI" in hits[OTHER + ";file=glb"]["desc"]
    # One request: a hit is named from what the search said of it.
    assert len(made.http.request.asked) == 1


def test_a_search_asks_for_no_more_models_than_it_needs(site):
    made = site()
    page = search_url(q="bracket", downloadable="true", count=24)
    following = API + "/search?count=24&cursor=24&downloadable=true&q=bracket&type=models"
    made.http.request.table[page] = (
        200,
        {"results": [_hit("%032x" % i, "Bracket %d" % i) for i in range(24)], "next": following},
    )
    made.http.request.table[following] = (
        200,
        {"results": [_hit("%032x" % (100 + i), "Bracket %d" % i) for i in range(24)], "next": None},
    )
    assert len(made.get("search/part?q=bracket&limit=3")) == 3
    assert [url for url, _ in made.http.request.asked] == [page]
    assert len(made.get("search/part?q=bracket&limit=30")) == 30
    assert [url for url, _ in made.http.request.asked] == [page, following]


def test_a_search_for_uploads_asks_sketchfab_for_models_uploaded_so(site):
    made = site(formats="stl,obj")
    made.http.request.table[search_url(q="bracket", downloadable="true", file_format="stl", count=24)] = (
        200,
        {"results": [_hit(UID, "Bracket for Nema 17")], "next": None},
    )
    made.http.request.table[search_url(q="bracket", downloadable="true", file_format="obj", count=24)] = (
        200,
        {"results": [_hit(OTHER, "NEMA17 Plastic Bracket"), _hit(UID, "Bracket for Nema 17")], "next": None},
    )
    hits = made.get("search/part?q=bracket")
    # An upload that is both is one part in two formats, named by the better.
    assert list(hits) == [UID + ";file=source.stl", OTHER + ";file=source.obj"]
    assert hits[UID + ";file=source.stl"]["type"] == "stl"


def test_a_hit_that_does_not_say_what_it_has_is_read_from_its_details(site):
    made = site()
    hit = _hit(UID, "Bracket for Nema 17")
    del hit["archives"]
    made.http.request.table[search_url(q="nema", downloadable="true", count=24)] = (200, {"results": [hit]})
    assert list(made.get("search/part?q=nema")) == [UID + ";file=glb"]
    assert (API + "/models/" + UID, {}) in made.http.request.asked


def test_max_faces_keeps_a_search_to_models_of_that_many_triangles(site, capsys):
    made = site(max_faces="100000")
    url = search_url(q="gear", downloadable="true", count=24, archives_max_face_count="100000")
    made.http.request.table[url] = (200, {"results": [_hit(UID, "Gear")], "next": None})
    assert list(made.get("search/part?q=gear")) == [UID + ";file=glb"]
    assert rm.serve(site(max_faces="lots"), "search/part?q=gear") is None
    assert "'max_faces' is a number of triangles" in capsys.readouterr().err


# --- licences ------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        ({"label": "CC Attribution-NonCommercial-ShareAlike"}, "CC BY-NC-SA 4.0"),
        ({"label": "CC0 Public Domain"}, "CC0 1.0"),
        ({"url": "http://creativecommons.org/licenses/by-nd/4.0/", "label": "x"}, "CC BY-ND 4.0"),
        ({"slug": "ed", "label": "Editorial"}, "Sketchfab Editorial"),
        ({"label": "Something new"}, "Something new"),
        (None, None),
    ],
)
def test_a_licence_is_named_the_way_the_other_model_sites_name_it(value, expected):
    assert plugin._license(value) == expected


def test_a_name_is_spelled_in_an_address_the_way_sketchfab_spells_it():
    assert plugin.model_url(UID, "NEMA17  Plastic Bracket (L-Type)!") == (
        "https://sketchfab.com/3d-models/nema17-plastic-bracket-l-type-" + UID
    )
    assert plugin.model_url(UID, "") == "https://sketchfab.com/3d-models/none-" + UID


# --- logging in ----------------------------------------------------------------


def test_a_token_is_checked_by_asking_sketchfab_who_it_is(site):
    made = site()
    made.http.request.table[API + "/me"] = (200, {"username": "ann", "displayName": "Ann", "apiToken": "x"})
    assert made.whoami({"token": "a" * 32}) == "ann"
    assert made.http.request.asked[-1] == (API + "/me", {"Authorization": "Token " + "a" * 32})
    assert made.whoami({"token": "", "oauth_token": "granted"}) == "ann"
    assert made.http.request.asked[-1] == (API + "/me", {"Authorization": "Bearer granted"})
    made.http.request.table[API + "/me"] = (401, {"detail": "Invalid API token"})
    assert made.whoami({"token": "b" * 32}) is None
    assert made.whoami({"token": ""}) is None


def test_the_login_asks_for_the_api_token_on_the_page_that_shows_it(site):
    spec = site().login_spec()
    assert spec["url"] == "https://sketchfab.com/settings/password"
    capture = spec["capture"][0]
    assert capture["name"] == "token" and capture["ask"]["secret"] is True
    assert re.match(capture["match"], "0123456789abcdef0123456789abcdef")
    assert not re.match(capture["match"], "my password")


def test_with_an_oauth_application_the_login_is_an_implicit_grant(site):
    spec = site(client_id="abc", redirect_uri="http://127.0.0.1:8765/partcad/login/sketchfab").login_spec()
    assert spec["url"].startswith("https://sketchfab.com/oauth2/authorize/?")
    assert "response_type=token" in spec["url"] and "client_id=abc" in spec["url"]
    assert spec["capture"] == [
        {
            "name": "oauth_token",
            "redirect": {"url": "http://127.0.0.1:8765/partcad/login/sketchfab*", "param": "access_token"},
        }
    ]


class _BrowserNeeded(BaseException):
    pass


class _Callback:
    def open_browser(self, **spec):
        raise _BrowserNeeded(spec)


class _AgentCallback(_Callback):
    non_interactive = True


def test_partcad_runs_its_login_and_it_asks_for_the_browser(monkeypatch):
    monkeypatch.delenv("SKETCHFAB_TOKEN", raising=False)
    monkeypatch.delenv("SKETCHFAB_OAUTH_TOKEN", raising=False)
    with pytest.raises(_BrowserNeeded) as needed:
        runpy.run_path(
            _PLUGIN,
            init_globals={"request": {"api": "login", "parameters": {"token": ""}}, "partcad_login": _Callback()},
            run_name="login",
        )
    assert needed.value.args[0]["title"] == "Sketchfab"


def test_with_nobody_at_the_screen_the_login_asks_for_the_api_token_and_says_where_it_is(monkeypatch):
    """An OAuth grant's token is in the address of a page that never loads: no good to find by hand."""
    monkeypatch.delenv("SKETCHFAB_TOKEN", raising=False)
    monkeypatch.delenv("SKETCHFAB_OAUTH_TOKEN", raising=False)
    parameters = {"token": "", "client_id": "abc", "redirect_uri": "http://127.0.0.1:8765/cb"}
    with pytest.raises(_BrowserNeeded) as needed:
        runpy.run_path(
            _PLUGIN,
            init_globals={"request": {"api": "login", "parameters": parameters}, "partcad_login": _AgentCallback()},
            run_name="login",
        )
    spec = needed.value.args[0]
    assert spec["url"] == "https://sketchfab.com/settings/password"
    assert "Searching Sketchfab, and reading a model's details, take no token" in spec["instructions"]
    assert "SKETCHFAB_TOKEN" in spec["instructions"]


# --- the contract with PartCAD -------------------------------------------------


def test_partcad_runs_it_and_reads_the_answer_from_output():
    result = runpy.run_path(_PLUGIN, init_globals={"request": {"key": "meta", "parameters": {}}}, run_name="get")
    meta = result["output"]["result"]
    assert meta["manufacturable"] is False
    assert meta["searchKinds"] == ["part"] and meta["instanceKinds"] == ["part"]


def test_the_cache_version_is_a_literal_partcad_can_read():
    with open(_PLUGIN) as f:
        assert any(line.startswith("CACHE_VERSION = ") and line.split("=")[1].strip().isdigit() for line in f)


def test_the_shared_module_is_the_one_every_model_site_plugin_has():
    import hashlib

    with open(os.path.join(_HERE, "remote_models.py"), "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(os.path.join(_HERE, "remote_models.sha256")) as f:
        assert digest == f.read().split()[0], "remote_models.py differs from the shared copy: update all five"
