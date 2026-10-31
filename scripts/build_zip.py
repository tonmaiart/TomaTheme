# SPDX-License-Identifier: GPL-3.0-or-later
"""Build dist/<id>-<version>.zip, an extension zip that installs by dragging it into Blender."""

import argparse
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUDE_DIRS = {".git", ".github", "scripts", "dist", "__pycache__", ".claude"}
EXCLUDE_FILES = {".gitignore"}


def manifest_value(key):
    with open(os.path.join(ROOT, "blender_manifest.toml"), encoding="utf-8") as f:
        match = re.search(r'^%s\s*=\s*"([^"]+)"' % key, f.read(), re.MULTILINE)
    if not match:
        sys.exit("blender_manifest.toml has no %s" % key)
    return match.group(1)


def shipped_files():
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for name in sorted(files):
            if name not in EXCLUDE_FILES and not name.endswith(".pyc"):
                path = os.path.join(folder, name)
                yield path, os.path.relpath(path, ROOT).replace(os.sep, "/")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-version", help="fail unless the manifest version equals this")
    args = parser.parse_args()

    ext_id, version = manifest_value("id"), manifest_value("version")
    if args.expect_version and args.expect_version != version:
        sys.exit("Tag %s does not match blender_manifest.toml version %s" % (args.expect_version, version))

    out = os.path.join(ROOT, "dist", "%s-%s.zip" % (ext_id, version))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    # The manifest sits at the zip root, which is what Blender's drag-and-drop install expects.
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, arcname in shipped_files():
            zf.write(path, arcname)
            print("  +", arcname)
    print(out)


if __name__ == "__main__":
    main()
