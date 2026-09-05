import sys
import json
import ast
import copy
import os
import hashlib
import subprocess
from auto_apply_version_metadata import get_comparable_version_tuple_from_string

DEBUG = True

# index.json is deliberately absent: plugin manager releases add their own
# "x.y.z": null entry by hand (see CLAUDE.md), this script only ever touches the
# category manifests.
MANIFEST_PATHS = {
    "minigames": "plugins/minigames.json",
    "utilities": "plugins/utilities.json",
    "maps": "plugins/maps.json",
}


def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)


def version_key(version):
    """Comparison/sort key for a version string, so 1.0.10 sorts above 1.0.9."""
    try:
        return get_comparable_version_tuple_from_string(version)
    except ValueError:
        raise ValueError(f"Version {version!r} is not in x.y.z form.")


def md5sum_of(path):
    with open(path, "rb") as fin:
        return hashlib.md5(fin.read()).hexdigest()


def read_manifest_at(path, ref):
    """Load a manifest as it exists at `ref`, or None if it can't be read there."""
    try:
        blob = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            capture_output=True,
            check=True,
        ).stdout
        return json.loads(blob)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return None


def get_published_versions(plugin_name, category):
    """Versions of `plugin_name` that are already published on the PR's base branch.

    The working tree cannot answer this. Once ci-apply.yml has pushed its
    "[ci] apply-plugin-metadata-and-formatting" commit back to the PR branch,
    the PR's own copy of the manifest already lists the version being added -
    so comparing against the working tree rejects every re-run of PR Check,
    including the one ci-apply.yml's own push triggers, and every re-run caused
    by a contributor pushing a follow-up commit.

    PLUGMAN_BASE_REF is set by ci-check.yml to the PR's base sha. Local runs
    fall back to origin/main, then to the working tree when there is no history
    to consult at all.
    """
    path = MANIFEST_PATHS[category]
    manifest = None
    for ref in (os.environ.get("PLUGMAN_BASE_REF"), "origin/main", "main"):
        if ref:
            manifest = read_manifest_at(path, ref)
            if manifest is not None:
                break
    if manifest is None:
        with open(path, "r") as file:
            manifest = json.load(file)
    return manifest["plugins"].get(plugin_name, {}).get("versions", {})


def update_plugin_json(plugin_info, category, plugin_path):
    name = plugin_info["plugin_name"]
    version = plugin_info["version"]

    # Ensure the version is always greater than the already PUBLISHED version -
    # what is on the base branch, not what this PR's own tree happens to say.
    published = get_published_versions(name, category)
    if published:
        latest_published = max(published, key=version_key)
        if version_key(version) <= version_key(latest_published):
            raise Exception(
                "Version cant be lower or equal than the previous version. "
                f"{name} {latest_published} is already published; bump the version "
                f"in its plugman dict (currently {version})."
            )

    with open(f"plugins/{category}.json", "r+") as file:
        data = json.load(file)
        plugin = data["plugins"].get(name)
        if plugin is None:
            # New plugin. Key order here is the shape every other entry has.
            plugin = data["plugins"][name] = {
                "description": plugin_info["description"],
                "external_url": plugin_info["external_url"],
                "authors": plugin_info["authors"],
                "versions": {},
            }

        versions = plugin["versions"]
        stamped = versions.get(version)
        # A null placeholder is only (re)written when there is something for
        # auto_apply_version_metadata.py to stamp, which keeps re-runs over an
        # already-processed tree a no-op - otherwise ci-apply.yml's push would
        # trigger a PR Check that undoes the stamp, forever.
        #
        # A stamped entry whose md5sum no longer matches the file means the
        # contributor pushed further edits under the same UNPUBLISHED version
        # (the published case raised above). Reset it so the stamp is
        # recomputed, rather than demanding a bump for every review iteration.
        if version not in versions or (
            isinstance(stamped, dict) and stamped.get("md5sum") != md5sum_of(plugin_path)
        ):
            versions[version] = None

        # Ensure latest version appears first
        plugin["versions"] = dict(
            sorted(versions.items(), key=lambda item: version_key(item[0]), reverse=True)
        )
        plugin["description"] = plugin_info["description"]
        plugin["external_url"] = plugin_info["external_url"]
        plugin["authors"] = plugin_info["authors"]

        file.seek(0)
        json.dump(data, file, indent=2, ensure_ascii=False)
        # Ensure old content is removed
        file.truncate()


def resolve_literal(node, constants, where):
    """ast.literal_eval, widened to module-level constants and indexing into them.

    Plugins commonly keep a `__version__` / `__author__` dunder next to the code
    that uses them and want the plugman dict to reference those rather than
    repeat the values. Nothing here imports or executes the plugin, so only
    names this module already resolved to a literal are available, and only
    indexing (not attribute access or calls) is applied to them.
    """
    if isinstance(node, ast.Name):
        if node.id not in constants:
            raise ValueError(
                f"{where}: {node.id} is not a module-level constant defined above "
                "plugman. Only names assigned a literal earlier in the file can be "
                "referenced, because the plugin is parsed, never imported."
            )
        # Copied so an entry like authors=__author__ cannot be mutated later
        # through the constants table.
        return copy.deepcopy(constants[node.id])

    if isinstance(node, ast.Subscript):
        container = resolve_literal(node.value, constants, where)
        index = resolve_literal(node.slice, constants, where)
        try:
            return container[index]
        except (TypeError, KeyError, IndexError) as err:
            raise ValueError(
                f"{where}: cannot index {container!r} with {index!r}: {err}"
            ) from None

    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        items = [resolve_literal(item, constants, where) for item in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(items)
        if isinstance(node, ast.Set):
            return set(items)
        return items

    if isinstance(node, ast.Dict):
        if any(key is None for key in node.keys):
            raise ValueError(f"{where}: ** unpacking inside plugman is not supported.")
        return {
            resolve_literal(key, constants, where): resolve_literal(value, constants, where)
            for key, value in zip(node.keys, node.values)
        }

    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        raise ValueError(
            f"{where}: unsupported expression `{ast.unparse(node)}`. plugman values must "
            "be literals, or module-level constants (optionally indexed, e.g. "
            "__author__[0]). Method calls such as __file__.split('/') are not evaluated."
        ) from None


def collect_module_constants(tree, stop_at):
    """Module-level names bound to a literal, in the statements before `stop_at`.

    Order matters: a name assigned *after* plugman would raise NameError when the
    game imports the plugin, so it must not resolve here either.
    """
    constants = {}
    for node in tree.body:
        if node is stop_at:
            break
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        else:
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                constants[target.id] = value
    return constants


def build_plugman_info(node, tree, plugin, file_name_no_extension):
    """Turn a `plugman = dict(...)` call node into the dict the manifest needs."""
    where = f"{plugin}: plugman"
    constants = collect_module_constants(tree, stop_at=node)

    result = {}
    for keyword in node.value.keywords:
        if keyword.arg is None:
            raise ValueError(f"{where}: ** unpacking inside plugman is not supported.")
        result[keyword.arg] = resolve_literal(keyword.value, constants, where)

    # plugin_name is optional: the only value the check below would ever accept
    # is the file's own stem, so a plugin that omits it simply gets that.
    if "plugin_name" in result:
        plugin_name = result["plugin_name"]
        # some basic validation specific to plugin manager
        if not isinstance(plugin_name, str):
            raise ValueError(f"{where}: plugin_name must be a string.")
        if plugin_name != plugin_name.lower():
            raise ValueError("Plugin name in plugman must be in snakecase.")
        if plugin_name != file_name_no_extension:
            raise ValueError("Plugin name in plugman does not match the file name.")
    else:
        result["plugin_name"] = file_name_no_extension

    missing = [key for key in ("description", "external_url", "authors", "version")
               if key not in result]
    if missing:
        raise ValueError(f"{where}: missing required key(s) {', '.join(missing)}.")
    if not isinstance(result["version"], str):
        raise ValueError(
            f"{where}: version must be a string in x.y.z form, got "
            f"{result['version']!r}. Quote it (version=\"1.0.0\")."
        )
    return result


def extract_plugman(plugins):
    for plugin in plugins:
        if "plugins" + os.sep in plugin and plugin.endswith(".py"):

            print(f"Processing plugin file: {plugin}")
            try:
                # Split the path and get the part after 'plugins/'
                parts = plugin.split("plugins" + os.sep)[1].split(os.sep)
                file_name_no_extension = plugin.split(os.sep)[-1].replace(".py", "")
                category = parts[0]  # First part after plugins/
                debug_print(f"Determined category: {category}")
            except ValueError:
                if "plugin_manager" in plugin:
                    continue
            with open(plugin, "r") as f:
                tree = ast.parse(f.read())

            # A changed file that reaches the end of this loop without stamping
            # the manifest ships against the PREVIOUS version's md5sum. That
            # used to pass here silently and only surface much later as an
            # opaque "checksum changed" failure in test_latest_version, so
            # every path below either updates a manifest or raises.
            handled = False

            # Module level statements in source order, so collect_module_constants()
            # can tell what is defined ABOVE plugman. Every plugin in the catalog
            # assigns plugman at column 0; one hidden inside a function or an if
            # was never picked up meaningfully anyway and now raises below.
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target = node.targets[0]
                    if isinstance(target, ast.Name) and target.id == "plugman":
                        if (
                            isinstance(node.value, ast.Call)
                            and isinstance(node.value.func, ast.Name)
                            and node.value.func.id == "dict"
                        ):
                            # dict() constructor format
                            result = build_plugman_info(
                                node, tree, plugin, file_name_no_extension
                            )
                            update_plugin_json(result, category=category, plugin_path=plugin)
                            handled = True
                        else:
                            # Only the dict() constructor form is parsed. A literal
                            # {key: value} was previously returned from here, which
                            # silently abandoned every remaining changed file too.
                            raise ValueError(
                                f"{plugin}: plugman must be assigned with the dict() "
                                "constructor, e.g. plugman = dict(plugin_name=..., "
                                "version=...). A literal { } dict is not supported."
                            )

            if not handled:
                raise ValueError(
                    f"{plugin}: no plugman dict found. Every plugin under plugins/ "
                    "needs one so its catalog entry and version can be generated, see\n"
                    "https://github.com/bombsquad-community/plugin-manager#submitting-a-plugin\n"
                    f'plugin_name defaults to "{file_name_no_extension}" (the file stem). '
                    "Bump version on every edit; the manifest entry is derived from it."
                )


if __name__ == "__main__":
    plugins = sys.argv[1].split('\n')
    debug_print(plugins)
    extract_plugman(plugins)
