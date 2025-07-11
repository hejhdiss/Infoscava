# Infoscava - Universal File Analyzer

**Infoscava** is a desktop application for comprehensive file analysis.

<p align="center">
  <img src="icon.jpg" width="128" height="128" alt="Infoscava Icon">
</p>

**Download:**[v2.1.9](https://github.com/hejhdiss/Infoscava/releases/tag/v2.1.9)

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

