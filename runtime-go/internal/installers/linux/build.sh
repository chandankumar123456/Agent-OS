#!/bin/bash
# Build script for AgentOS Linux AppImage

set -e

VERSION="${1:-0.1.0}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/tmp/agentos-appimage-build"
APP_NAME="AgentOS"

echo "Building AgentOS Linux AppImage v$VERSION"
echo "==========================================="

# Check prerequisites
if ! command -v go &> /dev/null; then
    echo "Error: Go is not installed"
    exit 1
fi

# Clean build directory
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Create AppDir structure
echo "Creating AppDir structure..."
APPDIR="$BUILD_DIR/AppDir"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APPDIR/usr/share/metainfo"

# Build Go binary
echo "Building Go binary..."
cd "$SOURCE_DIR/../../"
GOOS=linux GOARCH=amd64 go build -o "$APPDIR/usr/bin/agentos-supervisor" .

chmod +x "$APPDIR/usr/bin/agentos-supervisor"

# Create .desktop file
echo "Creating .desktop file..."
cat > "$APPDIR/usr/share/applications/agentos.desktop" << 'EOF'
[Desktop Entry]
Name=AgentOS
Comment=Local-native runtime for AI agents
Exec=agentos-supervisor
Icon=agentos
Type=Application
Categories=System;Utility;
Terminal=false
StartupNotify=false
X-AppImage-Version=VERSION_PLACEHOLDER
EOF

sed -i "s/VERSION_PLACEHOLDER/$VERSION/g" "$APPDIR/usr/share/applications/agentos.desktop"

# Copy to AppDir root
cp "$APPDIR/usr/share/applications/agentos.desktop" "$APPDIR/"

# Create AppRun script
echo "Creating AppRun script..."
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
# AppRun script for AgentOS AppImage

# Get the directory where the AppImage is located
APPDIR="$(dirname "$(readlink -f "$0")")"
export PATH="$APPDIR/usr/bin:$PATH"

# Set up data directory
AGENTOS_HOME="${AGENTOS_HOME:-$HOME/.agentos}"
mkdir -p "$AGENTOS_HOME/config"
mkdir -p "$AGPDIR/data"

# Copy default config if not exists
if [ ! -f "$AGENTOS_HOME/config/default.yaml" ]; then
    mkdir -p "$AGENTOS_HOME/config"
fi

# Run supervisor with data directory
exec "$APPDIR/usr/bin/agentos-supervisor" \
    --data-dir "$AGENTOS_HOME/data" \
    --config "$AGENTOS_HOME/config" \
    "$@"
EOF

chmod +x "$APPDIR/AppRun"

# Copy icon if exists
if [ -f "$SOURCE_DIR/../../../assets/icons/agentos.png" ]; then
    echo "Copying icon..."
    cp "$SOURCE_DIR/../../../assets/icons/agentos.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/"
    cp "$SOURCE_DIR/../../../assets/icons/agentos.png" "$APPDIR/agentos.png"
else
    echo "Warning: Icon not found, creating placeholder..."
    # Create a simple placeholder or skip
    touch "$APPDIR/agentos.png"
fi

# Create metainfo (AppStream)
echo "Creating metainfo..."
cat > "$APPDIR/usr/share/metainfo/agentos.appdata.xml" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<component type="console-application">
  <id>dev.agentos.supervisor</id>
  <metadata_license>MIT</metadata_license>
  <project_license>MIT</project_license>
  <name>AgentOS</name>
  <summary>Local-native runtime for AI agents</summary>
  <description>
    <p>AgentOS is a local-native runtime for AI agents with desktop automation capabilities.</p>
  </description>
  <categories>
    <category>System</category>
    <category>Utility</category>
  </categories>
  <provides>
    <binary>agentos-supervisor</binary>
  </provides>
  <releases>
    <release version="$VERSION" date="$(date +%Y-%m-%d)"/>
  </releases>
</component>
EOF

# Copy default config
if [ -f "$SOURCE_DIR/../../config/default.yaml" ]; then
    mkdir -p "$APPDIR/etc/agentos"
    cp "$SOURCE_DIR/../../config/default.yaml" "$APPDIR/etc/agentos/"
fi

# Download appimagetool if not exists
APPIMAGETOOL="$BUILD_DIR/appimagetool-x86_64.AppImage"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Downloading appimagetool..."
    wget -q -O "$APPIMAGETOOL" "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$APPIMAGETOOL"
fi

# Build AppImage
echo "Building AppImage..."
cd "$BUILD_DIR"
"$APPIMAGETOOL" AppDir

# Move to output
mv "$BUILD_DIR/AgentOS-x86_64.AppImage" "$SOURCE_DIR/AgentOS-v$VERSION-x86_64.AppImage"
chmod +x "$SOURCE_DIR/AgentOS-v$VERSION-x86_64.AppImage"

# Cleanup
rm -rf "$BUILD_DIR"

# Get file size
APPIMAGE_SIZE=$(du -h "$SOURCE_DIR/AgentOS-v$VERSION-x86_64.AppImage" | cut -f1)

echo ""
echo "==========================================="
echo "Build complete: AgentOS-v$VERSION-x86_64.AppImage"
echo "Size: $APPIMAGE_SIZE"
echo "==========================================="
echo ""
echo "To test:"
echo "  $SOURCE_DIR/AgentOS-v$VERSION-x86_64.AppImage --version"
