#!/usr/bin/env bash
# git release-app [X.Y.Z]: tag the tip of main and wait for the GitHub Release it builds.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

BRANCH="main"
if [ "$(git rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]; then
    echo "❌ Releases ship from '${BRANCH}'. Switch to it first."
    exit 1
fi

VERSION="${1:-$(sed -n 's/^version *= *"\(.*\)"/\1/p' blender_manifest.toml)}"
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "❌ '${VERSION}' is not an X.Y.Z version."
    exit 1
fi
MANIFEST_VERSION="$(sed -n 's/^version *= *"\(.*\)"/\1/p' blender_manifest.toml)"
if [ "$VERSION" != "$MANIFEST_VERSION" ]; then
    echo "❌ Tag ${VERSION} does not match blender_manifest.toml version ${MANIFEST_VERSION}. Bump the manifest first."
    exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
    echo "📝 Uncommitted changes found -- committing automatically:"
    git status --short
    git add -A
    git commit --quiet -m "Release ${VERSION}"
fi

git fetch origin "$BRANCH" --quiet
LOCAL="$(git rev-parse "$BRANCH")"
REMOTE="$(git rev-parse "origin/${BRANCH}")"
BASE="$(git merge-base "$BRANCH" "origin/${BRANCH}")"
if [ "$LOCAL" = "$REMOTE" ]; then
    :
elif [ "$REMOTE" = "$BASE" ]; then
    echo "⬆️  Pushing ${BRANCH}..."
    git push origin "$BRANCH"
elif [ "$LOCAL" = "$BASE" ]; then
    echo "⬇️  Fast-forwarding ${BRANCH} to origin..."
    git merge --ff-only "origin/${BRANCH}"
else
    echo "❌ '${BRANCH}' and 'origin/${BRANCH}' have diverged: git pull --rebase origin ${BRANCH}"
    exit 1
fi

HEAD_SHA="$(git rev-parse HEAD)"
echo "🏷️  Tagging ${VERSION} at ${HEAD_SHA:0:7}..."
git tag -f "$VERSION" HEAD >/dev/null
START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
# Deleting the remote tag first makes the push a new tag event, so the workflow always runs.
git push origin ":refs/tags/${VERSION}" 2>/dev/null || true
git push origin "refs/tags/${VERSION}"

echo "⏳ Waiting for the release run..."
RUN_ID=""
for _ in $(seq 1 60); do
    RUN_ID="$(gh run list --workflow=release.yml --limit 10 --json databaseId,createdAt,headSha \
        --jq ".[] | select(.createdAt >= \"${START}\" and .headSha == \"${HEAD_SHA}\") | .databaseId" | head -n1)"
    [ -n "$RUN_ID" ] && break
    sleep 5
done
if [ -z "$RUN_ID" ]; then
    echo "❌ No release.yml run showed up within 5 minutes. Check the Actions tab."
    exit 1
fi

if ! gh run watch "$RUN_ID" --exit-status --interval 10; then
    echo "❌ Release failed. See: gh run view ${RUN_ID} --log-failed"
    exit 1
fi
echo "✅ ${VERSION} is released: $(gh release view "$VERSION" --json url --jq .url)"
