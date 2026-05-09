#!/bin/bash
# Build script for AgentOS macOS DMG Installer with code signing
# Usage: ./build_dmg.sh [version] [sign]

set -e

VERSION="${1:-0.1.0}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/tmp/agentos-macos-build"
APP_NAME="AgentOS"
BUNDLE_ID="dev.agentos.supervisor"
SIGN_CERTIFICATE="${2:-}"

echo "Building AgentOS macOS Installer v$VERSION"
echo "==========================================="

# Check prerequisites
echo "[1/8] Checking prerequisites..."

if ! command -v go &> /dev/null; then
    echo "ERROR: Go is not installed"
    exit 1
fi

# Clean build directory
echo "[2/8] Preparing build directory..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Create app bundle structure
echo "[3/8] Creating app bundle structure..."
APP_DIR="$BUILD_DIR/$APP_NAME.app"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"
mkdir -p "$APP_DIR/Contents/Frameworks"

# Build universal binary
echo "[4/8] Building Go binaries..."

cd "$SOURCE_DIR/../../"

# Build for Intel (amd64)
echo "  - Building for Intel (amd64)..."
GOOS=darwin GOARCH=amd64 CGO_ENABLED=0 go build \
    -ldflags="-s -w -linkmode external -extldflags=-static" \
    -o "$BUILD_DIR/supervisor-amd64" .

# Build for Apple Silicon (arm64)
echo "  - Building for Apple Silicon (arm64)..."
GOOS=darwin GOARCH=arm64 CGO_ENABLED=0 go build \
    -ldflags="-s -w -linkmode external -extldflags=-static" \
    -o "$BUILD_DIR/supervisor-arm64" .

# Create universal binary
echo "  - Creating universal binary..."
lipo -create -output "$APP_DIR/Contents/MacOS/supervisor" \
    "$BUILD_DIR/supervisor-amd64" \
    "$BUILD_DIR/supervisor-arm64"

# Make executable
chmod +x "$APP_DIR/Contents/MacOS/supervisor"

# Build CLI if exists
if [ -f "cli/main.go" ]; then
    echo "  - Building CLI universal binary..."
    GOOS=darwin GOARCH=amd64 CGO_ENABLED=0 go build \
        -ldflags="-s -w" \
        -o "$BUILD_DIR/cli-amd64" ./cli/
    
    GOOS=darwin GOARCH=arm64 CGO_ENABLED=0 go build \
        -ldflags="-s -w" \
        -o "$BUILD_DIR/cli-arm64" ./cli/
    
    lipo -create -output "$APP_DIR/Contents/MacOS/agentos" \
        "$BUILD_DIR/cli-amd64" \
        "$BUILD_DIR/cli-arm64"
    
    chmod +x "$APP_DIR/Contents/MacOS/agentos"
fi

# Create Info.plist
echo "[5/8] Creating Info.plist..."

# Get build number
BUILD_NUM=$(date +%Y%m%d%H%M%S)

cat > "$APP_DIR/Contents/Info.plist" << INFOPLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>supervisor</string>
    <key>CFBundleIdentifier</key>
    <string>$BUNDLE_ID</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleVersion</key>
    <string>${BUILD_NUM}</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.14</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSBackgroundOnly</key>
    <false/>
    <key>LSUIElement</key>
    <false/>
    <key>CFBundleURLTypes</key>
    <array>
        <dict>
            <key>CFBundleURLName</key>
            <string>${BUNDLE_ID}</string>
            <key>CFBundleURLSchemes</key>
            <array>
                <string>agentos</string>
            </array>
        </dict>
    </array>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright © 2024 AgentOS Team. All rights reserved.</string>
</dict>
</plist>
INFOPLIST_EOF

# Create PkgInfo
echo "APPL????" > "$APP_DIR/Contents/PkgInfo"

# Copy icon if exists
if [ -f "$SOURCE_DIR/../../../assets/icons/agentos.icns" ]; then
    echo "  - Copying icon..."
    cp "$SOURCE_DIR/../../../assets/icons/agentos.icns" "$APP_DIR/Contents/Resources/"
else
    echo "  - Warning: Icon not found, using default"
fi

# Create wrapper script for first-run setup
echo "[6/8] Creating wrapper script..."

cat > "$APP_DIR/Contents/MacOS/agentos-wrapper" << 'WRAPPER_EOF'
#!/bin/bash
# AgentOS wrapper script for initial setup

# Get the directory where the app bundle is located
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENTOS_HOME="$HOME/.agentos"

# Create config directory if it doesn't exist
mkdir -p "$AGENTOS_HOME/config"
mkdir -p "$AGENTOS_HOME/data"

# Copy default config if not exists
if [ ! -f "$AGENTOS_HOME/config/default.yaml" ]; then
    if [ -f "$APP_DIR/Contents/Resources/default.yaml" ]; then
        cp "$APP_DIR/Contents/Resources/default.yaml" "$AGENTOS_HOME/config/"
    fi
fi

# Run supervisor with data directory
exec "$APP_DIR/Contents/MacOS/supervisor" \
    --data-dir "$AGENTOS_HOME/data" \
    --config "$AGENTOS_HOME/config" \
    "$@"
WRAPPER_EOF

chmod +x "$APP_DIR/Contents/MacOS/agentos-wrapper"

# Copy default config
if [ -f "$SOURCE_DIR/../../config/default.yaml" ]; then
    cp "$SOURCE_DIR/../../config/default.yaml" "$APP_DIR/Contents/Resources/"
fi

# Create Background folder for DMG
mkdir -p "$BUILD_DIR/Background"

# Create welcome text
cat > "$BUILD_DIR/Background/Background.txt" << 'BGEOF'

    AgentOS Installer

    Version VERSION_PLACEHOLDER

    Drag AgentOS to your Applications folder.

BGEOF

sed -i '' "s/VERSION_PLACEHOLDER/$VERSION/g" "$BUILD_DIR/Background/Background.txt"

# Create symlink to Applications in DMG
echo "[7/8] Creating DMG..."

# Check for create-dmg or use hdiutil
if command -v create-dmg &> /dev/null; then
    echo "  - Using create-dmg..."
    
    # Create symlink to Applications
    ln -s /Applications "$BUILD_DIR/Applications"
    
    create-dmg \
        --volname "AgentOS Installer" \
        --window-pos 200 120 \
        --window-size 660 400 \
        --icon-size 120 \
        --app-drop-link 400 200 \
        --icon "$APP_NAME.app" 150 200 \
        --icon "Applications" 520 200 \
        --background "$BUILD_DIR/Background/Background.png" \
        --skip-jenkins \
        "$SOURCE_DIR/AgentOS-v${VERSION}.dmg" \
        "$APP_DIR"
    
else
    echo "  - Using hdiutil (create-dmg not found)..."
    
    # Create temporary DMG using hdiutil
    TEMP_DMG="$BUILD_DIR/temp.dmg"
    hdiutil create -srcfolder "$APP_DIR" -volname "AgentOS Installer" -fs HFS+ \
        -format UDRW -size 200m "$TEMP_DMG"
    
    # Mount it
    MOUNT_POINT="/Volumes/AgentOS Installer"
    hdiutil attach "$TEMP_DMG" -mountpoint "$MOUNT_POINT"
    
    # Create symlink to Applications (with retry)
    for i in {1..5}; do
        if [ -d "$MOUNT_POINT" ]; then
            ln -sf /Applications "$MOUNT_POINT/Applications"
            break
        fi
        sleep 1
    done
    
    # Unmount
    hdiutil detach "$MOUNT_POINT" -force
    
    # Convert to compressed DMG
    hdiutil convert "$TEMP_DMG" -format UDZO -o "$SOURCE_DIR/AgentOS-v${VERSION}.dmg"
    
    rm -f "$TEMP_DMG"
fi

# Sign the app if certificate provided
if [ -n "$SIGN_CERTIFICATE" ]; then
    echo "[8/8] Signing app..."
    codesign --force --deep --sign "$SIGN_CERTIFICATE" \
        --entitlements "$SOURCE_DIR/entitlements.plist" \
        --timestamp \
        "$APP_DIR"
    
    if [ -f "$SOURCE_DIR/AgentOS-v${VERSION}.dmg" ]; then
        codesign --force --sign "$SIGN_CERTIFICATE" \
            --timestamp \
            "$SOURCE_DIR/AgentOS-v${VERSION}.dmg"
    fi
fi

# Cleanup
rm -rf "$BUILD_DIR"

# Verify the DMG
if [ -f "$SOURCE_DIR/AgentOS-v${VERSION}.dmg" ]; then
    DMG_SIZE=$(du -h "$SOURCE_DIR/AgentOS-v${VERSION}.dmg" | cut -f1)
    DMG_CHECKSUM=$(shasum -a 256 "$SOURCE_DIR/AgentOS-v${VERSION}.dmg" | cut -d' ' -f1)
    
    echo ""
    echo "==========================================="
    echo "Build complete: AgentOS-v${VERSION}.dmg"
    echo "Size: $DMG_SIZE"
    echo "SHA256: $DMG_CHECKSUM"
    echo "==========================================="
    echo ""
    echo "To mount:"
    echo "  hdiutil attach AgentOS-v${VERSION}.dmg"
    echo ""
    echo "To install:"
    echo "  cp -r /Volumes/AgentOS\\ Installer/AgentOS.app /Applications/"
    echo ""
    echo "To notarize (after signing):"
    echo "  xcrun altool --notarize-app -f AgentOS-v${VERSION}.dmg --apiKey ID --apiKey KEY"
else
    echo "ERROR: DMG file was not created"
    exit 1
fi