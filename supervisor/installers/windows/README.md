# AgentOS Windows Installer

## Prerequisites

- WiX Toolset 3.11 or later
- Windows 10 SDK (for code signing, optional)
- Code signing certificate (optional)

## Install WiX Toolset

```powershell
winget install WiXToolset.WiXToolset
```

Or download from: https://wixtoolset.org/

## Build Process

### 1. Prepare Assets

Before building, ensure you have:
- `supervisor.exe` - The supervisor binary
- `config/default.yaml` - Default configuration
- `assets/icons/agentos.ico` - Application icon
- `LICENSE.rtf` - License text (rich text format)

### 2. Build the Installer

```powershell
# Navigate to the installer directory
cd supervisor\installers\windows

# Compile the WiX source files
candle.exe Product.wxs Components.wxs -dSourceDir=%CD% -ext WixUIExtension

# Link the object files to create the MSI
light.exe Product.wixobj Components.wixobj -o AgentOS-v0.1.0.msi -ext WixUIExtension -sice:ICE27
```

### 3. Sign the Installer (Optional)

If you have a code signing certificate:

```powershell
# Sign the MSI
signtool.exe sign /f certificate.pfx /p password /t http://timestamp.digicert.com /d "AgentOS" /du "https://agentos.dev" AgentOS-v0.1.0.msi

# Verify the signature
signtool.exe verify /pa AgentOS-v0.1.0.msi
```

### 4. Test the Installer

```powershell
# Install silently
msiexec.exe /i AgentOS-v0.1.0.msi /qn /l*v install.log

# Uninstall
msiexec.exe /x AgentOS-v0.1.0.msi /qn
```

## Features

- **Per-machine installation**: Installs to `C:\Program Files\AgentOS\`
- **Desktop shortcut**: Creates shortcut on desktop
- **Start Menu**: Creates Start Menu group with shortcuts
- **Environment variables**: Sets `AGENTOS_HOME` and updates `PATH`
- **Automatic upgrades**: Supports major upgrades
- **Clean uninstall**: Removes all files and registry entries

## Customization

### Change Installation Directory

Edit `Product.wxs` and modify the `INSTALLFOLDER` property:

```xml
<Property Id="WIXUI_INSTALLDIR" Value="INSTALLFOLDER" />
<Directory Id="ProgramFiles64Folder">
  <Directory Id="INSTALLFOLDER" Name="AgentOS" />
</Directory>
```

### Add Components

Edit `Components.wxs` and add new `<Component>` elements:

```xml
<Component Id="CMP_MyComponent" Guid="NEW-GUID-HERE">
  <File Id="FIL_MyFile" Source="path\to\file.ext" KeyPath="yes" />
</Component>
```

Remember to reference the component in `Product.wxs`:

```xml
<ComponentRef Id="CMP_MyComponent" />
```

### Customize UI

The installer uses the WiX `WixUI_InstallDir` dialog set. To customize:

1. Copy the WiX source dialogs from `$(WIX)\src\ext\UIExtension\wixlib`
2. Modify the `.wxs` files
3. Include them in your build instead of using `-ext WixUIExtension`

## Troubleshooting

### Build Errors

1. **"The system cannot find the file specified"**
   - Ensure all source files exist
   - Check paths in `Source` attributes

2. **ICE validation errors**
   - Use `-sice:ICE27` to suppress specific ICE errors
   - Run with `-v` for verbose output

3. **Linker errors**
   - Ensure all component GUIDs are unique
   - Check that all components are referenced

### Installation Errors

1. **"Installation failed"**
   - Check Windows Event Log
   - Review `%TEMP%\MSI*.log` files

2. **"Access denied"**
   - Run installer as Administrator
   - Check antivirus software

## References

- [WiX Toolset Documentation](https://wixtoolset.org/documentation/)
- [WiX Tutorial](https://www.firegiant.com/wix/tutorial/)
- [Windows Installer Guide](https://docs.microsoft.com/en-us/windows/win32/msi/windows-installer-portal)
