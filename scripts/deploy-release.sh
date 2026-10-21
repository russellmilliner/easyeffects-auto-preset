#!/usr/bin/env bash
# Interactive End-to-End Release Builder & GitHub Releases Publisher
# for EasyEffects Auto Preset.
#
# Workflow:
#   1. Optionally increment version (via scripts/bump-version.sh)
#   2. Run unit tests & syntax checks
#   3. Build Rust release binary, Linux .tar.gz archive, and Flatpak bundle + SHA-256 checksums
#   4. Optionally update local ~/.local/bin/easyeffects-auto-preset and restart user service
#   5. Commit, tag vX.Y.Z, and push to GitHub (via scripts/sync-github.sh)
#   6. Create or update the GitHub Release with all 6 release artifacts

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BOLD="\033[1m"
CYAN="\033[1;36m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
RESET="\033[0m"

BUMP_FLAG=""
TARGET_VERSION=""
NOTES_FILE=""
AUTO_YES=false
INSTALL_LOCAL=""

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Interactive end-to-end release builder and GitHub Releases publisher.

Options:
  --patch                 Increment patch version before releasing
  --minor                 Increment minor version before releasing
  --major                 Increment major version before releasing
  --version <X.Y.Z>       Set explicit version before releasing
  --no-bump               Release the current version in Cargo.toml without bumping
  --notes-file <path>     Path to custom markdown release notes file
  --install-local         Update ~/.local/bin/easyeffects-auto-preset and restart systemd service
  --no-install-local      Skip updating local installation
  -y, --yes               Non-interactive mode (accept defaults)
  -h, --help              Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --patch) BUMP_FLAG="--patch"; shift ;;
    --minor) BUMP_FLAG="--minor"; shift ;;
    --major) BUMP_FLAG="--major"; shift ;;
    --version) BUMP_FLAG="--version"; TARGET_VERSION="${2:-}"; shift 2 ;;
    --no-bump) BUMP_FLAG="none"; shift ;;
    --notes-file) NOTES_FILE="${2:-}"; shift 2 ;;
    --install-local) INSTALL_LOCAL="yes"; shift ;;
    --no-install-local) INSTALL_LOCAL="no"; shift ;;
    -y|--yes) AUTO_YES=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo -e "${RED}Unknown argument: $1${RESET}" >&2; usage; exit 1 ;;
  esac
done

CURRENT_VERSION="$(grep -E '^version\s*=' "$REPO_ROOT/Cargo.toml" | head -n 1 | sed -E 's/.*"([^"]+)".*/\1/')"

echo -e "${CYAN}============================================================${RESET}"
echo -e "${BOLD}  EasyEffects Auto Preset — Interactive Release Deployer${RESET}"
echo -e "${CYAN}============================================================${RESET}"
echo -e "Current version in Cargo.toml: ${YELLOW}v${CURRENT_VERSION}${RESET}"
echo ""

# Step 1: Optional Version Bump
if [[ -z "$BUMP_FLAG" ]]; then
  if $AUTO_YES; then
    BUMP_FLAG="none"
  else
    read -r -p "Would you like to increment the version before building? [y/N]: " bump_ans
    bump_ans="${bump_ans:-N}"
    if [[ "$bump_ans" =~ ^[Yy] ]]; then
      "$REPO_ROOT/scripts/bump-version.sh"
    fi
  fi
elif [[ "$BUMP_FLAG" != "none" ]]; then
  BUMP_ARGS=("$BUMP_FLAG")
  if [[ -n "$TARGET_VERSION" ]]; then
    BUMP_ARGS+=("$TARGET_VERSION")
  fi
  if $AUTO_YES; then
    BUMP_ARGS+=("--yes")
  fi
  "$REPO_ROOT/scripts/bump-version.sh" "${BUMP_ARGS[@]}"
fi

VERSION="$(grep -E '^version\s*=' "$REPO_ROOT/Cargo.toml" | head -n 1 | sed -E 's/.*"([^"]+)".*/\1/')"
TAG="v${VERSION}"
ARCH="$(uname -m)"

echo ""
echo -e "${BOLD}==> Step 1/5: Running tests and syntax verification for ${GREEN}${TAG}${RESET}..."
cargo test
python3 -m py_compile python/easyeffects_auto_preset.py
echo -e "${GREEN}  [OK] All tests and syntax checks passed.${RESET}"

echo ""
echo -e "${BOLD}==> Step 2/5: Building release binary, Flatpak bundle, and Linux archive...${RESET}"
cargo build --release
"$REPO_ROOT/scripts/build-flatpak.sh"

DIST_DIR="$REPO_ROOT/dist"
STAGE_NAME="easyeffects-auto-preset-${TAG}-linux-${ARCH}"
FLATPAK_NAME="easyeffects-auto-preset-${TAG}-${ARCH}.flatpak"
TAR_NAME="${STAGE_NAME}.tar.gz"
BIN_NAME="easyeffects-auto-preset-${TAG}-${ARCH}"

rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR/$STAGE_NAME"

cp "$REPO_ROOT/target/release/easyeffects-auto-preset" "$DIST_DIR/$BIN_NAME"
cp "$REPO_ROOT/target/release/easyeffects-auto-preset" "$DIST_DIR/$STAGE_NAME/"
cp -r "$REPO_ROOT/python" "$REPO_ROOT/presets" "$REPO_ROOT/systemd" "$REPO_ROOT/data" \
      "$REPO_ROOT/README.md" "$REPO_ROOT/LICENSE" "$REPO_ROOT/NOTICE" \
      "$DIST_DIR/$STAGE_NAME/"

(
  cd "$DIST_DIR"
  tar -czf "$TAR_NAME" "$STAGE_NAME"
  rm -rf "$STAGE_NAME"
  cp "$REPO_ROOT/target/release/$FLATPAK_NAME" .
  sha256sum "$BIN_NAME" > "${BIN_NAME}.sha256"
  sha256sum "$TAR_NAME" > "${TAR_NAME}.sha256"
  sha256sum "$FLATPAK_NAME" > "${FLATPAK_NAME}.sha256"
)

echo -e "${GREEN}  [OK] Built release artifacts in dist/:${RESET}"
ls -lh "$DIST_DIR"

# Step 3: Optional Local Installation
if [[ -z "$INSTALL_LOCAL" ]]; then
  if $AUTO_YES; then
    INSTALL_LOCAL="yes"
  else
    echo ""
    read -r -p "Update local ~/.local/bin/easyeffects-auto-preset and restart systemd service? [Y/n]: " inst_ans
    inst_ans="${inst_ans:-Y}"
    if [[ "$inst_ans" =~ ^[Yy] ]]; then
      INSTALL_LOCAL="yes"
    else
      INSTALL_LOCAL="no"
    fi
  fi
fi

if [[ "$INSTALL_LOCAL" == "yes" ]]; then
  echo -e "${BOLD}==> Step 3/5: Updating local installation & systemd service...${RESET}"
  mkdir -p "$HOME/.local/bin"
  install -m 755 "$REPO_ROOT/python/easyeffects_auto_preset.py" "$HOME/.local/bin/easyeffects-auto-preset"
  systemctl --user restart easyeffects-auto-preset.service 2>/dev/null || true
  echo -e "${GREEN}  [OK] Updated ~/.local/bin/easyeffects-auto-preset and restarted service.${RESET}"
else
  echo -e "${YELLOW}==> Step 3/5: Skipped local installation.${RESET}"
fi

# Step 4: Sync & Tag on GitHub
echo ""
echo -e "${BOLD}==> Step 4/5: Committing, tagging ${TAG}, and pushing to GitHub...${RESET}"
rm -rf "$DIST_DIR"
git add Cargo.toml Cargo.lock src/main.rs python/easyeffects_auto_preset.py README.md \
        data/io.github.russellmilliner.easyeffects_auto_preset.metainfo.xml docs/screenshots/*.png 2>/dev/null || true

if ! git diff --cached --quiet; then
  git commit -m "release: EasyEffects Auto Preset ${TAG}"
fi

if ! git rev-parse "$TAG" >/dev/null 2>&1; then
  git tag -a "$TAG" -m "EasyEffects Auto Preset ${TAG}"
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git push origin "$BRANCH"
git push origin "$TAG"
echo -e "${GREEN}  [OK] Pushed ${BRANCH} and ${TAG} to GitHub.${RESET}"

# Recreate dist/ after git operations so working tree stays clean
mkdir -p "$DIST_DIR/$STAGE_NAME"
cp "$REPO_ROOT/target/release/easyeffects-auto-preset" "$DIST_DIR/$BIN_NAME"
cp "$REPO_ROOT/target/release/easyeffects-auto-preset" "$DIST_DIR/$STAGE_NAME/"
cp -r "$REPO_ROOT/python" "$REPO_ROOT/presets" "$REPO_ROOT/systemd" "$REPO_ROOT/data" \
      "$REPO_ROOT/README.md" "$REPO_ROOT/LICENSE" "$REPO_ROOT/NOTICE" \
      "$DIST_DIR/$STAGE_NAME/"
(
  cd "$DIST_DIR"
  tar -czf "$TAR_NAME" "$STAGE_NAME"
  rm -rf "$STAGE_NAME"
  cp "$REPO_ROOT/target/release/$FLATPAK_NAME" .
  sha256sum "$BIN_NAME" > "${BIN_NAME}.sha256"
  sha256sum "$TAR_NAME" > "${TAR_NAME}.sha256"
  sha256sum "$FLATPAK_NAME" > "${FLATPAK_NAME}.sha256"
)

# Step 5: Publish GitHub Release
echo ""
echo -e "${BOLD}==> Step 5/5: Publishing GitHub Release ${TAG}...${RESET}"
if ! $AUTO_YES; then
  read -r -p "Publish/update GitHub Release ${TAG} with all 6 artifacts now? [Y/n]: " rel_ans
  rel_ans="${rel_ans:-Y}"
  if [[ ! "$rel_ans" =~ ^[Yy] ]]; then
    echo "Artifacts remain in $DIST_DIR. Exiting without publishing GitHub release."
    exit 0
  fi
fi

NOTES_TMP="$(mktemp)"
trap 'rm -f "$NOTES_TMP"; rm -rf "$DIST_DIR"' EXIT

if [[ -n "$NOTES_FILE" && -f "$NOTES_FILE" ]]; then
  cp "$NOTES_FILE" "$NOTES_TMP"
else
  prev_tag="$(git describe --tags --abbrev=0 "${TAG}^" 2>/dev/null || echo "")"
  changelog=""
  if [[ -n "$prev_tag" ]]; then
    changelog="$(git log --pretty=format:"- %s (%h)" "${prev_tag}..${TAG}" || true)"
  else
    changelog="$(git log -n 10 --pretty=format:"- %s (%h)" || true)"
  fi

  cat > "$NOTES_TMP" <<EOF
## EasyEffects Auto Preset ${TAG}

### Changes
${changelog}

### Downloads
| Package | File | Description |
| :--- | :--- | :--- |
| **Flatpak Bundle (\`${ARCH}\`)** | \`${FLATPAK_NAME}\` | Self-contained Flatpak bundle (\`org.kde.Platform//6.11\`) |
| **Linux Release Archive (\`${ARCH}\`)** | \`${TAR_NAME}\` | Native Rust daemon, PyQt6 GUI & tray app, bundled EasyEffects presets, systemd service |
| **Standalone Rust Daemon (\`${ARCH}\`)** | \`${BIN_NAME}\` | Compiled standalone Rust CLI & daemon binary |
EOF
fi

ASSETS=(
  "$DIST_DIR/$FLATPAK_NAME"
  "$DIST_DIR/${FLATPAK_NAME}.sha256"
  "$DIST_DIR/$TAR_NAME"
  "$DIST_DIR/${TAR_NAME}.sha256"
  "$DIST_DIR/$BIN_NAME"
  "$DIST_DIR/${BIN_NAME}.sha256"
)

if gh release view "$TAG" >/dev/null 2>&1; then
  echo -e "Release ${YELLOW}${TAG}${RESET} already exists — uploading clobbered assets and updating notes..."
  gh release upload "$TAG" "${ASSETS[@]}" --clobber
  gh release edit "$TAG" --title "EasyEffects Auto Preset ${TAG}" --notes-file "$NOTES_TMP"
else
  gh release create "$TAG" "${ASSETS[@]}" \
    --title "EasyEffects Auto Preset ${TAG}" \
    --notes-file "$NOTES_TMP"
fi

echo ""
echo -e "${GREEN}============================================================${RESET}"
echo -e "${GREEN}  Release ${TAG} deployed successfully!${RESET}"
echo -e "  URL: https://github.com/russellmilliner/easyeffects-auto-preset/releases/tag/${TAG}"
echo -e "${GREEN}============================================================${RESET}"
