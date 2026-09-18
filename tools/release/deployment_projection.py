"""Assemble and freeze the read-only Cloudflare deployment projection.

The `runtime` / `creator` steps dispatch a Host deploy and then verify the run's
retained evidence field by field against a frozen projection. Freezing is the
point rather than a convenience: the projection binds what production served
*before* the dispatch, and the deployment replaces exactly that, so re-deriving
it afterwards would compare the release against itself and every resume would
report drift. The first assembly writes the document beside the prepared
output; every later read answers those same bytes.

Everything except the replaced Worker version is derived from local release
inputs the operator already holds: the prepared plan document, the staged Host
archive it names, and one unauthenticated read of the public origin. The
replaced version's identity needs a Cloudflare API token, which the authorized
operator has and this module never invents: without it, and with an
unreadable prepared output or origin, the projection is `None` and the step
stays `pending`.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

from .batch_reference import digest, sha
from .model import canonical_json, canonical_sha256
from .orchestration import JournalError
from .profiles import CREATOR_WEB_SPEC, WEB_RUNTIME_SPEC

# The deploy steps and the Host each one deploys.
HOSTS = {"runtime": "web-runtime-host", "creator": "creator-web"}
# Taken from the release profiles that name the archives, so the projection
# cannot start looking for a filename the build no longer produces.
ARCHIVE_PREFIXES = {spec.host_id: spec.archive_prefix
                    for spec in (WEB_RUNTIME_SPEC, CREATOR_WEB_SPEC)}
ENTRY = "dist/index.html"
MANIFEST = "dist/host-manifest.json"
# A Web Host release archive, not a retained evidence archive: this bounds the
# size of a staged asset this module will touch at all, so a corrupt or hostile
# archive cannot make a read-only step consume the machine. The archive is read
# twice — once streamed to check its digest, once opened by `zipfile` for the
# two entry files — because a zip's directory needs random access and cannot be
# hashed in the same pass. The bound is on the archive, not on total I/O.
LIMIT = 256 * 1024 * 1024
# The two entry files are an HTML page and a JSON manifest. Bounding them by
# the archive's size would let the two of them together decompress to twice it;
# this is what an entry point can plausibly be, applied to each.
ENTRY_LIMIT = 8 * 1024 * 1024
_FIELDS = ("target_revision", "product_build", "host_version", "site_id",
           "archive", "release_files", "prior", "prior_site_sha256")


def _fail(reason):
    raise JournalError(
        f"why: the frozen deployment projection {reason}; remedy: reconcile "
        "the prepared release output, the live origin and the Worker "
        "deployment before dispatching this Host")


def output_relative(tag, step):
    """Where this step's frozen projection lives, under the prepared output."""
    from .prepared_step import output_relative as prepared_output

    if step not in HOSTS:
        _fail(f"names an unknown deployment step {step!r}")
    return prepared_output(tag) / "deployment" / f"{step}.json"


def validate(projection):
    """Exactly the shape `DeploymentEffect` compares against, or fail closed."""
    # `sha` and `digest` are the same readers `DeploymentEffect` applies to the
    # projection it receives, so a document this accepts cannot be refused
    # there for its shape.
    if type(projection) is not dict or set(projection) != set(_FIELDS):
        _fail("does not carry exactly the compared fields")
    if not sha(projection["target_revision"]):
        _fail("has no target revision")
    for key in ("product_build", "host_version", "site_id"):
        if type(projection[key]) is not str or not projection[key]:
            _fail(f"has no {key}")
    archive = projection["archive"]
    if type(archive) is not dict or set(archive) != {"filename", "sha256"} \
            or type(archive["filename"]) is not str or not archive["filename"] \
            or not digest(archive["sha256"]):
        _fail("has no staged archive identity")
    files = projection["release_files"]
    if type(files) is not dict or set(files) != {"index_sha256", "manifest_sha256"} \
            or not all(digest(files[key]) for key in files):
        _fail("has no served-file digests")
    if not digest(projection["prior_site_sha256"]):
        _fail("has no prior origin digest")
    prior = projection["prior"]
    if prior is None:
        return projection
    if type(prior) is not dict or set(prior) != {
            "deploy_id", "deploy_url", "product_build", "host_version",
            "index_sha256", "manifest_sha256"} \
            or not all(type(value) is str and value for value in prior.values()) \
            or not digest(prior["index_sha256"]) or not digest(prior["manifest_sha256"]):
        _fail("has an invalid replaced deployment")
    return projection


def read_frozen(root, tag, step):
    """The projection frozen for this tag and step, or None before one exists."""
    path = Path(root) / output_relative(tag, step)
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        _fail("exists but is unreadable")
    try:
        document = json.loads(payload)
    except ValueError:
        _fail("is not a readable document")
    if canonical_json(document) != payload:
        # A rewritten or reformatted freeze is drift, not a projection: the
        # bytes are what every later read of this drive must agree on.
        _fail("does not match the bytes it was frozen as")
    return validate(document)


def freeze(root, tag, step, projection):
    """Write the projection once; a second write must present the same bytes."""
    validate(projection)
    payload = canonical_json(projection)
    path = Path(root) / output_relative(tag, step)
    existing = read_frozen(root, tag, step)
    if existing is not None:
        if canonical_json(existing) != payload:
            _fail("was already frozen with different contents")
        # A copy on both paths: a caller that mutates what it got back must not
        # be able to reach through to anything this module read or wrote.
        return deepcopy(existing)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        _fail("has nowhere to be written")
    # A refusal to overwrite a link someone placed here, not a race guard: the
    # write lands in a sibling temporary file and `os.replace` is `rename(2)`,
    # which replaces a destination symlink itself rather than following it.
    if path.is_symlink() or path.parent.is_symlink():
        _fail("would be written through a link")
    try:
        descriptor, staged = tempfile.mkstemp(prefix="." + path.name + ".",
                                              dir=str(path.parent))
    except OSError:
        _fail("could not be staged beside its output")
    try:
        try:
            stream = os.fdopen(descriptor, "wb")
        except BaseException:
            # mkstemp handed over an open descriptor; if wrapping it fails the
            # descriptor is ours to close and nothing else will.
            os.close(descriptor)
            raise
        with stream as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # `link` rather than `replace`: the existence check above and this
        # write are not one operation, so two drives for the same tag can both
        # see nothing frozen. `link` fails when the name is taken, which makes
        # the second writer lose the race instead of silently replacing bytes
        # the first drive is already bound to.
        os.link(staged, path)
    except FileExistsError:
        frozen = read_frozen(root, tag, step)
        if frozen is None or canonical_json(frozen) != payload:
            _fail("was frozen by another drive with different contents")
        return deepcopy(frozen)
    except OSError:
        _fail("could not be written atomically")
    finally:
        if staged is not None:
            try:
                os.unlink(staged)
            except OSError:
                pass
    # The rename is what publishes the freeze, so persist the directory entry
    # too. Not every platform allows fsync on a directory; failing to harden is
    # not a reason to fail a projection that was written.
    try:
        descriptor = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return deepcopy(projection)
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
    return deepcopy(projection)


def _plan(root, tag):
    """The prepared plan document for this tag, or None before `prepare` ran."""
    from . import prepared_step
    from .carriers import read_prepared_plan

    recorded = read_prepared_plan(root, tag)
    if recorded is None:
        return None
    output = Path(root) / prepared_step.output_relative(tag)
    try:
        payload = (output / prepared_step._PLAN_DOCUMENT).read_bytes()
    except OSError:
        _fail("cannot read the prepared plan document")
    if hashlib.sha256(payload).hexdigest() != recorded:
        _fail("reads a prepared plan that no longer matches its digest")
    try:
        document = json.loads(payload)
    except ValueError:
        _fail("reads an unreadable prepared plan document")
    if type(document) is not dict or document.get("tag") != tag:
        _fail("reads a prepared plan for another tag")
    return document, output


def _asset(document, host, product_build):
    """The one staged archive this Host deploys, named by the release profile."""
    prefix = f"{ARCHIVE_PREFIXES[host]}-"
    suffix = f"-product-{product_build}.zip"
    assets = document.get("assets")
    if type(assets) is not list:
        _fail("reads a prepared plan without its assets")
    matches = [a for a in assets if type(a) is dict
               and type(a.get("name")) is str
               and a["name"].startswith(prefix) and a["name"].endswith(suffix)]
    if len(matches) != 1:
        _fail(f"finds no single staged archive for {host}")
    asset = matches[0]
    if not digest(asset.get("sha256")):
        _fail("reads a staged archive without a digest")
    return asset


def _archive_contents(path, expected_sha256):
    """The Host identity and served digests inside the staged archive."""
    try:
        payload_size = path.stat().st_size
    except OSError:
        _fail("cannot read the staged archive it names")
    if payload_size > LIMIT:
        _fail("reads a staged archive beyond the release bound")
    digests = {}
    bodies = {}
    try:
        # One open for both passes: hashing the file and then reopening it by
        # name would let the digest and the entry bytes describe two different
        # archives. A zip's directory needs random access, so it cannot be
        # parsed in the hashing pass — but it can be parsed from the same
        # descriptor, which is the same inode either way.
        with path.open("rb") as handle:
            read = hashlib.sha256()
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                read.update(block)
            if read.hexdigest() != expected_sha256:
                _fail("reads a staged archive whose bytes differ from the plan")
            handle.seek(0)
            with zipfile.ZipFile(handle) as archive:
                if not {ENTRY, MANIFEST} <= set(archive.namelist()):
                    _fail("reads a staged archive without both entry files")
                for member, key in ((ENTRY, "index_sha256"),
                                    (MANIFEST, "manifest_sha256")):
                    info = archive.getinfo(member)
                    # A directory or link entry under an entry file's name
                    # opens as an empty stream, so it would digest to the empty
                    # string instead of failing. The plan's archive digest
                    # already refuses a tampered archive; this refuses a build
                    # that produced one.
                    if info.is_dir() \
                            or (info.external_attr >> 16) & 0o170000 == 0o120000:
                        _fail("reads an entry file that is not a regular file")
                    if info.file_size > ENTRY_LIMIT:
                        _fail("reads an entry file beyond the entry bound")
                    with archive.open(info) as stream:
                        body = stream.read(ENTRY_LIMIT + 1)
                    if len(body) > ENTRY_LIMIT:
                        _fail("reads an entry file beyond the entry bound")
                    bodies[member] = body
                    digests[key] = hashlib.sha256(body).hexdigest()
    except (OSError, zipfile.BadZipFile):
        _fail("cannot open the staged archive it names")
    manifest = bodies[MANIFEST]
    try:
        document = json.loads(manifest)
    except ValueError:
        _fail("reads a staged archive with an unreadable manifest")
    if type(document) is not dict:
        _fail("reads a staged archive with an unreadable manifest")
    for field in ("product_build", "host_version"):
        if type(document.get(field)) is not str or not document[field]:
            _fail(f"reads a staged archive with no {field}")
    return document["product_build"], document["host_version"], digests


class NoDeployment:
    """The Worker exists but holds no deployment: a first deployment, not a gap.

    Compared by type, never by identity with the singleton below. A reader
    assembled from a second import of this module — the candidate-worktree copy
    the surrounding code guards against — would hand back a different object,
    and identity would send a first deployment down the "invalid version"
    branch instead.
    """

    def __repr__(self):
        return "NO_DEPLOYMENT"


NO_DEPLOYMENT = NoDeployment()


def assemble(root, tag, step, *, reader):
    """Derive the projection from this release's inputs, or None while it cannot.

    `reader` supplies the four live facts this cannot derive from the release
    itself, each already bounded and validated by its own module:

    - `reader.worker(host)` — the Worker name, the Site identity under Cloudflare;
    - `reader.version_url(host, version)` — the immutable per-version origin;
    - `reader.replaced_version(host)` — the deployment this run replaces, as a
      version identity, `NO_DEPLOYMENT` when the Worker holds none, or `None`
      when it cannot be read (no token, no answer): the caller's credentials
      are not this module's business, and an unread Worker stays `pending`;
    - `reader.observe(host)` — what the public origin serves right now, or
      `None`. That `None` does not separate "serves nothing" from "could not be
      read": both mean this drive does not know what production serves, and both
      have the same remedy — read the origin and the Worker directly. The step
      waits either way rather than freezing a prior nobody observed.

    Injecting them keeps this a pure derivation over evidence the caller
    obtained, which is also what lets the tests pin each branch.
    """
    if step not in HOSTS:
        _fail(f"names an unknown deployment step {step!r}")
    host = HOSTS[step]
    prepared = _plan(root, tag)
    if prepared is None:
        # `prepare` has not run for this tag: there is nothing to project from.
        return None
    document, output = prepared
    product_build = document.get("identity")
    target_revision = document.get("target_revision")
    if type(product_build) is not str or not product_build \
            or type(target_revision) is not str or not target_revision:
        _fail("reads a prepared plan without its release identity")
    asset = _asset(document, host, product_build)
    archived_build, host_version, release_files = _archive_contents(
        output / "assets" / asset["name"], asset["sha256"])
    if archived_build != product_build:
        _fail("reads a staged archive built for another Product Build")
    site_id = reader.worker(host)
    if type(site_id) is not str or not site_id:
        _fail("reads no Worker identity for this Host")

    version = reader.replaced_version(host)
    if version is None:
        # The Worker could not be read at all. Waiting is the only honest
        # answer: a projection that guessed the prior would authorize a
        # deployment against a state nobody observed.
        return None
    if type(version) is NoDeployment:
        prior = None
        # Nothing was served, so there is no observation to digest. The
        # deployment effect compares this digest only against a recorded
        # `prior_good`, which is absent for a first deployment; it still has to
        # be a well-formed digest, and this one says exactly what was seen.
        prior_site_sha256 = canonical_sha256(
            {"worker": site_id, "served": False})
    else:
        if type(version) is not str or not version:
            _fail("reads an invalid replaced deployment identity")
        observation = reader.observe(host)
        if observation is None:
            # A deployed Worker whose origin cannot be read is a gap, not a
            # first deployment; the prior it would replace is unknown.
            return None
        deploy_url = reader.version_url(host, version)
        # The immutable per-version origin, not the production one: a
        # well-formed but wrong URL would freeze and only be caught by the
        # effect's field comparison, long after the dispatch. Checked as a
        # relationship rather than a template, so the URL shape stays the
        # evidence module's to state.
        if type(deploy_url) is not str or version[:8] not in deploy_url \
                or site_id not in deploy_url:
            _fail("reads an immutable origin that names another version or Worker")
        prior = _replaced(observation, version, deploy_url)
        prior_site_sha256 = canonical_sha256(observation["response"])

    return validate({
        "target_revision": target_revision,
        "product_build": product_build,
        "host_version": host_version,
        "site_id": site_id,
        "archive": {"filename": asset["name"], "sha256": asset["sha256"]},
        "release_files": release_files,
        "prior": prior,
        "prior_site_sha256": prior_site_sha256,
    })


def _replaced(observation, version, version_url):
    """The replaced deployment, in the one shape the comparison uses."""
    if type(observation) is not dict:
        _fail("reads an unusable origin observation")
    files = observation.get("release_files")
    if type(files) is not dict or set(files) != {"index_sha256", "manifest_sha256"}:
        _fail("reads an origin observation without its served digests")
    for field in ("product_build", "host_version"):
        if type(observation.get(field)) is not str or not observation[field]:
            _fail(f"reads an origin observation without {field}")
    if type(observation.get("response")) is not dict or not observation["response"]:
        _fail("reads an origin observation without its response")
    if type(version_url) is not str or not version_url:
        _fail("reads no immutable origin for the replaced deployment")
    return {"deploy_id": version, "deploy_url": version_url,
            "product_build": observation["product_build"],
            "host_version": observation["host_version"],
            "index_sha256": files["index_sha256"],
            "manifest_sha256": files["manifest_sha256"]}


def projection(root, tag, step, *, reader):
    """The frozen projection for this drive: the first assembly wins.

    Later calls in the same drive — including a resume after the dispatch, when
    the origin already serves this release — read the frozen bytes back instead
    of observing production again.
    """
    frozen = read_frozen(root, tag, step)
    if frozen is not None:
        return frozen
    assembled = assemble(root, tag, step, reader=reader)
    if assembled is None:
        return None
    return freeze(root, tag, step, assembled)
