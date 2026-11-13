#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
version=$(cat VERSION | tr -d '\r\n')
bundle="plugin/online-source/build/macos/VDJ Companion Source.bundle"
mkdir -p "$bundle/Contents/MacOS"
xcrun clang++ -std=c++17 -O2 -bundle -fvisibility=hidden \
  -arch arm64 -arch x86_64 -mmacosx-version-min=14.0 \
  -Iplugin/sdk -Iplugin/online-source/src \
  -DVDJ_COMPANION_VERSION="\"$version-macos-preview\"" \
  plugin/online-source/src/Main.cpp plugin/online-source/src/VdjCompanionSource.cpp \
  plugin/online-source/platform/macos/HttpClient.cpp \
  -framework CoreFoundation -lcurl -o "$bundle/Contents/MacOS/VDJCompanionSource"
cat > "$bundle/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>VDJCompanionSource</string>
<key>CFBundleIdentifier</key><string>com.rcsy-px.vdj-companion.source</string>
<key>CFBundleName</key><string>VDJ Companion Source</string>
<key>CFBundlePackageType</key><string>BNDL</string>
<key>CFBundleVersion</key><string>$version</string>
<key>CFBundleShortVersionString</key><string>$version</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
</dict></plist>
EOF
codesign --force --sign - "$bundle"
codesign --verify --strict "$bundle"
lipo -verify_arch arm64 x86_64 "$bundle/Contents/MacOS/VDJCompanionSource"
