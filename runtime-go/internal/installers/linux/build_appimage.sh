#!/bin/bash
# Build script for AgentOS Linux AppImage with code signing
# Usage: ./build_appimage.sh [version] [sign]

set -e

VERSION="${1:-0.1.0}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/tmp/agentos-appimage-build"
APP_NAME="AgentOS"

echo "==========================================="
echo "Building AgentOS AppImage v$VERSION"
echo "==========================================="

# Check prerequisites
echo "[1/7] Checking prerequisites..."

if ! command -v go &> /dev/null; then
    echo "ERROR: Go is not installed"
    exit 1
fi

# Clean build directory
echo "[2/7] Preparing build directory..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/AppDir"

# Create directory structure
echo "[3/7] Creating AppDir structure..."
mkdir -p "$BUILD_DIR/AppDir/usr/bin"
mkdir -p "$BUILD_DIR/AppDir/usr/share/applications"
mkdir -p "$BUILD_DIR/AppDir/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$BUILD_DIR/AppDir/usr/share/metainfo"
mkdir -p "$BUILD_DIR/AppDir/usr/lib"
mkdir -p "$BUILD_DIR/AppDir/etc/agentos"

# Build Go binary with static linking
echo "[4/7] Building Go binary..."

cd "$SOURCE_DIR/../../"

# Build supervisor binary
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags="-s -w -linkmode external -extldflags=-static" \
    -o "$BUILD_DIR/AppDir/usr/bin/agentos-supervisor" .

chmod +x "$BUILD_DIR/AppDir/usr/bin/agentos-supervisor"

# Build CLI if exists
if [ -f "cli/main.go" ]; then
    echo "  - Building CLI..."
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
        -ldflags="-s -w -linkmode external -extldflags=-static" \
        -o "$BUILD_DIR/AppDir/usr/bin/agentos-cli" ./cli/
    chmod +x "$BUILD_DIR/AppDir/usr/bin/agentos-cli"
fi

# Create .desktop file
echo "[5/7] Creating .desktop file..."

cat > "$BUILD_DIR/AppDir/usr/share/applications/dev.agentos.supervisor.desktop" << 'DESKTOP_EOF'
[Desktop Entry]
Name=AgentOS
Comment=Local-native runtime for AI agents with desktop automation
Exec=agentos-supervisor
Icon=agentos
Type=Application
Categories=System;Utility;Development;
Terminal=false
StartupNotify=false
X-AppImage-Version=VERSION_PLACEHOLDER
DESKTOP_EOF

sed -i "s/VERSION_PLACEHOLDER/$VERSION/g" "$BUILD_DIR/AppDir/usr/share/applications/dev.agentos.supervisor.desktop"

# Copy to AppDir root
cp "$BUILD_DIR/AppDir/usr/share/applications/dev.agentos.supervisor.desktop" "$BUILD_DIR/AppDir/agentos.desktop"

# Create AppRun script
echo "  - Creating AppRun script..."

cat > "$BUILD_DIR/AppDir/AppRun" << 'APPRUN_EOF'
#!/bin/bash
# AppRun script for AgentOS AppImage

# Get the directory where the AppImage is mounted
APPDIR="${APPIMAGE%/*}"
if [ "$APPDIR" = "$APPIMAGE" ]; then
    APPDIR="$(pwd)"
fi

# Ensure absolute path
if [[ ! "$APPDIR" = /* ]]; then
    APPDIR="$(pwd)/$APPDIR"
fi

export PATH="$APPDIR/usr/bin:$PATH"
export LD_LIBRARY_PATH="$APPDIR/usr/lib:$LD_LIBRARY_PATH"

# Set up data directory
AGENTOS_HOME="${AGENTOS_HOME:-$HOME/.agentos}"
mkdir -p "$AGENTOS_HOME/config"
mkdir -p "$AGENTOS_HOME/data"

# Copy default config if not exists
if [ ! -f "$AGENTOS_HOME/config/default.yaml" ]; then
    if [ -f "$APPDIR/etc/agentos/default.yaml" ]; then
        cp "$APPDIR/etc/agentos/default.yaml" "$AGENTOS_HOME/config/default.yaml"
    fi
fi

# Run supervisor with data directory
exec "$APPDIR/usr/bin/agentos-supervisor" \
    --data-dir "$AGENTOS_HOME/data" \
    --config "$AGENTOS_HOME/config" \
    "$@"
APPRUN_EOF

chmod +x "$BUILD_DIR/AppDir/AppRun"

# Create icons and metadata
echo "[6/7] Creating icons and metadata..."

# Copy icon if exists
if [ -f "$SOURCE_DIR/../../../assets/icons/agentos.png" ]; then
    cp "$SOURCE_DIR/../../../assets/icons/agentos.png" "$BUILD_DIR/AppDir/usr/share/icons/hicolor/256x256/apps/"
    cp "$SOURCE_DIR/../../../assets/icons/agentos.png" "$BUILD_DIR/AppDir/agentos.png"
else
    echo "  - Creating placeholder icon..."
    # Minimal 1x1 transparent PNG
    echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwADggF/lC2NkgAAAABJRU5ErkJggg==" | base64 -d > "$BUILD_DIR/AppDir/agentos.png"
fi

# Create AppStream metainfo
cat > "$BUILD_DIR/AppDir/usr/share/metainfo/dev.agentos.supervisor.appdata.xml" << METAINFO_EOF
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>dev.agentos.supervisor</id>
  <metadata_license>MIT</metadata_license>
  <project_license>MIT</project_license>
  <name>AgentOS</name>
  <summary>Local-native runtime for AI agents</summary>
  <description>
    <p>AgentOS is a local-native runtime for AI agents with desktop automation. It provides structured agent execution via LangGraph and Model Context Protocol tools.</p>
  </description>
  <categories>
    <category>System</category>
    <category>Utility</category>
    <category>Development</category>
  </categories>
  <url type="homepage">https://agentos.dev</url>
  <provides>
    <binary>agentos-supervisor</binary>
  </provides>
  <releases>
    <release version="$VERSION" date="$(date +%Y-%m-%d)" type="stable"/>
  </releases>
</component>
METAINFO_EOF

# Copy configuration files
echo "  - Copying configuration files..."

if [ -f "$SOURCE_DIR/../../config/default.yaml" ]; then
    cp "$SOURCE_DIR/../../config/default.yaml" "$BUILD_DIR/AppDir/etc/agentos/"
fi

if [ -f "$SOURCE_DIR/../../LICENSE" ]; then
    cp "$SOURCE_DIR/../../LICENSE" "$BUILD_DIR/AppDir/"
fi

# Build AppImage
echo "[7/7] Building AppImage..."

cd "$BUILD_DIR"

# Download appimagetool if not exists
APPIMAGETOOL="$BUILD_DIR/appimagetool"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "  - Downloading appimagetool..."
    
    if command -v curl &> /dev/null; then
        curl -sL "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -o "$APPIMAGETOOL"
    elif command -v wget &> /dev/null; then
        wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -O "$APPIMAGETOOL"
    else
        echo "ERROR: Neither curl nor wget found"
        exit 1
    fi
    
    chmod +x "$APPIMAGETOOL"
fi

# Try appimagetool first
if "$APPIMAGETOOL" AppDir 2>/dev/null; then
    echo "  - AppImage generated successfully"
else
    echo "  - appimagetool failed, trying docker method..."
    
    # Try docker-based build
    if command -v docker &> /dev/null && docker ps &> /dev/null 2>&1; then
        docker run --rm \
            -v "$BUILD_DIR:/build" \
            -w /build \
            ghcr.io/nicoulaj/appimagetool:latest \
            /usr/bin/appimagetool AppDir
    else
        echo "WARNING: AppImage generation failed. Files are ready in: $BUILD_DIR/AppDir"
        echo "To build manually, run: $APPIMAGETOOL AppDir"
        exit 0
    fi
fi

# Move to output
if [ -f "$BUILD_DIR/AgentOS-x86_64.AppImage" ]; then
    mv "$BUILD_DIR/AgentOS-x86_64.AppImage" "$SOURCE_DIR/AgentOS-v$VERSION-x86_64.AppImage"
    chmod +x "$SOURCE_DIR/AgentOS-v$VERSION-x86_64.AppImage"
fi

# Cleanup
rm -rf "$BUILD_DIR"

# Show results
if [ -f "$SOURCE_DIR/AgentOS-v$VERSION-x86_64.AppImage" ]; then
    APPIMAGE_SIZE=$(du -h "$SOURCE_DIR/AgentOS-v$VERSION-x86_64.AppImage" | cut -f1)
    APPIMAGE_CHECKSUM=$(sha256sum "$SOURCE_DIR/AgentOS-v$VERSION-x86_64.AppImage" | cut -d' ' -f1)
    
    echo ""
    echo "==========================================="
    echo "Build complete: AgentOS-v$VERSION-x86_64.AppImage"
    echo "Size: $APPIMAGE_SIZE"
    echo "SHA256: $APPIMAGE_CHECKSUM"
    echo "==========================================="
    echo ""
    echo "To test:"
    echo "  chmod +x $SOURCE_DIR/AgentOS-v$VERSION-x86_64.AppImage"
    echo "  $SOURCE_DIR/AgentOS-v$VERSION-x86_64.AppImage --version"
    echo ""
    echo "To install:"
    echo "  cp $SOURCE_DIR/AgentOS-v$VERSION-x86_64.AppImage /usr/local/bin/agentos"
    echo "  chmod +x /usr/local/bin/agentos"
else
    echo "ERROR: AppImage build failed"
    exit 1
fi