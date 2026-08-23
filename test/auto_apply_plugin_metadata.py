import sys
import json
import ast
import os
import hashlib
import subprocess
import get_latest
from auto_apply_version_metadata import get_comparable_version_tuple_from_string

DEBUG = True

MANIFEST_PATHS = {
    "minigames": "plugins/minigames.json",
    "utilities": "plugins/utilities.json",
    "maps": "plugins/maps.json",
    "plugman": "index.json",
}

print("DOES THIS RUN AUTO APPLY PLUGIN METADATA?")


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


def get_latest_version(plugin_name, category) -> str:
    try:
        if category != "plugman":
            return get_latest.get_latest_plugin_version(plugin_name, MANIFEST_PATHS[category])
        return get_latest.get_latest_plugman_version()

    except Exception as e:
        raise e


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


def update_plugman_json(version):
    with open("index.json", "r+") as file:
        data = json.load(file)
        plugman_version = int(get_latest_version("plugin_manager", "plugman").replace(".", ""))
        current_version = int(version["version"].replace(".", ""))

        if current_version > plugman_version:
            with open("index.json", "r+") as file:
                data = json.load(file)
                data[current_version] = None
                data["versions"] = dict(sorted(data["versions"].items(), reverse=True))


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

            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target = node.targets[0]
                    if isinstance(target, ast.Name) and target.id == "plugman":
                        if isinstance(node.value, ast.Dict):
                            # i dont want to support multiple formats for now
                            # because its harder to parse and maintain
                            # ill leave this here for now, though not supported
                            # Standard dictionary format {key: value}
                            return ast.literal_eval(node.value)
                        elif (
                            isinstance(node.value, ast.Call)
                            and isinstance(node.value.func, ast.Name)
                            and node.value.func.id == "dict"
                        ):
                            # dict() constructor format
                            result = {}
                            for kw in node.value.keywords:
                                if kw.arg == "plugin_name":
                                    plugin_name = ast.literal_eval(kw.value)
                                    # some basic validation specific to plugin manager
                                    if plugin_name != plugin_name.lower():
                                        raise ValueError(
                                            "Plugin name in plugman must be in snakecase."
                                        )
                                    if plugin_name != file_name_no_extension:
                                        raise ValueError(
                                            "Plugin name in plugman does not match the file name."
                                        )
                                result[kw.arg] = ast.literal_eval(kw.value)
                            if category:
                                update_plugin_json(result, category=category, plugin_path=plugin)
                            else:
                                update_plugman_json(result)
            # raise ValueError("Variable plugman not found in the file or has unsupported format.")


if __name__ == "__main__":
    plugins = sys.argv[1].split('\n')
    debug_print(plugins)
    extract_plugman(plugins)
