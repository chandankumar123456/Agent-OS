#!/bin/bash
# Build script for AgentOS macOS Installer

set -e

VERSION="${1:-0.1.0}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/tmp/agentos-macos-build"
APP_NAME="AgentOS"
BUNDLE_ID="dev.agentos.supervisor"

echo "Building AgentOS macOS Installer v$VERSION"
echo "==========================================="

# Check prerequisites
if ! command -v go &> /dev/null; then
    echo "Error: Go is not installed"
    exit 1
fi

# Clean build directory
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Create app bundle structure
echo "Creating app bundle structure..."
APP_DIR="$BUILD_DIR/$APP_NAME.app"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Build universal binary (Intel + Apple Silicon)
echo "Building Go binary..."
cd "$SOURCE_DIR/../../"

# Build for Intel (amd64)
echo "  - Building for Intel..."
GOOS=darwin GOARCH=amd64 go build -o "$BUILD_DIR/supervisor-amd64" .

# Build for Apple Silicon (arm64)
echo "  - Building for Apple Silicon..."
GOOS=darwin GOARCH=arm64 go build -o "$BUILD_DIR/supervisor-arm64" .

# Create universal binary
echo "  - Creating universal binary..."
lipo -create -output "$APP_DIR/Contents/MacOS/supervisor" \
    "$BUILD_DIR/supervisor-amd64" \
    "$BUILD_DIR/supervisor-arm64"

# Make executable
chmod +x "$APP_DIR/Contents/MacOS/supervisor"

# Create Info.plist
echo "Creating Info.plist..."
cat > "$APP_DIR/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>supervisor</string>
    <key>CFBundleIdentifier</key>
    <string>dev.agentos.supervisor</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>AgentOS</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>VERSION_PLACEHOLDER</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.14</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSBackgroundOnly</key>
    <true/>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
EOF

# Replace version placeholder
sed -i '' "s/VERSION_PLACEHOLDER/$VERSION/g" "$APP_DIR/Contents/Info.plist"

# Copy icon if exists
if [ -f "$SOURCE_DIR/../../../assets/icons/agentos.icns" ]; then
    echo "Copying icon..."
    cp "$SOURCE_DIR/../../../assets/icons/agentos.icns" "$APP_DIR/Contents/Resources/"
else
    echo "Warning: Icon not found, using default"
fi

# Create PkgInfo
echo "APPL????" > "$APP_DIR/Contents/PkgInfo"

# Create wrapper script
echo "Creating wrapper script..."
cat > "$APP_DIR/Contents/MacOS/agentos-wrapper" << 'EOF'
#!/bin/bash
# AgentOS wrapper script

# Get the directory where the app bundle is located
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENTOS_HOME="$HOME/.agentos"

# Create config directory if it doesn't exist
mkdir -p "$AGENTOS_HOME/config"
mkdir -p "$AGENTOS_HOME/data"

# Copy default config if not exists
if [ ! -f "$AGENTOS_HOME/config/default.yaml" ]; then
    cp "$APP_DIR/../Resources/default.yaml" "$AGENTOS_HOME/config/" 2>/dev/null || true
fi

# Run supervisor with data directory
exec "$APP_DIR/MacOS/supervisor" \
    --data-dir "$AGENTOS_HOME/data" \
    --config "$AGENTOS_HOME/config" \
    "$@"
EOF

chmod +x "$APP_DIR/Contents/MacOS/agentos-wrapper"

# Copy default config
if [ -f "$SOURCE_DIR/../../config/default.yaml" ]; then
    cp "$SOURCE_DIR/../../config/default.yaml" "$APP_DIR/Contents/Resources/"
fi

# Create DMG
echo "Creating DMG..."

# Check for create-dmg
if command -v create-dmg &> /dev/null; then
    create-dmg \
        --volname "AgentOS Installer" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --app-drop-link 450 185 \
        --icon "AgentOS.app" 150 185 \
        "$SOURCE_DIR/AgentOS-v$VERSION.dmg" \
        "$APP_DIR"
else
    echo "create-dmg not found, using hdiutil..."
    
    # Create temporary DMG
    TEMP_DMG="$BUILD_DIR/temp.dmg"
    hdiutil create -srcfolder "$APP_DIR" -volname "AgentOS Installer" -fs HFS+ \
        -format UDRW -size 100m "$TEMP_DMG"
    
    # Mount it
    MOUNT_POINT="/Volumes/AgentOS Installer"
    hdiutil attach "$TEMP_DMG" -mountpoint "$MOUNT_POINT"
    
    # Create symlink to Applications
    ln -s /Applications "$MOUNT_POINT/Applications"
    
    # Unmount
    hdiutil detach "$MOUNT_POINT"
    
    # Convert to compressed DMG
    hdiutil convert "$TEMP_DMG" -format UDZO -o "$SOURCE_DIR/AgentOS-v$VERSION.dmg"
fi

# Sign the app if requested
if [ "$SIGN" = "1" ]; then
    echo "Signing app..."
    codesign --force --deep --sign "Developer ID Application" "$APP_DIR"
fi

# Cleanup
rm -rf "$BUILD_DIR"

# Get file size
DMG_SIZE=$(du -h "$SOURCE_DIR/AgentOS-v$VERSION.dmg" | cut -f1)

echo ""
echo "==========================================="
echo "Build complete: AgentOS-v$VERSION.dmg"
echo "Size: $DMG_SIZE"
echo "==========================================="
