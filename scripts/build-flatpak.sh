#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ID="io.github.russellmilliner.easyeffects_auto_preset"
VERSION="$(grep -E '^version\s*=' "$REPO_ROOT/Cargo.toml" | head -n 1 | sed -E 's/.*"([^"]+)".*/\1/')"
ARCH="$(uname -m)"
WORK_DIR="${FLATPAK_WORK_DIR:-$REPO_ROOT/target/flatpak-work}"
OUT_DIR="${FLATPAK_OUT_DIR:-$REPO_ROOT/target/release}"
BUNDLE_NAME="easyeffects-auto-preset-v${VERSION}-${ARCH}.flatpak"

echo "==> Building EasyEffects Auto Preset v${VERSION} Flatpak (${ARCH})..."
rm -rf "$WORK_DIR/build-dir" "$WORK_DIR/repo"
mkdir -p "$WORK_DIR" "$OUT_DIR"

if command -v flatpak-builder >/dev/null 2>&1; then
  echo "==> Building with flatpak-builder..."
  flatpak-builder --force-clean --user --install-deps-from=flathub "$WORK_DIR/build-dir" "$REPO_ROOT/${APP_ID}.yml"
  flatpak build-export "$WORK_DIR/repo" "$WORK_DIR/build-dir"
  flatpak build-bundle "$WORK_DIR/repo" "$OUT_DIR/$BUNDLE_NAME" "$APP_ID" --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo
else
  echo "==> Building with standard flatpak build tools..."
  flatpak build-init \
    --sdk-extension=org.freedesktop.Sdk.Extension.rust-stable \
    "$WORK_DIR/build-dir" \
    "$APP_ID" \
    org.kde.Sdk \
    org.kde.Platform \
    6.11

  CARGO_HOME_DIR="${CARGO_HOME:-$HOME/.cargo}"

  flatpak build \
    --share=network \
    --filesystem="$REPO_ROOT":ro \
    --filesystem="$CARGO_HOME_DIR":ro \
    --filesystem="$WORK_DIR":rw \
    --env=PATH=/usr/lib/sdk/rust-stable/bin:/usr/bin:/bin \
    --env=CARGO_HOME="$CARGO_HOME_DIR" \
    --env=CARGO_TARGET_DIR="$WORK_DIR/target" \
    "$WORK_DIR/build-dir" \
    sh -c "
      set -euo pipefail
      cargo build --release --manifest-path '$REPO_ROOT/Cargo.toml'
      install -Dm755 \"\$CARGO_TARGET_DIR/release/easyeffects-auto-preset\" -t /app/bin/
      install -Dm755 '$REPO_ROOT/python/easyeffects_auto_preset.py' /app/bin/easyeffects-auto-preset-gui
      install -Dm644 '$REPO_ROOT/data/${APP_ID}.desktop' -t /app/share/applications/
      install -Dm644 '$REPO_ROOT/data/${APP_ID}.metainfo.xml' -t /app/share/metainfo/
      install -Dm644 '$REPO_ROOT/data/icons/${APP_ID}.png' -t /app/share/icons/hicolor/128x128/apps/
      install -Dm644 '$REPO_ROOT/LICENSE' '$REPO_ROOT/NOTICE' -t /app/share/licenses/${APP_ID}/
      install -d /app/share/easyeffects-auto-preset/presets/
      install -m644 '$REPO_ROOT/presets/'*.json -t /app/share/easyeffects-auto-preset/presets/
    "

  flatpak build-finish "$WORK_DIR/build-dir" \
    --command=easyeffects-auto-preset-gui \
    --share=ipc \
    --share=network \
    --socket=x11 \
    --socket=wayland \
    --socket=pulseaudio \
    --device=dri \
    --talk-name=org.kde.StatusNotifierWatcher \
    --talk-name=org.freedesktop.Notifications \
    --filesystem=xdg-config/easyeffects-auto-preset:create \
    --filesystem=~/.var/app/com.github.wwmm.easyeffects:ro

  flatpak build-export "$WORK_DIR/repo" "$WORK_DIR/build-dir" stable
  flatpak build-bundle "$WORK_DIR/repo" "$OUT_DIR/$BUNDLE_NAME" "$APP_ID" stable --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo
fi

(cd "$OUT_DIR" && sha256sum "$BUNDLE_NAME" > "${BUNDLE_NAME}.sha256" && ln -sf "$BUNDLE_NAME" easyeffects-auto-preset.flatpak)
echo "==> Built Flatpak bundle: $OUT_DIR/$BUNDLE_NAME"

if [[ "${1:-}" == "--install" ]]; then
  echo "==> Installing Flatpak bundle into user installation..."
  flatpak install --user -y --reinstall "$OUT_DIR/$BUNDLE_NAME"
fi
