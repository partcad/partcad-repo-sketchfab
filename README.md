# Sketchfab for PartCAD

Serves Sketchfab's models as PartCAD parts, published as
`//pub/universe/sketchfab/models`.

**Nothing is listed.** A model site's catalog is not something to enumerate,
so `pc list parts` of this package is empty, as is `pc list packages`. A part is
asked for by name, and found with `pc search parts`:

```shell
pc search parts -P //pub/universe/sketchfab/models -k "nema 17 bracket"
pc inspect "//pub/universe/sketchfab/models:d3af66e9f74040508937b1dc81964f26"
```

**No geometry is vendored.** Every file is fetched from Sketchfab the first
time a part is built, and kept by PartCAD from then on.

**Every download takes a Sketchfab account.** Searching, and a model's details,
take nothing; a model's files - even the glTF binary Sketchfab makes of it -
take the API token of your own account. See [Logging in](#logging-in).

**Nothing here is manufacturable.** The package says `manufacturable: false`,
and so does the plugin of what it serves: an upload to a model site says
nothing about whether, or how, it is made to be made - and on Sketchfab it is
most often made to be looked at.

Requires PartCAD 0.9.3 or newer: the first release whose repository plugins
may search their own catalog (`searchKinds`), resolve a parametrized name
themselves (`instanceKinds`), and log in (`pc login`). They are described under
"Repositories" and "Logging in" in PartCAD's plugin documentation.

## Names

A model is a part per file of it that PartCAD reads, and the name says which.
A model is named by its uid, the 32 hexadecimal digits that end its address, as
in `sketchfab.com/3d-models/bracket-for-nema-17-d3af66e9f74040508937b1dc81964f26`:

| Name | Is |
| --- | --- |
| `<uid>` | the model's best file: the glTF binary Sketchfab made of it |
| `<uid>;file=glb` | that glTF binary, by name |
| `<uid>;format=stl` | the designer's upload, where it was an STL |
| `<uid>;source=original` | the designer's upload, where it was an STL or an OBJ |
| `<uid>;file=source.obj` | the designer's upload, read as an OBJ |

Any of them may be given together, and must then agree; `source` and the
plugin's own `formats` are under [Parameters](#parameters). Of the formats
PartCAD reads, Sketchfab has three:

| Format | Read as PartCAD part type | On Sketchfab |
| --- | --- | --- |
| `glb` | `gltf` | The glTF binary Sketchfab converts every downloadable model into: `file=glb`, or `source=preview`, since it is Sketchfab's own mesh of the model. |
| `stl` | `stl` | The designer's upload, where it was an STL: `file=source.stl`. |
| `obj` | `obj` | The designer's upload, where it was an OBJ: `file=source.obj`. |

Sketchfab takes no STEP, BREP, 3MF or OpenSCAD upload, so the rest of the
formats the other model sites are read in never come up here. Its glTF (an
archive of a `.gltf` and the files it names) is the same mesh as its glTF
binary, and is not served; its USDZ is a format PartCAD does not read. An upload
in any other format - FBX, Blender, PLY, IGES, 3ds Max - is not a part, and
neither is a GLB upload, which the glTF binary stands for.

**"Best" is the glTF binary.** Every downloadable model has one, and it is what
Sketchfab's API documents handing over. The designer's upload is chosen only
when a name asks for it - `format=stl`, `source=original`, `file=source.stl` -
or the plugin's `formats` leaves the glTF binary out: Sketchfab's own
documentation of its API says uploads are not served through it (see
[Status](#status)).

**What a model was uploaded as** is something Sketchfab says only through its
search, which takes the format to look for (`file_format`). So the plugin looks
a model up by its name and its author, as an STL and as an OBJ - two requests,
kept for a day - and offers the upload in the format it is found as. A model
the search does not find that way has no upload offered. An upload that is an
archive is served as its largest file of that format: an upload of several
files is one scene on Sketchfab, and a part is one file.

These names are resolved by the plugin rather than by PartCAD applying the
parameters to a base part, because another file is another `path` and maybe
another `type`. `pc info` of a part shows the `file` and `format` it resolved
to, which is what to write to pin it.

### What a Sketchfab model is, in PartCAD

Sketchfab is made for showing models, and most of what is on it is textured
meshes made to be rendered: scans, game assets, scenes. PartCAD reads the
triangles of a model, as it reads any glTF or STL - colours and textures are
dropped - and makes a face of every one of them. Four things follow, and the
first two decide whether a model is any use as a part:

- **Size.** PartCAD takes about a minute per hundred thousand triangles (a
  closed mesh of ten thousand built in 6 s, one of a hundred thousand in 73 s,
  where this was written). A model made to be looked at is often hundreds of
  thousands of them: the first 24 models a search for "gear" found had a
  median of about 76,000, and two had over a million. `max_faces` keeps a
  search to models of no more than it says.
- **Scale.** glTF states metres, and PartCAD reads a glTF binary in metres. A
  model drawn in millimetres, as anything made to be printed is, comes out a
  thousand times too large if Sketchfab's conversion kept its numbers, which
  Sketchfab does not document: a glTF binary shaped like Sketchfab's, twenty
  units across, came out 20,000 mm. An STL or an OBJ is read in millimetres,
  which is what makes the designer's upload worth asking for. `pc info` shows a
  part's bounding box.
- **Solids.** A mesh that does not close - a leaf, a ground plane, a scan with
  holes - is built with a warning that it is not a solid; a mesh that closes is
  one.
- **Orientation.** Sketchfab's glTF binaries put the model under a node that
  turns it from Z up to glTF's Y up, and PartCAD turns it back, so a model comes
  out the way up its author made it (seen with a file of that shape).

## Search

`pc search parts -k <words>` asks Sketchfab's own search for downloadable
models, with no token, and answers with names of the form above - one per
model, `<uid>;file=glb`, from what the search says of each, so a hit is
everything needed to fetch its geometry and a search is one request (a page of
24 models) unless more hits are asked for. A model Sketchfab could not convert
is not a hit. With `formats` leaving the glTF binary out (`stl,obj`), or
`source` set to `original`, it asks instead for the models uploaded in each of
those formats, and names their uploads (`<uid>;file=source.stl`); a model
uploaded as both is one part, named by its STL. `max_faces` leaves out the
models of more triangles than it says. `--limit` caps the hits (20 by default).

A search is never cached by PartCAD; the plugin keeps what the site answered for
ten minutes.

## Logging in

```shell
pc login //pub/universe/sketchfab:sketchfab_repo
```

checks the token the plugin has by asking Sketchfab whom it belongs to
(`api.sketchfab.com/v3/me`), and keeps it if Sketchfab still takes it.
Otherwise it opens your default browser, in PartCAD's own profile with
PartCAD's extension in it:

- **Without an OAuth application**, which is how it is, on
  <https://sketchfab.com/settings/password>, the page that shows a signed-in
  user their API token (signing in first, when you are not; the page comes back
  after). Copy the **API token**, and paste it into the PartCAD bar at the top
  of the page. Nothing is read off the page itself.
- **With an OAuth application** - `client_id` and `redirect_uri` set - on
  Sketchfab's authorization page. Sign in and allow it; Sketchfab sends the
  browser to the registered redirect URI with a token in the address (an
  implicit grant: no client secret is involved, which is what lets a public
  plugin use it), and the extension reads it off the address. The page never
  has to load. The token is kept as `oauth_token`, and lasts a month: an
  implicit grant has no refresh token, so `pc login` then asks again.

Sketchfab registers an OAuth application only when asked, through its help
center, with the application's name, its grant type and its redirect URI
(<https://sketchfab.com/developers/oauth>). PartCAD has none, so `client_id` is
empty and `pc login` asks for the API token; an application of your own works
the same way, set in your `~/.partcad/config.yaml`.

The token is saved in your `~/.partcad/config.yaml` as your override of the
repository's `token` (or `oauth_token`) parameter, which is where every later
command reads it from. `pc login --check ...` only checks it.

## Credentials, by hand

The API token is your own account's: sign in at <https://sketchfab.com>, open
<https://sketchfab.com/settings/password>, and copy the **API token** it shows.
Give it to the plugin either way, never in a package:

```shell
export SKETCHFAB_TOKEN=...        # read by the plugin; see the note on Docker below
```

```yaml
# ~/.partcad/config.yaml
parameters:
  "//pub/universe/sketchfab:sketchfab_repo":
    token: "..."
```

`pc --extra-param "//pub/universe/sketchfab:sketchfab_repo.token=..."` does
the same for one command. The token is sent to `api.sketchfab.com` as
`Authorization: Token ...` (an OAuth token as `Authorization: Bearer ...`), and
only to download a model or to check whom it is: a search and a model's details
are asked without it, and the files themselves are fetched from the signed links
Sketchfab hands back, without it.

What Sketchfab asks of an application that downloads is that the person
downloading is signed in to Sketchfab with an account of their own (its API
agreement, 4.6, and its terms of use, 4.2.4): that is what the token is. Keep it
to yourself.

**Docker.** PartCAD runs a plugin in its Python sandbox, and the `docker` sandbox
does not carry PartCAD's environment into its container, so an environment
variable does not reach the plugin there. The repository parameter does, being
part of what PartCAD hands the plugin; use that, or `pythonSandbox: venv`.

## Parameters

The plugin's parameters, declared in `partcad.yaml`, are a default for every
Sketchfab part:

| Parameter | Default | What it is |
| --- | --- | --- |
| `formats` | all, in the order above | The formats to take a model in, best first, separated by commas: `glb`, `stl`, `obj`. A format left out is not taken - `stl,obj` is the designer's uploads only, and searches for models uploaded so - unless a part asks for it by its own `format` or `file`. The glTF binary is still chosen before an upload when both are taken. |
| `source` | `auto` | Which of a model's files: `original` is the designer's upload, where it is an STL or an OBJ; `preview` is the glTF binary Sketchfab made of it; `auto` is the glTF binary, unless a part or `formats` asks for the upload. Every one of them takes a Sketchfab account to download. |
| `max_faces` | empty | The most triangles a model a search names may have, as Sketchfab counts them in its glTF binary. Empty is no limit; `100000` keeps a search to what PartCAD builds in about a minute. A part asked for by name is served whatever its size. |
| `token` | empty | The API token of your own Sketchfab account, which every download takes. `SKETCHFAB_TOKEN` gives it too. |
| `oauth_token` | empty | Instead of `token`: what an OAuth application was granted on your behalf. `pc login` gets it when `client_id` is set. `SKETCHFAB_OAUTH_TOKEN` gives it too. |
| `client_id` | empty | The OAuth application `pc login` signs in with, by an implicit grant, instead of asking for the API token. Empty: Sketchfab registers applications only on request, and PartCAD has none. Set it, with `redirect_uri`, to an application of your own. |
| `redirect_uri` | empty | The redirect URI registered with that application (Sketchfab takes `http://127.0.0.1:<port>/...`). It is never loaded. |

They are yours to set without touching this package - every one of them, the
credentials included, and the OAuth settings beside them:

- in your own `~/.partcad/config.yaml`, by the plugin's name, which is where
  `pc login` keeps the credentials:

  ```yaml
  parameters:
    "//pub/universe/sketchfab:sketchfab_repo":
      formats: stl,obj
      max_faces: "100000"
  ```

- or, for anything but the credentials, in a package of your own, as an enrich
  of the plugin and a package it serves - `//sketchfab_uploads:<uid>` in a
  package at the root:

  ```yaml
  repositories:
    uploads_repo:
      type: enrich
      source: //pub/universe/sketchfab:sketchfab_repo
      with:
        formats: stl,obj
  dependencies:
    sketchfab_uploads:
      type: external
      plugin: :uploads_repo
  ```

A part's own `file`, `format` and `source` override them for that part - in its
name (`d3af66e9f74040508937b1dc81964f26;format=stl`), or in the `with` of an
enrich of the part:

```yaml
parts:
  bracket:
    type: enrich
    source: //pub/universe/sketchfab/models:d3af66e9f74040508937b1dc81964f26
    with:
      format: stl
```

PartCAD keys what it caches of this package on your overrides of the plugin's
parameters, so a change to one - logging in, too - takes effect at once. An
environment variable is not seen there: after setting one, `pc update`
refreshes what was cached without it.

## Logging in with nobody at the screen

An AI agent, or a script, logs in without a browser:

```shell
pc login --agent //pub/universe/sketchfab:sketchfab_repo
pc login --agent --set token=... //pub/universe/sketchfab:sketchfab_repo
```

The first prints what a person would do in the browser instead of opening one -
where to sign in, what to copy, and the command that hands it over - and exits
with status 3. It asks for the API token, never an OAuth grant (whose token
lives in the address of a page that never loads), says where Sketchfab shows
it, and that searching needs none. The second hands over what the person found;
the plugin checks it with Sketchfab before PartCAD keeps it. `pc mcp`'s `login`
tool works the same way.

## Status

Run against the live API with PartCAD 0.9.6 from a checkout, without a
Sketchfab account:

- **Search**: `pc search parts` names downloadable models, with their licence,
  author and page; with `formats: stl` it names the STL uploads of models
  uploaded so, and with `max_faces` only models of so many triangles. Through
  an enrich of the plugin in another package, too.
- **A model's details**, and what it was uploaded as: `pc info
  "<uid>;format=stl"` of a model uploaded as an STL resolves to its upload,
  and stops at the download, saying it takes a token.
- **`pc login --agent`** prints the instructions above and exits with status 3;
  a wrong token handed over with `--set` is refused by `/v3/me`, and nothing is
  saved.

Not run, for want of an account, and written to what Sketchfab documents and
its API shows:

- **Downloading.** `models/<uid>/download`, with the token, answers with signed
  links good for minutes, `{"glb": {"url": ..., "expires": 300}, ...}`; the
  plugin takes `glb` for the glTF binary and `source` for the upload. Whether
  `source` is there is the open question: Sketchfab's Download API page says
  "Models are not currently available in their source formats such as FBX and
  OBJ through the API", while its search lists a `source` archive beside `glb`,
  `gltf` and `usdz` for every downloadable model looked at, and another client
  of the API offers it. If it is not handed over, a part of the upload fails saying so, and
  `<uid>;file=glb` is the way.
- **The glTF binaries themselves**: their scale (see above), and whether they
  use anything PartCAD's glTF reader refuses. They are not documented as
  Draco-compressed, as MakerWorld's previews are.
- **The token's shape**: the login takes 20 to 64 letters and digits.
- **`pc login` in a browser.** sketchfab.com's own pages answer anything but a
  browser with an AWS WAF challenge (HTTP 202, `x-amzn-waf-action: challenge`),
  so the guide's selectors are written to what is known of the pages rather
  than seen. A browser answers that challenge itself; the plugin never meets it,
  since it asks only `api.sketchfab.com`, which answers normally.

## Layout

| Path | Purpose |
| --- | --- |
| `partcad.yaml` | `//pub/universe/sketchfab`; the `models` external dependency and the `sketchfab_repo` repository that serves it. |
| `sketchfab_repo.py` | The repository plugin: how Sketchfab is asked. |
| `remote_models.py` | What every model-site plugin shares, byte for byte: the names, the formats, HTTP and its cache, the keys PartCAD asks. The same file is in partcad-repo-thingiverse, partcad-repo-makerworld, partcad-repo-grabcad, partcad-repo-printables and partcad-repo-cults3d, and here; `remote_models.sha256` is its digest, and a test fails when the two disagree - change it in all of them. |
| `test_*.py` | The tests. Nothing in them touches the network. |

```shell
python -m pytest
```

When what the plugin answers changes - here or in `remote_models.py` - raise
`CACHE_VERSION` in `sketchfab_repo.py`: PartCAD keys everything it caches of this
package on it.

## Caching

PartCAD keeps every answer the plugin gives, files included, under its own
cache, apart from a search. The plugin keeps what Sketchfab answered under
`~/.cache/partcad-sketchfab/` (or `$PARTCAD_SKETCHFAB_CACHE`): a model's details,
and what it was uploaded as, for a day; a search for ten minutes; the download
links never, since they are signed for minutes; and a request that came to
nothing for a while too, so that a refused or throttled run is not repeated in
full by the next one - a 404 for a day, anything else for five minutes. Delete
the directory to start over.

Every request says what it is: `User-Agent: Mozilla/5.0 (compatible;
PartCAD-sketchfab/<version>; +https://github.com/partcad/partcad-repo-sketchfab)`.

## Licensing

The code here is Apache-2.0 (`LICENSE`). Each model carries its own licence,
which the part states (`license`): a Creative Commons licence for every free
download - `CC BY 4.0`, `CC BY-SA 4.0`, `CC BY-ND 4.0`, `CC BY-NC 4.0`,
`CC BY-NC-SA 4.0`, `CC BY-NC-ND 4.0` or `CC0 1.0` - or Sketchfab's own
Standard or Editorial licence, for what its store sold. It is the designer's,
not this package's. The part also states its author (`author`, as Sketchfab
credits one: `Display Name (@username)`) and its page (`url`), and says in its
`desc` that it is on Sketchfab: that is what Sketchfab's API agreement (4.5,
4.7) asks an application to show of a model it downloads, and what its licence
asks of you wherever the model goes.

**NoAI.** A model its author tagged `NoAI` says so in its `desc`. Sketchfab's
terms of use (5, item 14) forbid using such a model in a generative AI's
datasets or development, or as an input to one. PartCAD serves AI agents too
(`pc mcp`); whether an agent reading such a part is that is for whoever runs it
to judge, and the plugin says what the tag means rather than decide.

**Sharing.** PartCAD's cache can be shared - a team's, in S3 - and what it holds
of a model is then handed to everyone who reads it. Sketchfab's terms (5, item
13) forbid collecting its content to make it available to others except as its
licence allows; the Creative Commons licences allow sharing with credit, and
Sketchfab's Standard and Editorial licences do not.

Sketchfab's terms of use are at <https://sketchfab.com/terms>, its API agreement
at <https://sketchfab.com/developers/terms>, and its guidelines for applications
that download at <https://sketchfab.com/developers/download-api/guidelines>.
Sketchfab has been KitBash's since August 2026, when KitBash bought it from Epic
Games; the terms of use quoted here took effect on 27 October 2026.
