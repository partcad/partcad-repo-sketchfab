#
# partcad-sketchfab, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""A PartCAD 'basic' repository plugin that serves Sketchfab models as parts.

Published as ``//pub/universe/sketchfab/models``. Nothing is listed: a part is
asked for by the model's uid - the 32 hexadecimal digits that end its address,
sketchfab.com/3d-models/<slug>-<uid> - and is one file of that model.

    <uid>                      the model's best file: the glTF binary Sketchfab made of it
    <uid>;file=glb             that glTF binary, by name
    <uid>;source=original      the designer's upload, when it is a format PartCAD reads
    <uid>;format=stl           the designer's upload, when it was an STL
    <uid>;file=source.obj      the designer's upload, read as OBJ

Sketchfab's search, and a model's details, are Sketchfab's to give anyone.
Every download takes a Sketchfab account: give the plugin the API token of your
own (sketchfab.com/settings/password) as SKETCHFAB_TOKEN, or as the repository's
'token' parameter, which 'pc login' sets (see the README).

PartCAD runs this script once per key (via runpy) with the key in
``request["key"]``; the answer goes in ``output``. What the keys mean, and
everything else that is the same for every model site, is in remote_models.py.
"""

import importlib.util
import io
import os
import re
import sys
import unicodedata
import urllib.parse
import zipfile

# When this plugin's answers stopped meaning what they meant before. PartCAD
# keys everything it caches of this package on it, so raise it with any change
# to what is answered - here or in remote_models.py.
#
# v1: models as parts, Sketchfab's glTF binary of each and the designer's upload
#     where it is an STL or an OBJ; 'formats' and 'source'; and 'login'.
CACHE_VERSION = 1


def _shared():
    """remote_models.py, beside this script, under a name of this plugin's own."""
    name = "_partcad_sketchfab_remote_models"
    if name not in sys.modules:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "remote_models.py")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


rm = _shared()

WEB = "https://sketchfab.com"
API = "https://api.sketchfab.com/v3"

# A model's uid: what ends its address, and all its API knows it by.
_UID = re.compile(r"^[0-9a-f]{32}$")

# The formats PartCAD reads that Sketchfab takes an upload in and that its
# search tells apart ('file_format'), which is how the plugin learns what a
# model was uploaded as without downloading it. Sketchfab takes no STEP, BREP,
# 3MF or OpenSCAD upload; a GLB upload is left to the glTF binary Sketchfab
# makes of every model, which holds the same triangles.
UPLOAD_FORMATS = ("stl", "obj")

# The most models one page of Sketchfab's search holds.
_PAGE = 24

# The glTF binary Sketchfab makes of every downloadable model, and the
# designer's upload: what the two kinds of file are called in a part's name.
GLB = "glb"
GLB_NAME = "sketchfab.glb"
UPLOAD = "source"

# The licences a model on Sketchfab is under, by their slug there (its
# /v3/licenses). The Creative Commons ones link to version 4.0; 'Standard' and
# 'Editorial' are Sketchfab's own, for what was sold in its store.
_LICENSES = {
    "by": "CC BY 4.0",
    "by-sa": "CC BY-SA 4.0",
    "by-nd": "CC BY-ND 4.0",
    "by-nc": "CC BY-NC 4.0",
    "by-nc-sa": "CC BY-NC-SA 4.0",
    "by-nc-nd": "CC BY-NC-ND 4.0",
    "cc0": "CC0 1.0",
    "free-st": "Sketchfab Free Standard",
    "st": "Sketchfab Standard",
    "ed": "Sketchfab Editorial",
}
# A search hit gives a licence by its label alone.
_SLUG_OF_LABEL = {
    "CC Attribution": "by",
    "CC Attribution-ShareAlike": "by-sa",
    "CC Attribution-NoDerivs": "by-nd",
    "CC Attribution-NonCommercial": "by-nc",
    "CC Attribution-NonCommercial-ShareAlike": "by-nc-sa",
    "CC Attribution-NonCommercial-NoDerivs": "by-nc-nd",
    "CC0 Public Domain": "cc0",
    "Free Standard": "free-st",
    "Standard": "st",
    "Editorial": "ed",
}
_CC = re.compile(r"creativecommons\.org/(?:licenses/([a-z-]+)|publicdomain/(zero))/(\d+(?:\.\d+)?)", re.IGNORECASE)

# What Sketchfab's terms say of a model its author tagged 'NoAI'.
_NOAI = (
    "Tagged NoAI by its author: Sketchfab's terms forbid using it in a generative AI's datasets or development, "
    "or as an input to one."
)


def model_url(model_id, name=None):
    """A model's page: '/3d-models/<slug>-<uid>', which Sketchfab finds by the uid whatever the slug."""
    return "%s/3d-models/%s-%s" % (WEB, _slug(name) or "none", model_id)


def _slug(name):
    """A name as Sketchfab spells it in an address (Django's 'slugify')."""
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[-\s]+", "-", re.sub(r"[^\w\s-]", "", text.lower())).strip("-_")


def _license(value):
    """'CC BY-SA 4.0' for a Creative Commons licence; Sketchfab's own by name."""
    if not isinstance(value, dict):
        return None
    found = _CC.search(value.get("url") or "")
    if found:
        kind, zero, version = found.groups()
        return "CC0 %s" % version if zero else "CC %s %s" % (kind.upper(), version)
    slug = value.get("slug") or _SLUG_OF_LABEL.get(value.get("label"))
    return _LICENSES.get(slug) or value.get("label") or value.get("fullName") or None


def _author(user):
    """A model's author as Sketchfab credits one: 'Display Name (@username)'."""
    if not isinstance(user, dict):
        return None
    name, username = user.get("displayName"), user.get("username")
    if name and username and name != username:
        return "%s (@%s)" % (name, username)
    return username or name or None


def _noai(tags):
    return any(
        isinstance(tag, dict) and str(tag.get("slug") or tag.get("name") or "").lower() == "noai" for tag in tags or []
    )


def _glb():
    return rm.File(GLB, GLB_NAME, fallback=True)


def _upload(fmt):
    return rm.File("%s.%s" % (UPLOAD, fmt), "%s.%s" % (UPLOAD, fmt))


def _extensions(fmt):
    return next(exts for name, _, exts in rm.FORMATS if name == fmt)


class Sketchfab(rm.Site):
    NAME = "sketchfab"
    TITLE = "Sketchfab"
    URL = WEB
    DESC = "Models on Sketchfab, a part per file, by the model's uid. Nothing is listed; search instead."
    VERSION = CACHE_VERSION
    # The glTF binary Sketchfab makes of every downloadable model is its own
    # mesh of it, which is what 'source: preview' means.
    PREVIEWS = True
    # Unlike other sites' previews it is not coarser, and it needs the token
    # like every download.
    PREVIEW_DESCRIPTION = "the glTF binary %s makes of every downloadable model, which needs a token like any download"
    LOGIN_INSTRUCTIONS = (
        "Searching Sketchfab, and reading a model's details, take no token; every download does, the glTF binary "
        "Sketchfab makes of a model included. The token is the API token of your own Sketchfab account: sign in at "
        "https://sketchfab.com, and copy the API token https://sketchfab.com/settings/password shows (under "
        "'Password & API')."
    )

    # 'token' is an API token, sent as 'Authorization: Token'; 'oauth_token' is
    # what an OAuth application was granted, sent as 'Authorization: Bearer'.
    CREDENTIALS = {"token": "SKETCHFAB_TOKEN", "oauth_token": "SKETCHFAB_OAUTH_TOKEN"}

    def __init__(self, request=None):
        super().__init__(request)
        # The OAuth application 'pc login' signs in with, when there is one:
        # its client id and the callback it registered. Not credentials - an
        # implicit grant takes no client secret - so they are the package's
        # parameters, and anybody's to set to an application of their own.
        parameters = self.request.get("parameters") or {}
        self.client_id = str(parameters.get("client_id") or "").strip()
        self.redirect_uri = str(parameters.get("redirect_uri") or "").strip()
        # The most triangles a model a search names may have, in the glTF
        # binary Sketchfab made of it; empty is no limit. A model made to be
        # looked at is often a million of them, and PartCAD makes a face of
        # each.
        self.max_faces = str(parameters.get("max_faces") or "").strip()

    def valid_id(self, model_id):
        return bool(_UID.match(model_id))

    def usable(self, file):
        # What Sketchfab's API documents serving is its own glTF binary of a
        # model; of the designer's upload, its documentation says the API does
        # not serve it. So the upload is chosen only when asked for - by
        # 'source', 'format', 'file' or the plugin's 'formats' - and never
        # instead of the glTF binary.
        return file.fallback

    # -- credentials --

    @staticmethod
    def _authorization(credentials):
        if credentials.get("token"):
            return {"Authorization": "Token " + credentials["token"]}
        if credentials.get("oauth_token"):
            return {"Authorization": "Bearer " + credentials["oauth_token"]}
        return None

    def whoami(self, credentials):
        authorization = self._authorization(credentials)
        if not authorization:
            return None
        status, me = self.http.probe(API + "/me", "who the Sketchfab token is", headers=authorization)
        if status in (401, 403):
            return None
        if status != 200 or not isinstance(me, dict):
            raise rm.SiteError("sketchfab: asking who the token is answered HTTP %d" % status)
        return me.get("username") or me.get("displayName") or "a Sketchfab user"

    def login_spec(self):
        # With nobody at the screen, the token has to be found by hand, and the
        # API token is what a person can find: an OAuth grant's lives in the
        # address of a page that never loads.
        if self.client_id and self.redirect_uri and not self.non_interactive:
            # OAuth, implicit: Sketchfab sends the browser to the registered
            # callback with the token in the fragment. That page never has to
            # load; the extension reads the token off the address it was sent to.
            return {
                "url": "%s/oauth2/authorize/?%s"
                % (
                    WEB,
                    urllib.parse.urlencode(
                        {"response_type": "token", "client_id": self.client_id, "redirect_uri": self.redirect_uri}
                    ),
                ),
                "title": "Sketchfab",
                "capture": [
                    {"name": "oauth_token", "redirect": {"url": self.redirect_uri + "*", "param": "access_token"}}
                ],
                "guide": [
                    {
                        "url": "https://sketchfab.com/login*",
                        "selector": "input[type=email], input[name=email]",
                        "text": "Sign in to Sketchfab",
                    },
                    {
                        "url": "https://sketchfab.com/oauth2/authorize*",
                        "selector": "button[type=submit], input[type=submit]",
                        "text": "Let PartCAD download models with your Sketchfab account",
                    },
                ],
            }
        # The account's own API token, which Sketchfab shows its owner on the
        # settings page; it is pasted into the extension's bar.
        return {
            "url": "%s/settings/password" % WEB,
            "title": "Sketchfab",
            "capture": [
                {
                    "name": "token",
                    "ask": {"label": "Your Sketchfab API token, shown on this page", "secret": True},
                    "match": "^[A-Za-z0-9]{20,64}$",
                }
            ],
            "guide": [
                {
                    # Not signed in, the settings page sends the browser here first.
                    "url": "https://sketchfab.com/login*",
                    "selector": "input[type=email], input[name=email]",
                    "text": "Sign in to Sketchfab; you come back to your settings after",
                },
                {
                    "url": "https://sketchfab.com/settings/password*",
                    "selector": "label, h2, h3, h4, dt, th, legend, span",
                    "contains": "^\\s*api token\\s*$",
                    "text": "Copy your API token, and paste it into the PartCAD bar",
                },
            ],
        }

    # -- a model --

    def _model(self, hit, files=None):
        """A Model out of what Sketchfab says of one, in its details or in a search."""
        uid = str(hit.get("uid"))
        model = rm.Model(
            uid,
            title=hit.get("name"),
            # A search hit's own link is '/3d-models/none-<uid>'.
            url=model_url(uid, hit.get("name")),
            author=_author(hit.get("user")),
            license=_license(hit.get("license")),
            files=files,
        )
        model.noai = _noai(hit.get("tags"))
        return model

    def model(self, model_id):
        detail = self.http.json("%s/models/%s" % (API, model_id), "model %s" % model_id)
        if not isinstance(detail, dict) or detail.get("uid") != model_id:
            raise rm.NotFound("sketchfab: model %s: not found" % model_id)
        if not detail.get("isDownloadable"):
            raise rm.NotFound(
                "sketchfab: model %s (%s) is not downloadable: its author has not made it so"
                % (model_id, detail.get("name") or "untitled")
            )
        return self._model(detail, [_glb()] + [_upload(fmt) for fmt in self._uploaded_as(detail)])

    def _uploaded_as(self, detail):
        """The formats of UPLOAD_FORMATS the model was uploaded in, as Sketchfab's search says.

        Sketchfab says what a model was uploaded as only to its search, which
        takes the format to look for ('file_format'): so the model is looked
        for by its name and its author, in each format, and is that format if
        it is found. Not finding it says nothing, so the upload is then not
        offered at all.
        """
        username = (detail.get("user") or {}).get("username")
        if not username:
            return []
        found = []
        for fmt in UPLOAD_FORMATS:
            query = [("type", "models"), ("q", (detail.get("name") or "")[:100]), ("user", username)]
            query += [("downloadable", "true"), ("file_format", fmt), ("count", _PAGE)]
            answer = self.http.json(
                "%s/search?%s" % (API, urllib.parse.urlencode(query)),
                "what model %s was uploaded as" % detail["uid"],
            )
            if any(isinstance(hit, dict) and hit.get("uid") == detail["uid"] for hit in _results(answer)):
                found.append(fmt)
        return found

    def part_config(self, model, file):
        config = super().part_config(model, file)
        title = model.title or "Sketchfab model %s" % model.id
        if file.fallback:
            config["desc"] = "%s, on Sketchfab: the glTF binary Sketchfab made of it" % title
        else:
            config["desc"] = "%s, on Sketchfab: the designer's upload, as %s" % (title, file.format.upper())
        if getattr(model, "noai", False):
            config["desc"] += ". " + _NOAI
        return config

    # -- its files --

    def download(self, model, file):
        what = "%s of model %s" % (file.name, model.id)
        authorization = self._authorization(self.credentials())
        if not authorization:
            raise rm.NeedsCredentials(
                "sketchfab: %s takes a Sketchfab account, as every download from Sketchfab does: set "
                "SKETCHFAB_TOKEN, or the 'token' parameter of the repository, to the API token "
                "https://sketchfab.com/settings/password shows you ('pc login' sets it; see the README)" % what
            )
        try:
            # Not cached: the links are signed, and good for minutes.
            links = self.http.json(
                "%s/models/%s/download" % (API, model.id),
                "the downloads of model %s" % model.id,
                headers=authorization,
                ttl=0,
            )
        except rm.NeedsCredentials as e:
            raise rm.NeedsCredentials(
                "%s. The Sketchfab token in SKETCHFAB_TOKEN or the 'token' parameter was not accepted; "
                "'pc login' checks it" % e
            )
        offered = (
            sorted(k for k, v in links.items() if isinstance(v, dict) and v.get("url"))
            if isinstance(links, dict)
            else []
        )
        key = GLB if file.fallback else UPLOAD
        link = links[key]["url"] if key in offered else None
        if not link:
            if key == UPLOAD:
                raise rm.SiteError(
                    "sketchfab: Sketchfab did not hand over the designer's upload of model %s (it offered %s); "
                    "its API documentation says uploads are not served through it. '%s;file=%s' is the glTF "
                    "binary Sketchfab made of it" % (model.id, ", ".join(offered) or "nothing", model.id, GLB)
                )
            raise rm.SiteError(
                "sketchfab: Sketchfab has no glTF binary of model %s to hand over (it offered %s)"
                % (model.id, ", ".join(offered) or "nothing")
            )
        # The link is signed; the token is not sent along with it.
        data = self.http.download(link, what)
        if file.fallback:
            return _glb_of(data, what)
        return _upload_of(data, file, link, model.id)

    # -- searching --

    def search(self, text, limit):
        # Every downloadable model has a glTF binary, so a model is a hit as
        # it is found, with no request for its files: the search asks for no
        # more of them than the hits it is to answer with.
        wanted = -(-limit // rm.OVERSAMPLE)
        formats, source = self.preferences()
        if GLB in formats and source != "original":
            return self._search(text, wanted, None)
        # What is wanted is the designer's upload: Sketchfab's search finds the
        # models uploaded in each format there is to take.
        models = {}
        for fmt in (f for f in formats if f in UPLOAD_FORMATS) if source != "preview" else ():
            for model in self._search(text, wanted, fmt):
                if model.id in models:
                    models[model.id].files += [
                        f for f in model.files if f.id not in {g.id for g in models[model.id].files}
                    ]
                else:
                    models[model.id] = model
        return list(models.values())

    def _search(self, text, wanted, fmt):
        """Up to 'wanted' downloadable models Sketchfab finds for 'text', uploaded as 'fmt' when it is given."""
        query = [("type", "models"), ("q", text), ("downloadable", "true")]
        if fmt:
            query.append(("file_format", fmt))
        query.append(("count", _PAGE))
        if self.max_faces:
            if not self.max_faces.isdigit():
                raise rm.SiteError("sketchfab: 'max_faces' is a number of triangles, not '%s'" % self.max_faces)
            query.append(("archives_max_face_count", self.max_faces))
        url = "%s/search?%s" % (API, urllib.parse.urlencode(query))
        models = []
        for _ in range(-(-rm.MAX_LIMIT // _PAGE)):
            answer = self.http.json(url, "a search for '%s'" % text, ttl=600)
            for hit in _results(answer):
                if not isinstance(hit, dict) or not _UID.match(str(hit.get("uid") or "")):
                    continue
                archives = hit.get("archives")
                if fmt:
                    # Found by what it was uploaded as, which is what is wanted.
                    files = [_upload(fmt)]
                elif isinstance(archives, dict):
                    if not archives.get(GLB):
                        continue  # Sketchfab could not convert it
                    files = [_glb()]
                else:
                    files = None  # the details say, when it is a hit
                models.append(self._model(hit, files))
                if len(models) >= wanted:
                    return models
            url = answer.get("next") if isinstance(answer, dict) else None
            if not url or not str(url).startswith(API + "/"):
                break
        return models


def _results(answer):
    results = answer.get("results") if isinstance(answer, dict) else None
    return results if isinstance(results, list) else []


def _glb_of(data, what):
    """The '.glb' in what Sketchfab handed over: the file itself, or the one in an archive."""
    if rm.is_zip(data):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            meshes = sorted(n for n in z.namelist() if n.lower().endswith(".glb"))
            if not meshes:
                raise rm.SiteError("sketchfab: %s is an archive with no '.glb' in it" % what)
            data = z.read(meshes[0])
    if data[:4] != b"glTF":
        raise rm.SiteError("sketchfab: what Sketchfab handed over as %s is not a glTF binary" % what)
    return data


def _upload_of(data, file, link, model_id):
    """The file of the designer's upload in 'file.format': the upload itself, or the largest such in its archive."""
    extensions = _extensions(file.format)
    if rm.is_zip(data):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            members = [
                m
                for m in z.infolist()
                if not m.is_dir()
                and not m.filename.startswith("__MACOSX/")
                and m.filename.rsplit(".", 1)[-1].lower() in extensions
            ]
            if not members:
                raise rm.NotFound(
                    "sketchfab: the upload of model %s holds no %s file (it holds %s)"
                    % (model_id, file.format.upper(), ", ".join(z.namelist()[:10]) or "nothing")
                )
            # An upload of several is one scene on Sketchfab; a part is one
            # file, and the largest is taken to be the model.
            return z.read(max(members, key=lambda m: (m.file_size, m.filename)).filename)
    name = urllib.parse.unquote(urllib.parse.urlsplit(link).path.rsplit("/", 1)[-1])
    # A link whose name says nothing of its format is taken at its word.
    _, dot, extension = name.rpartition(".")
    if dot and extension.lower() not in extensions:
        raise rm.SiteError("sketchfab: the upload of model %s is '%s', not %s" % (model_id, name, file.format.upper()))
    return data


def get(key):
    return rm.serve(Sketchfab(globals().get("request")), key)


# Last, so that everything above is defined when PartCAD runs this.
if __name__ == "get":
    output = {"result": get(request["key"])}  # noqa: F821 - injected by the runtime
elif __name__ == "login":
    output = {"result": rm.login(Sketchfab(globals().get("request")), globals().get("partcad_login"))}
else:
    output = {}
