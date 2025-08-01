# Infoscava - Universal File Analyzer

**Infoscava** is a desktop application for comprehensive file analysis.

<p align="center">
  <img src="icon.jpg" width="128" height="128" alt="Infoscava Icon">
</p>

**Download:**[v2.1.9](https://github.com/hejhdiss/Infoscava/releases/tag/v2.1.9)

## ⚠️ Notice: No More Binary Releases

Due to frequent antivirus false positives and licensing complications, all future versions of Infoscava will be distributed in **pure Python form only**.

You can run the app using:

```bash
python main.py --file "path to file" --lang (language name in short )
```

```
--file : adds only if you wants to open a file on start.
--lang : not tested.
```

## Key Features in v2.1.9

- **File Analysis:** Metadata, hashes, text, hex, structured data (JSON), image (EXIF, GPS), Base64, entropy, byte histograms.
- **User Interface:** Tabbed design, file browser, drag-and-drop, theme toggle, file watcher, keyboard shortcuts, analysis export.
- **Standalone Windows Executable (.exe):** No Python environment needed.
- **Embedded Icon:** Custom application icon (`icon.ico` included in the repository).
- **Standard Installer:** User-friendly installation.
- **Right-Click Context Menu:** "Open with Infoscava" integration.
- **Security Enhancements:** Basic security checks to prevent loading files from sensitive system directories.
- **Additional Search Tab:** with multi-match highlighting, match navigation, and live results.
- **UI Bug Fix**: Patched issue where the Light (White) Theme was not applied correctly to the QTreeView file browser.

### User Interface:

- Tabbed design for organized analysis views.
- Integrated file browser and drag-and-drop support for easy file loading.
- **Theme Toggle:** Switch between Dark and Light themes.
- **File Watcher:** Automatic reload of the file if changes are detected on disk.
- Keyboard shortcuts for common actions.
- **Analysis Export:** Export comprehensive analysis reports to JSON, TXT, or HTML formats.

### Plugin System:

- **Dynamic Plugin Loading:** Support for custom analysis and reporting plugins defined by .infoscava files (containing Base64-encoded Python code).
- **Plugin Management:** Dialog for loading new plugins, reloading existing ones, and deleting plugins.
- **Dynamic Plugin Tabs:** Plugins can generate their own tabs for custom output, including HTML reports, JSON tables, or plain text.
- **Plugin History:** A dedicated tab to log plugin loading, execution, and deletion events.

### Extended Capabilities via Plugins:

The plugin system in Infoscava is designed to extend the app's core functionality by integrating powerful external tools such as **YARA**, **ExifTool**, and others through built-in Python modules like `os`, `shutil`, and `subprocess`. When bundled via PyInstaller, these capabilities are self-contained, allowing advanced analysis features without requiring external dependencies.

Users can create or install plugins that connect with CLI tools or APIs, enabling **deep file inspection, automated threat detection, and cross-tool orchestration**. However, caution is advised: **plugins from untrusted sources may introduce security risks**, so users should only install those they trust.

The core GUI will remain focused on essential features, while **advanced features are delegated to plugins**, allowing users to customize and scale Infoscava to their specific needs. The system also supports **hook-based on-demand integration**, meaning plugins can act as bridges to other tools or services dynamically. This opens up numerous opportunities for building a powerful and extensible file analysis ecosystem around Infoscava.


## Contribution & Support

We are actively looking for contributors, collaborators, and supporters to help grow Infoscava!

- Problems/Bugs: If you encounter any issues, please use the Discussions section or create a new Issue.
- Contributions: We welcome code contributions, feature suggestions, and any form of support. Feel free to reach out via discussions or pull requests.

We plan to create a Linux version and continue with more updates and bug fixes. Please support and contribute to the community.

## Credits

Developer: Muhammed Shafin P ([@hejhdiss](https://github.com/hejhdiss))

Built with PySide6, PyInstaller, and Inno Setup.(**Python 3.11**)

## License

This project is licensed under the [MIT License](LICENSE.txt).

## Antivirus Detections

It has been reported that Infoscava's compiled binaries may be flagged by some antivirus software as a "Trojan" or similar threat. We want to assure users that Infoscava is an open-source project, and its entire codebase is publicly available for review. These detections are often false positives, common with new or less widely distributed executables that perform file system operations or are packed for distribution. We encourage users to inspect the source code if they have concerns.