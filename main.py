import sys
import os
import hashlib
import chardet
import mimetypes
import datetime
import json
import xml.etree.ElementTree as ET
import csv
import io
import base64
import math
import argparse
from functools import partial
import importlib.util # For dynamic module loading
import importlib # For module reloading
import shutil # For copying plugin files
import traceback # For detailed error logging

try:
    from PIL import Image, ExifTags
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use('QtAgg')
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLabel, QTabWidget, QTextEdit, QStatusBar,
    QMessageBox, QProgressBar, QSizePolicy, QScrollArea, QComboBox,
    QSplitter, QFileSystemModel, QTreeView, QLineEdit, QDialog,
    QMenuBar, QToolBar, QMenu, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QHeaderView, QTableWidget, QTableWidgetItem,
    QSpinBox, QCheckBox, QTextBrowser, QListWidget, QListWidgetItem,
    QStackedWidget, QFormLayout, QDoubleSpinBox, QStyle,QProxyStyle, QStyleOption # Added QFormLayout, QDoubleSpinBox
)
from PySide6.QtCore import (
    Qt, QThread, Signal, QRunnable, QThreadPool, QUrl, QTimer,
    QFileSystemWatcher, QCoreApplication, QTranslator, QLocale, QSize,
    QPoint, QRect, QDir, Slot, QObject
)
from PySide6.QtGui import (
    QIcon, QTextCharFormat, QTextCursor, QSyntaxHighlighter,
    QTextDocument, QFont, QColor, QPalette, QDesktopServices,
    QImage, QPixmap, QPainter, QBrush, QKeySequence, QAction, QFontDatabase,
    QTextLayout, QTextLine
)

# --- Constants ---
# These will now be managed by settings, but provide initial defaults if settings file is absent
# MAX_FILE_SIZE_FOR_FULL_READ = 20 * 1024 * 1024 # 20 MB limit for full file read
# MAX_TEXT_PREVIEW_LINES = 10000
# MAX_HEX_PREVIEW_BYTES = 16384
# MAX_STRUCTURED_PREVIEW_LINES = 100
# MAX_PLUGIN_HISTORY_ENTRIES = 200 # Limit for plugin history log

SUPPORTED_ENCODINGS = ['UTF-8', 'UTF-16', 'UTF-16BE', 'UTF-16LE', 'UTF-32', 'UTF-32BE', 'UTF-32LE', 'UTF-7', 'ASCII', 'Windows-1250', 'Windows-1251', 'Windows-1252', 'Windows-1253', 'Windows-1254', 'Windows-1255', 'Windows-1256', 'Windows-1257', 'Windows-1258', 'CP437', 'CP720', 'CP737', 'CP775', 'CP850', 'CP852', 'CP855', 'CP856', 'CP857', 'CP858', 'CP860', 'CP861', 'CP862', 'CP863', 'CP864', 'CP865', 'CP866', 'CP869', 'GB2312', 'GBK', 'GB18030', 'Big5', 'HKSCS', 'Shift-JIS', 'EUC-JP', 'ISO-2022-JP', 'EUC-KR', 'ISO-2022-KR', 'KOI8-R', 'KOI8-U', 'Macintosh', 'MacCyrillic', 'MacGreek', 'MacTurkish', 'HP-Roman8']

# Path for theme settings file (in user's home directory)
THEME_SETTINGS_FILE = os.path.join(os.path.expanduser('~'), '.infoscava_theme.json')
# Path for application settings file
APP_SETTINGS_FILE = os.path.join(os.path.expanduser('~'), '.infoscava_settings.json')
# Directory for plugin definition files (.infoscava)
PLUGIN_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
# File to store persistent list of loaded plugins
PLUGIN_CONFIG_FILE = os.path.join(PLUGIN_DIRECTORY, "plugins_config.json")
# File to store plugin history
PLUGIN_HISTORY_FILE = os.path.join(PLUGIN_DIRECTORY, "plugin_history.json")

# Default settings values
DEFAULT_APP_SETTINGS = {
    'MAX_FILE_SIZE_FOR_FULL_READ': 20 * 1024 * 1024, # 20 MB
    'MAX_TEXT_PREVIEW_LINES': 10000,
    'MAX_HEX_PREVIEW_BYTES': 16384,
    'MAX_STRUCTURED_PREVIEW_LINES': 100,
    'MAX_PLUGIN_HISTORY_ENTRIES': 200
}


# --- Utility Functions ---

def human_readable_size(size_bytes):
    """Converts bytes to a human-readable format (KB, MB, GB, etc.)."""
    if size_bytes == 0:
        return "0 Bytes"
    units = ("Bytes", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {units[i]}"

def calculate_hash(filepath, hash_algo):
    """Calculates the hash of a file using the specified algorithm."""
    hasher = hash_algo()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192): # Read in chunks to handle large files efficiently
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        return f"Error: {e}"

def detect_encoding(filepath):
    """Detects the character encoding of a file using chardet."""
    try:
        with open(filepath, 'rb') as f:
            raw_data = f.read(1024 * 1024) # Read up to 1MB for detection
        result = chardet.detect(raw_data)
        return result['encoding'], result['confidence']
    except Exception as e:
        return None, 0.0

def calculate_shannon_entropy(filepath):
    """Calculates the Shannon entropy of a file."""
    try:
        with open(filepath, 'rb') as f:
            byte_data = f.read()
        if not byte_data:
            return 0.0

        frequency = [0] * 256
        for byte in byte_data:
            frequency[byte] += 1

        entropy = 0.0
        total_bytes = len(byte_data)
        for count in frequency:
            if count > 0:
                probability = count / total_bytes
                entropy -= probability * math.log2(probability)
        return entropy
    except Exception as e:
        return f"Error: {e}"

def get_mime_type(filepath):
    """Guesses the MIME type of a file. Adds custom types for common extensions."""
    mime_type, _ = mimetypes.guess_type(filepath)
    if mime_type:
        return mime_type
    _, ext = os.path.splitext(filepath)
    ext = ext.lower()
    # Custom MIME type mappings
    if ext == '.json': return 'application/json'
    if ext == '.xml': return 'application/xml'
    if ext == '.csv': return 'text/csv'
    if ext in ['.jpg', '.jpeg']: return 'image/jpeg'
    if ext == '.png': return 'image/png'
    if ext == '.gif': return 'image/gif'
    if ext == '.bmp': return 'image/bmp'
    if ext == '.txt': return 'text/plain'
    if ext == '.bin': return 'application/octet-stream'
    return 'application/octet-octet-stream'

# --- Threading for File Analysis ---

class FileAnalyzerThread(QThread):
    """
    A QThread subclass for performing file analysis in a separate thread.
    Emits signals for completion, errors, and progress updates.
    """
    finished = Signal(dict) # Emits analysis results dictionary
    error = Signal(str)     # Emits error message string
    progress = Signal(int, str) # Emits progress percentage and message

    def __init__(self, filepath, max_file_size_for_full_read, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.max_file_size_for_full_read = max_file_size_for_full_read

    def run(self):
        """Performs the file analysis operations."""
        results = {}
        try:
            self.progress.emit(0, self.tr("Starting analysis..."))

            # Basic File Info
            file_stat = os.stat(self.filepath)
            results['filename'] = os.path.basename(self.filepath)
            results['filepath'] = self.filepath
            results['size'] = file_stat.st_size
            results['last_modified'] = datetime.datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            results['mime_type'] = get_mime_type(self.filepath)
            self.progress.emit(10, self.tr("Basic info gathered."))

            # Encoding Detection
            encoding, confidence = detect_encoding(self.filepath)
            results['encoding'] = encoding
            results['encoding_confidence'] = confidence * 100 # Convert to percentage
            self.progress.emit(30, self.tr("Encoding detected."))

            # Hash Calculations
            results['sha256_hash'] = calculate_hash(self.filepath, hashlib.sha256)
            self.progress.emit(60, self.tr("SHA-256 calculated."))
            results['md5_hash'] = calculate_hash(self.filepath, hashlib.md5)
            self.progress.emit(90, self.tr("MD5 calculated."))

            # Entropy Calculation
            results['entropy'] = calculate_shannon_entropy(self.filepath)
            self.progress.emit(95, self.tr("Entropy calculated."))

            # Image Metadata (if PIL is available and it's an image)
            if PIL_AVAILABLE and results['mime_type'].startswith('image/'):
                try:
                    with Image.open(self.filepath) as img:
                        results['image_format'] = img.format
                        results['image_dimensions'] = f"{img.width}x{img.height}"
                        results['image_mode'] = img.mode
                        exif_data = {}
                        if hasattr(img, '_getexif'):
                            raw_exif = img._getexif()
                            if raw_exif is not None:
                                for tag, value in raw_exif.items():
                                    decoded = ExifTags.TAGS.get(tag, tag)
                                    # Attempt to decode bytes to string for display
                                    if isinstance(value, bytes):
                                        try:
                                            value = value.decode('utf-8', errors='ignore')
                                        except:
                                            pass
                                    exif_data[decoded] = value
                        results['exif_data'] = exif_data

                        # Extract GPS Info from EXIF
                        gps_info = {}
                        if 'GPSInfo' in exif_data:
                            gps_data = exif_data.get('GPSInfo', {}) # GPSInfo tag number
                            # Latitude
                            if 1 in gps_data and 2 in gps_data:
                                lat_ref = gps_data[1]
                                lat_tuple = gps_data[2]
                                latitude = sum(float(x) / 60**i for i, x in enumerate(lat_tuple))
                                if lat_ref == 'S': latitude = -latitude
                                gps_info['Latitude'] = latitude
                            # Longitude
                            if 3 in gps_data and 4 in gps_data:
                                lon_ref = gps_data[3]
                                lon_tuple = gps_data[4]
                                longitude = sum(float(x) / 60**i for i, x in enumerate(lon_tuple))
                                if lon_ref == 'W': longitude = -longitude
                                gps_info['Longitude'] = longitude
                            # Altitude
                            if 5 in gps_data and 6 in gps_data:
                                alt_ref = gps_data[5]
                                altitude = gps_data[6]
                                gps_info['Altitude'] = f"{altitude[0]/altitude[1]:.2f}m" if isinstance(altitude, tuple) else altitude
                                if alt_ref == 1: gps_info['Altitude'] += " (below sea level)"
                        results['gps_data'] = gps_info

                except Exception as e:
                    results['image_metadata_error'] = f"Could not read image metadata: {e}"
            self.progress.emit(98, self.tr("Image metadata processed."))

            self.progress.emit(100, self.tr("Analysis complete."))
            self.finished.emit(results) # Emit results upon successful completion
        except Exception as e:
            self.error.emit(self.tr(f"Error during analysis: {e}")) # Emit error message

# --- UI Tab Widgets ---

class MetadataTab(QWidget):
    """Displays general file metadata."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.labels = {}
        # Define metadata fields to display
        fields = [
            ("Filename", "filename"), ("Full Path", "filepath"),
            ("MIME Type", "mime_type"), ("File Size", "size"),
            ("Last Modified", "last_modified"), ("Encoding", "encoding"),
            ("Encoding Confidence", "encoding_confidence"),
            ("SHA-256 Hash", "sha256_hash"), ("MD5 Hash", "md5_hash"),
            ("Entropy", "entropy")
        ]

        for display_name, key in fields:
            row_layout = QHBoxLayout()
            label_name = QLabel(self.tr(f"<b>{display_name}:</b>"))
            label_value = QLabel(self.tr("N/A"))
            label_value.setTextInteractionFlags(Qt.TextSelectableByMouse) # Allow text selection
            self.labels[key] = label_value
            row_layout.addWidget(label_name)
            row_layout.addWidget(label_value, 1)
            row_layout.addStretch(1) # Push content to the left
            self.layout.addLayout(row_layout)

        self.layout.addStretch(1) # Push content to the top

    def update_metadata(self, metadata):
        """Updates the displayed metadata with new analysis results."""
        self.labels['filename'].setText(metadata.get('filename', self.tr("N/A")))
        self.labels['filepath'].setText(metadata.get('filepath', self.tr("N/A")))
        self.labels['mime_type'].setText(metadata.get('mime_type', self.tr("N/A")))
        self.labels['size'].setText(human_readable_size(metadata.get('size', 0)))
        self.labels['last_modified'].setText(metadata.get('last_modified', self.tr("N/A")))
        self.labels['encoding'].setText(metadata.get('encoding', self.tr("N/A")))
        # Encoding confidence is already multiplied by 100 in FileAnalyzerThread
        self.labels['encoding_confidence'].setText(f"{metadata.get('encoding_confidence', 0.0):.2f}%")
        self.labels['sha256_hash'].setText(metadata.get('sha256_hash', self.tr("N/A")))
        self.labels['md5_hash'].setText(metadata.get('md5_hash', self.tr("N/A")))
        self.labels['entropy'].setText(f"{metadata.get('entropy', 0.0):.4f}")

class TextHighlighter(QSyntaxHighlighter):
    """Custom syntax highlighter for text search results."""
    def __init__(self, parent):
        super().__init__(parent)
        self.highlight_format = QTextCharFormat()
        self.additional_highlights = [] # For multiple search matches

    def highlightBlock(self, text):
        """Applies highlighting to a block of text."""
        for pos, length, fmt in self.additional_highlights:
            # Check if the highlight range overlaps with the current text block
            if pos <= self.currentBlock().position() + len(text) and pos + length >= self.currentBlock().position():
                relative_start = max(0, pos - self.currentBlock().position())
                relative_end = min(len(text), pos + length - self.currentBlock().position())
                self.setFormat(relative_start, relative_end - relative_start, fmt)

    def set_highlights(self, ranges_and_formats):
        """Sets multiple highlight ranges with their formats."""
        # ranges_and_formats is a list of (pos, length, QTextCharFormat) tuples
        self.additional_highlights = ranges_and_formats
        self.rehighlight() # Reapply all highlights


class TextTab(QWidget):
    """Displays file content as text, with encoding selection and highlighting functionality."""
    text_content_changed = Signal(str) # New signal: Emits the decoded text content

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.file_content = b""
        self.current_encoding = "UTF-8"
        self.max_text_preview_lines = DEFAULT_APP_SETTINGS['MAX_TEXT_PREVIEW_LINES'] # Default value

        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel(self.tr("Encoding:")))
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(SUPPORTED_ENCODINGS)
        self.encoding_combo.setCurrentText("UTF-8")
        self.encoding_combo.currentTextChanged.connect(self._redecode_text)
        control_layout.addWidget(self.encoding_combo)
        control_layout.addStretch(1)
        self.layout.addLayout(control_layout)

        self.text_editor = QTextEdit()
        self.text_editor.setReadOnly(True)
        self.text_editor.setFont(QFont("Monospace", 10))
        self.text_editor.setStyleSheet("QTextEdit { line-height: 1.5; }")
        self.text_editor.setLineWrapMode(QTextEdit.NoWrap)
        self.text_editor.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.line_number_area = LineNumberArea(self.text_editor)
        text_editor_layout = QHBoxLayout()
        text_editor_layout.addWidget(self.line_number_area)
        text_editor_layout.addWidget(self.text_editor)
        text_editor_layout.setContentsMargins(0,0,0,0)
        self.layout.addLayout(text_editor_layout)

        self.text_editor.verticalScrollBar().valueChanged.connect(self.line_number_area.update)
        self.text_editor.textChanged.connect(self.line_number_area.update)
        self.text_editor.cursorPositionChanged.connect(self.line_number_area.update)
        self.text_editor.document().blockCountChanged.connect(self.line_number_area._on_block_count_changed)
        self.text_editor.document().contentsChange.connect(self._handle_contents_change)

        self.highlighter = TextHighlighter(self.text_editor.document())

    def _handle_contents_change(self, position, charsRemoved, charsAdded):
        self.line_number_area.update_width()
        self.line_number_area.update()

    def set_file_content(self, raw_bytes, encoding_hint=None, is_large=False, max_text_preview_lines=None):
        self.file_content = raw_bytes
        self.is_large_file = is_large
        if max_text_preview_lines is not None:
            self.max_text_preview_lines = max_text_preview_lines
        
        # Clear existing highlights when new content is set
        self.highlighter.set_highlights([])

        if is_large:
            display_text = self.tr(f"File too large for full display. Showing first {self.max_text_preview_lines} lines.\n")
            display_text += self.tr("--- Preview Mode ---\n")
            try:
                decoded_text = self.file_content.decode(encoding_hint or "utf-8", errors='replace')
                lines = decoded_text.splitlines()
                display_text += "\n".join(lines[:self.max_text_preview_lines])
            except Exception as e:
                display_text += self.tr(f"Could not decode preview with {encoding_hint}: {e}\n")
                display_text += self.tr("Attempting with UTF-8...\n")
                try:
                    display_text += self.file_content.decode("utf-8", errors='replace')
                except Exception as e:
                    display_text += self.tr(f"Could not decode with UTF-8: {e}")
            self.text_editor.setPlainText(display_text)
            self.text_content_changed.emit(display_text) # Emit the (truncated) text
        else:
            if encoding_hint and encoding_hint in SUPPORTED_ENCODINGS:
                self.encoding_combo.setCurrentText(encoding_hint)
            else:
                self.encoding_combo.setCurrentText("UTF-8")
            self._redecode_text(self.encoding_combo.currentText())

    def _redecode_text(self, encoding):
        self.current_encoding = encoding
        try:
            decoded_text = self.file_content.decode(encoding, errors='replace')
            self.text_editor.setPlainText(decoded_text)
            self.text_editor.verticalScrollBar().setValue(0)
            self.text_content_changed.emit(decoded_text) # Emit the full decoded text
            # Clear existing highlights when text is redecoded
            self.highlighter.set_highlights([])
        except LookupError:
            error_text = self.tr(f"Error: Encoding '{encoding}' not supported by Python. Please choose another.")
            self.text_editor.setPlainText(error_text)
            self.text_content_changed.emit(error_text)
            self.highlighter.set_highlights([])
        except Exception as e:
            error_text = self.tr(f"Error decoding with '{encoding}': {e}\n\nAttempting with UTF-8 (replace errors)...")
            try:
                self.text_editor.setPlainText(self.file_content.decode("utf-8", errors='replace'))
                self.text_content_changed.emit(self.text_editor.toPlainText())
            except Exception as e_utf8:
                critical_error_text = self.tr(f"Critical Error: Could not decode with any fallback: {e_utf8}")
                self.text_editor.setPlainText(critical_error_text)
                self.text_content_changed.emit(critical_error_text)
            self.highlighter.set_highlights([])

    def highlight_matches(self, matches_data, current_match_index, query_length):
        """
        Applies highlighting to the QTextEdit based on search results.
        matches_data: List of (start_pos, line_number) tuples.
        current_match_index: Index of the match to highlight differently.
        query_length: Length of the search query.
        """
        all_highlights = []

        # Format for the current match
        current_match_format = QTextCharFormat()
        current_match_format.setBackground(QColor("orange"))
        current_match_format.setForeground(QColor("black"))

        # Format for other matches
        other_match_format = QTextCharFormat()
        other_match_format.setBackground(QColor("yellow"))
        other_match_format.setForeground(QColor("black"))

        for i, (start_pos, _) in enumerate(matches_data):
            fmt = current_match_format if i == current_match_index else other_match_format
            all_highlights.append((start_pos, query_length, fmt))
        
        self.highlighter.set_highlights(all_highlights)

        # Scroll to the current match
        if matches_data and current_match_index != -1:
            cursor = QTextCursor(self.text_editor.document())
            cursor.setPosition(matches_data[current_match_index][0])
            self.text_editor.setTextCursor(cursor)
            self.text_editor.ensureCursorVisible()


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.editor.verticalScrollBar().valueChanged.connect(self.update)
        self.editor.textChanged.connect(self.update)
        self.editor.cursorPositionChanged.connect(self.update)
        self.editor.document().blockCountChanged.connect(self._on_block_count_changed)
        self.update_width()

    def sizeHint(self):
        if self.editor.document():
            return QSize(self.editor.fontMetrics().horizontalAdvance(str(self.editor.document().blockCount())) + 10, 0)
        return QSize(50, 0)

    @Slot()
    def _on_block_count_changed(self):
        self.update_width()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor(240, 240, 240))

        if not self.editor or not self.editor.document():
            painter.end()
            return

        block = self.editor.document().firstBlock() # Start from the first block
        block_number = 0
        current_line_number = self.editor.textCursor().blockNumber() + 1

        # Get the viewport's top and bottom y-coordinates
        viewport_top = self.editor.verticalScrollBar().value()
        viewport_bottom = viewport_top + self.editor.viewport().height()

        # Iterate through all blocks
        while block.isValid():
            block_number += 1
            # Get the block's bounding rectangle in document coordinates
            block_rect = self.editor.document().documentLayout().blockBoundingRect(block)
            
            # Convert block_rect to viewport coordinates
            block_top_in_viewport = block_rect.top() - viewport_top
            block_bottom_in_viewport = block_rect.bottom() - viewport_top

            # Only draw if the block is visible in the viewport
            if block_bottom_in_viewport >= 0 and block_top_in_viewport <= self.editor.viewport().height():
                number = str(block_number)
                painter.setPen(QColor(120, 120, 120))
                if block_number == current_line_number:
                    painter.setPen(QColor("blue"))
                    painter.setFont(QFont(painter.font().family(), painter.font().pointSize(), QFont.Bold))

                # Draw the text at the calculated position
                painter.drawText(0, int(block_top_in_viewport), self.width() - 5, int(block_rect.height()),
                                 Qt.AlignRight | Qt.AlignVCenter, number)
            
            block = block.next()
        painter.end()

    def update_width(self):
        if self.editor.document():
            width = self.editor.fontMetrics().horizontalAdvance(str(self.editor.document().blockCount())) + 10
            if self.width() != width:
                self.setFixedWidth(width)


class HexView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.file_content = b""
        self.is_large_file = False
        self.max_hex_preview_bytes = DEFAULT_APP_SETTINGS['MAX_HEX_PREVIEW_BYTES'] # Default value

        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel(self.tr("Bytes per line:")))
        self.width_combo = QComboBox()
        self.width_combo.addItems(["8", "16", "32", "64"])
        self.width_combo.setCurrentText("16")
        self.width_combo.currentTextChanged.connect(self._update_hex_display)
        control_layout.addWidget(self.width_combo)

        self.toggle_non_printables_checkbox = QCheckBox(self.tr("Show non-printables"))
        self.toggle_non_printables_checkbox.setChecked(False)
        self.toggle_non_printables_checkbox.stateChanged.connect(self._update_hex_display)
        control_layout.addWidget(self.toggle_non_printables_checkbox)

        control_layout.addStretch(1)
        self.layout.addLayout(control_layout)

        self.hex_editor = QTextEdit()
        self.hex_editor.setReadOnly(True)
        self.hex_editor.setFont(QFont("Monospace", 9))
        self.hex_editor.setLineWrapMode(QTextEdit.NoWrap)
        self.hex_editor.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layout.addWidget(self.hex_editor)

    def set_file_content(self, raw_bytes, is_large=False, max_hex_preview_bytes=None):
        self.file_content = raw_bytes
        self.is_large_file = is_large
        if max_hex_preview_bytes is not None:
            self.max_hex_preview_bytes = max_hex_preview_bytes
        self._update_hex_display()

    def _update_hex_display(self):
        bytes_per_line = int(self.width_combo.currentText())
        show_non_printables = self.toggle_non_printables_checkbox.isChecked()
        hex_output = []
        data_to_display = self.file_content

        if self.is_large_file:
            data_to_display = self.file_content[:self.max_hex_preview_bytes]
            hex_output.append(self.tr(f"File too large for full hex dump. Showing first {self.max_hex_preview_bytes} bytes.\n"))
            hex_output.append(self.tr("--- Preview Mode ---\n"))

        for i in range(0, len(data_to_display), bytes_per_line):
            chunk = data_to_display[i:i + bytes_per_line]
            hex_part = ' '.join(f'{byte:02x}' for byte in chunk)
            ascii_part = ''
            for byte in chunk:
                if 32 <= byte <= 126 or (show_non_printables and byte in range(0, 256)):
                    ascii_part += chr(byte) if 32 <= byte <= 126 else '.'
                else:
                    ascii_part += '.'
            hex_output.append(f'{i:08x}: {hex_part.ljust(bytes_per_line * 3 - 1)} | {ascii_part}')
        self.hex_editor.setPlainText('\n'.join(hex_output))
        self.hex_editor.verticalScrollBar().setValue(0)

class StructuredView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.stacked_widget = QStackedWidget()
        self.layout.addWidget(self.stacked_widget)

        # Text editor for JSON, XML, or general text
        self.text_editor = QTextEdit()
        self.text_editor.setReadOnly(True)
        self.text_editor.setFont(QFont("Monospace", 10))
        self.text_editor.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.stacked_widget.addWidget(self.text_editor) # Index 0

        # Table widget for CSV and JSON that can be tabled
        self.table_widget = QTableWidget()
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers) # Make table read-only
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setSelectionMode(QTableWidget.SingleSelection)
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive) # Allow resizing columns
        self.table_widget.verticalHeader().setVisible(False) # Hide row numbers
        self.stacked_widget.addWidget(self.table_widget) # Index 1

        self.max_structured_preview_lines = DEFAULT_APP_SETTINGS['MAX_STRUCTURED_PREVIEW_LINES'] # Default value

    def set_file_content(self, raw_bytes, mime_type, encoding_hint="utf-8", is_large=False, max_structured_preview_lines=None):
        self.text_editor.clear()
        self.table_widget.clear()
        self.table_widget.setRowCount(0)
        self.table_widget.setColumnCount(0)
        if max_structured_preview_lines is not None:
            self.max_structured_preview_lines = max_structured_preview_lines

        decoded_content = ""
        try:
            decoded_content = raw_bytes.decode(encoding_hint, errors='replace')
        except Exception:
            try:
                decoded_content = raw_bytes.decode("utf-8", errors='replace')
            except Exception as e:
                self.text_editor.setPlainText(self.tr(f"Could not decode file to text: {e}"))
                self.stacked_widget.setCurrentIndex(0)
                return

        if 'json' in mime_type:
            try:
                data = json.loads(decoded_content)
                # Attempt to display as table if it's a list of dicts or a single dict
                if isinstance(data, list) and all(isinstance(item, dict) for item in data):
                    self.stacked_widget.setCurrentIndex(1) # Show table
                    self._populate_table_from_list_of_dicts(data)
                    if is_large and len(data) > self.max_structured_preview_lines:
                        # For large JSON lists, display a message in the text editor (index 0)
                        # and still show the truncated table (index 1).
                        # This means we might need to show both, or prioritize the table.
                        # For now, let's prioritize the table and just print a message.
                        pass
                elif isinstance(data, dict):
                    self.stacked_widget.setCurrentIndex(1) # Show table
                    self._populate_table_from_single_dict(data)
                else:
                    # Fallback to text for other JSON types (e.g., list of primitives, string, number)
                    self.stacked_widget.setCurrentIndex(0)
                    pretty_json = json.dumps(data, indent=4, ensure_ascii=False)
                    if is_large:
                        lines = pretty_json.splitlines()
                        self.text_editor.setPlainText(self.tr(f"File too large for full structured display. Showing first {self.max_structured_preview_lines} lines.\n\n--- Preview Mode ---\n") + "\n".join(lines[:self.max_structured_preview_lines]))
                    else:
                        self.text_editor.setPlainText(pretty_json)
            except json.JSONDecodeError as e:
                self.stacked_widget.setCurrentIndex(0)
                self.text_editor.setPlainText(self.tr(f"Invalid JSON: {e}\n\nRaw content:\n{decoded_content[:1000]}..."))
            except Exception as e:
                self.stacked_widget.setCurrentIndex(0)
                self.text_editor.setPlainText(self.tr(f"Error processing JSON: {e}\n\nRaw content:\n{decoded_content[:1000]}..."))
        elif 'xml' in mime_type:
            self.stacked_widget.setCurrentIndex(0)
            try:
                root = ET.fromstring(decoded_content)
                # Use ET.indent for pretty printing if available (Python 3.9+)
                # Otherwise, just use tostring without pretty_print
                if hasattr(ET, 'indent'):
                    ET.indent(root, space="  ", level=0)
                    pretty_xml = ET.tostring(root, encoding='unicode')
                else:
                    pretty_xml = ET.tostring(root, encoding='unicode') # Removed pretty_print
                
                if is_large:
                    lines = pretty_xml.splitlines()
                    self.text_editor.setPlainText(self.tr(f"File too large for full structured display. Showing first {self.max_structured_preview_lines} lines.\n\n--- Preview Mode ---\n") + "\n".join(lines[:self.max_structured_preview_lines]))
                else:
                    self.text_editor.setPlainText(pretty_xml)
            except ET.ParseError as e:
                self.text_editor.setPlainText(self.tr(f"Invalid XML: {e}\n\nRaw content:\n{decoded_content[:1000]}..."))
            except Exception as e:
                error_details = traceback.format_exc()
                self.text_editor.setPlainText(self.tr(f"Error processing XML: {e}\nDetails:\n{error_details}\n\nRaw content:\n{decoded_content[:1000]}..."))
        elif 'csv' in mime_type or (mime_type == 'text/plain' and any(c in decoded_content[:1024] for c in [',', '\t', ';'])): # Heuristic for plain text that might be CSV
            try:
                f = io.StringIO(decoded_content)
                
                # Attempt to sniff dialect
                dialect = csv.excel # Default dialect
                try:
                    # Sniff up to a certain size, or the whole content if small
                    sniff_content = decoded_content[:1024] if len(decoded_content) > 1024 else decoded_content
                    if sniff_content: # Only sniff if there's content
                        dialect = csv.Sniffer().sniff(sniff_content)
                except csv.Error as e:
                    pass 

                reader = csv.reader(f, dialect)
                
                header = []
                data = []
                
                # Read the first row
                first_row = next(reader, None)
                if first_row:
                    # Check if the first row is likely a header using sniffer's has_header
                    # If has_header fails (e.g., on very short content), treat it as data.
                    try:
                        # This is a simple heuristic: if it's not just numbers and has some text, assume header
                        is_likely_header = False
                        if any(isinstance(item, str) and not item.strip().replace('.', '', 1).isdigit() for item in first_row):
                            is_likely_header = True
                        
                        if is_likely_header and len(decoded_content.splitlines()) > 1: # Also check if there's more than one line
                            header = first_row
                        else:
                            data.append(first_row)
                    except csv.Error:
                        # If has_header itself fails, assume no header and treat as data
                        data.append(first_row)
                
                # Read remaining data
                for row in reader:
                    data.append(row)

                # Determine the maximum number of columns needed
                max_cols = len(header) if header else 0
                for row in data:
                    max_cols = max(max_cols, len(row))

                self.table_widget.setColumnCount(max_cols)
                
                if header:
                    self.table_widget.setHorizontalHeaderLabels(header)
                else:
                    self.table_widget.setHorizontalHeaderLabels([self.tr(f"Column {i+1}") for i in range(max_cols)])

                # Handle large file preview for CSV
                if is_large and len(data) > self.max_structured_preview_lines:
                    self.text_editor.setPlainText(self.tr(f"File too large for full structured display. Showing first {self.max_structured_preview_lines} rows.\n\n--- Preview Mode ---\n"))
                    self.stacked_widget.setCurrentIndex(0) # Show text editor for the message
                    data = data[:self.max_structured_preview_lines] # Truncate data for display
                    # Then fall through to display the truncated table
                    self.stacked_widget.setCurrentIndex(1) # Switch back to table view after setting message
                else:
                    self.stacked_widget.setCurrentIndex(1) # Show table widget

                self.table_widget.setRowCount(len(data))
                for r_idx, row_data_item in enumerate(data):
                    for c_idx in range(max_cols): # Iterate up to max_cols
                        cell_value = row_data_item[c_idx] if c_idx < len(row_data_item) else ""
                        self.table_widget.setItem(r_idx, c_idx, QTableWidgetItem(str(cell_value)))
                
                self.table_widget.resizeColumnsToContents()
                self.table_widget.horizontalHeader().setStretchLastSection(True)

            except Exception as e: # Catch broader exceptions for debugging
                error_details = traceback.format_exc()
                self.text_editor.setPlainText(self.tr(f"Could not parse as CSV. Trying to display as plain text.\nError: {e}\nDetails:\n{error_details}\n\nRaw content:\n{decoded_content[:1000]}..."))
                self.stacked_widget.setCurrentIndex(0) # Show text editor
        else:
            # Default to text editor for unsupported or plain text
            self.stacked_widget.setCurrentIndex(0)
            self.text_editor.setPlainText(self.tr("Unsupported structured format or not detected. Displaying raw text.\n\n") + decoded_content)
        self.text_editor.verticalScrollBar().setValue(0) # Reset scroll for text editor
        # No direct scrollbar for table_widget, it manages its own.

    def _populate_table_from_list_of_dicts(self, data_list):
        """Populates the internal table_widget from a list of dictionaries (JSON array of objects)."""
        if not data_list:
            return

        # Collect all unique keys to form columns
        all_keys = set()
        for item in data_list:
            all_keys.update(item.keys())
        
        # Sort keys for consistent column order
        sorted_keys = sorted(list(all_keys))
        
        self.table_widget.setColumnCount(len(sorted_keys))
        self.table_widget.setHorizontalHeaderLabels(sorted_keys)
        self.table_widget.setRowCount(len(data_list))

        for row_idx, row_dict in enumerate(data_list):
            for col_idx, key in enumerate(sorted_keys):
                value = row_dict.get(key, "") # Get value, or empty string if key not present
                self.table_widget.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))
        
        self.table_widget.resizeColumnsToContents()
        self.table_widget.horizontalHeader().setStretchLastSection(True)

    def _populate_table_from_single_dict(self, data_dict):
        """Populates the internal table_widget from a single dictionary (JSON object)."""
        self.table_widget.setColumnCount(2) # Key | Value
        self.table_widget.setHorizontalHeaderLabels([self.tr("Key"), self.tr("Value")])
        self.table_widget.setRowCount(len(data_dict))

        for row_idx, (key, value) in enumerate(data_dict.items()):
            self.table_widget.setItem(row_idx, 0, QTableWidgetItem(str(key)))
            self.table_widget.setItem(row_idx, 1, QTableWidgetItem(str(value)))
        
        self.table_widget.resizeColumnsToContents()
        self.table_widget.horizontalHeader().setStretchLastSection(True)


class ImageMetadataTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout.addWidget(self.image_label)

        self.metadata_text_edit = QTextEdit()
        self.metadata_text_edit.setReadOnly(True)
        self.metadata_text_edit.setFont(QFont("Monospace", 9))
        self.metadata_text_edit.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layout.addWidget(self.metadata_text_edit)

    def update_image_data(self, filepath, metadata):
        self.image_label.clear()
        self.metadata_text_edit.clear()

        if not PIL_AVAILABLE:
            self.metadata_text_edit.setPlainText(self.tr("Pillow library not found. Image metadata display is disabled."))
            return

        if 'image_metadata_error' in metadata:
            self.metadata_text_edit.setPlainText(self.tr(f"Error loading image metadata: {metadata['image_metadata_error']}"))
            return

        try:
            pixmap = QPixmap(filepath)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.image_label.setPixmap(scaled_pixmap)
            else:
                self.image_label.setText(self.tr("Could not load image preview."))
        except Exception as e:
            self.image_label.setText(self.tr(f"Error loading image preview: {e}"))

        meta_str = []
        meta_str.append(self.tr(f"Format: {metadata.get('image_format', 'N/A')}"))
        meta_str.append(self.tr(f"Dimensions: {metadata.get('image_dimensions', 'N/A')}"))
        meta_str.append(self.tr(f"Color Mode: {metadata.get('image_mode', 'N/A')}"))

        if 'exif_data' in metadata and metadata['exif_data']:
            meta_str.append("\n--- EXIF Data ---")
            for key, value in metadata['exif_data'].items():
                meta_str.append(f"{key}: {value}")

        if 'gps_data' in metadata and metadata['gps_data']:
            meta_str.append("\n--- GPS Data ---")
            for key, value in metadata['gps_data'].items():
                meta_str.append(f"{key}: {value}")

        self.metadata_text_edit.setPlainText("\n".join(meta_str))
        self.metadata_text_edit.verticalScrollBar().setValue(0)

class Base64View(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.encode_button = QPushButton(self.tr("Encode File to Base64"))
        self.encode_button.clicked.connect(self._encode_file)
        self.layout.addWidget(self.encode_button)

        self.base64_text_edit = QTextEdit()
        self.base64_text_edit.setReadOnly(True)
        self.base64_text_edit.setFont(QFont("Monospace", 9))
        self.base64_text_edit.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layout.addWidget(self.base64_text_edit)

        self.file_content = b""

    def set_file_content(self, raw_bytes):
        self.file_content = raw_bytes
        self.base64_text_edit.clear()

    def _encode_file(self):
        if not self.file_content:
            self.base64_text_edit.setPlainText(self.tr("No file loaded to encode."))
            return
        try:
            encoded_data = base64.b64encode(self.file_content).decode('utf-8')
            self.base64_text_edit.setPlainText(encoded_data)
        except Exception as e:
            self.base64_text_edit.setPlainText(self.tr(f"Error encoding to Base64: {e}"))
        self.base64_text_edit.verticalScrollBar().setValue(0)

class EntropyTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.entropy_label = QLabel(self.tr("Shannon Entropy: N/A"))
        self.entropy_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.entropy_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.entropy_label)
        self.layout.addStretch(1)

    def update_entropy(self, entropy_value):
        if isinstance(entropy_value, (float, int)):
            self.entropy_label.setText(self.tr(f"Shannon Entropy: {entropy_value:.4f} bits/byte"))
        else:
            self.entropy_label.setText(self.tr(f"Shannon Entropy: {entropy_value}"))

class ByteHistogram(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        if MATPLOTLIB_AVAILABLE:
            self.figure = Figure()
            self.canvas = FigureCanvas(self.figure)
            self.layout.addWidget(self.canvas)
            self.ax = self.figure.add_subplot(111)
            self.ax.set_title(self.tr("Byte Frequency Histogram"))
            self.ax.set_xlabel(self.tr("Byte Value (0-255)"))
            self.ax.set_ylabel(self.tr("Frequency"))
            self.ax.set_xticks(range(0, 256, 16))
            self.ax.set_xlim(-1, 256)
        else:
            self.layout.addWidget(QLabel(self.tr("Matplotlib not found. Byte Histogram feature is disabled.")))

    def plot_histogram(self, file_content):
        if not MATPLOTLIB_AVAILABLE:
            return

        self.ax.clear()
        self.ax.set_title(self.tr("Byte Frequency Histogram"))
        self.ax.set_xlabel(self.tr("Byte Value (0-255)"))
        self.ax.set_ylabel(self.tr("Frequency"))
        self.ax.set_xticks(range(0, 256, 16))
        self.ax.set_xlim(-1, 256)

        if not file_content:
            self.ax.text(0.5, 0.5, self.tr("No data to plot."),
                         horizontalalignment='center', verticalalignment='center',
                         transform=self.ax.transAxes, fontsize=14, color='gray')
            self.canvas.draw()
            return

        byte_counts = [0] * 256
        for byte in file_content:
            byte_counts[byte] += 1

        self.ax.bar(range(256), byte_counts, width=1.0, color='skyblue', edgecolor='blue')
        self.canvas.draw()

class PluginHistoryTab(QWidget):
    """Displays a log of plugin loading, execution, and deletion events."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.history_text_edit = QTextEdit()
        self.history_text_edit.setReadOnly(True)
        self.history_text_edit.setFont(QFont("Monospace", 9))
        self.layout.addWidget(self.history_text_edit)
        self.history_text_edit.setPlainText(self.tr("Plugin history will appear here."))

    def add_log_entry(self, entry):
        """Adds a new log entry to the history."""
        self.history_text_edit.append(entry)
        self.history_text_edit.verticalScrollBar().setValue(self.history_text_edit.verticalScrollBar().maximum())
        
    def clear_history(self):
        """Clears the displayed history."""
        self.history_text_edit.clear()
        self.history_text_edit.setPlainText(self.tr("Plugin history will appear here."))


class PluginManager(QObject):
    """Manages loading, unloading, and execution of plugins, including history persistence."""
    plugin_loaded_signal = Signal(str) # Emits plugin name on successful load
    plugin_failed_signal = Signal(str, str) # Emits plugin name and error on failure
    plugin_deleted_signal = Signal(str) # Emits plugin name on deletion
    plugin_reloaded_signal = Signal() # Emits when plugins are reloaded (all or specific)
    reanalyze_requested = Signal() # New signal: Request main window to re-analyze current file

    def __init__(self, max_plugin_history_entries, parent=None):
        super().__init__(parent)
        # Stores {plugin_name: {'module': module_obj, 'function': func_obj, 'type': plugin_type, 'description': desc, 'json_path': path, 'plugin_py_path': path, 'tab_title': title}}
        self.loaded_plugins = {}
        self.plugin_history_tab = None # Reference to the UI tab for logging
        self.history_entries = [] # In-memory list of history entries
        self.max_plugin_history_entries = max_plugin_history_entries # Set from settings

        # Ensure plugin directories exist
        os.makedirs(PLUGIN_DIRECTORY, exist_ok=True)
        self._load_history() # Load history from file into self.history_entries
        self._load_plugins_from_disk_and_config() # Load plugins by scanning disk and updating config

    def set_plugin_history_tab(self, tab):
        self.plugin_history_tab = tab
        # DO NOT call _update_history_display here to keep the tab blank on startup
        # New entries will be added via _log()

    def update_settings(self, new_max_history_entries):
        """Updates the maximum history entries setting."""
        self.max_plugin_history_entries = new_max_history_entries
        # Trim history if new limit is smaller
        if len(self.history_entries) > self.max_plugin_history_entries:
            self.history_entries = self.history_entries[-self.max_plugin_history_entries:]
            if self.plugin_history_tab:
                self._update_history_display() # Force re-display to reflect trimming

    def _log(self, message):
        """Logs messages to the in-memory history and updates the UI."""
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        full_message = f"[{timestamp}] {message}"
        self.history_entries.append(full_message)
        # Trim history to MAX_PLUGIN_HISTORY_ENTRIES
        if len(self.history_entries) > self.max_plugin_history_entries:
            self.history_entries = self.history_entries[-self.max_plugin_history_entries:]
        
        # Safely update UI only if the widget still exists and is not destroyed
        if self.plugin_history_tab and self.plugin_history_tab.history_text_edit:
            # Check if the underlying C++ object is still valid
            # A common way is to check if it still has a parent.
            # If the parent is None, the widget has likely been deleted.
            if not self.plugin_history_tab.history_text_edit.parent() is None:
                try:
                    self.plugin_history_tab.history_text_edit.append(full_message)
                    self.plugin_history_tab.history_text_edit.verticalScrollBar().setValue(
                        self.plugin_history_tab.history_text_edit.verticalScrollBar().maximum()
                    )
                except RuntimeError:
                    # Catch the specific RuntimeError if the object was just destroyed between checks
                    # print(f"Warning: Attempted to log to a destroyed QTextEdit: {full_message}")
                    pass # Do nothing if the widget is already deleted

    def _update_history_display(self):
        """Refreshes the history display in the UI tab.
        This method is now primarily for internal use if we want to force a full re-display,
        but it's not called on startup to meet the user's requirement.
        """
        if self.plugin_history_tab:
            self.plugin_history_tab.clear_history()
            for entry in self.history_entries:
                self.plugin_history_tab.add_log_entry(entry)

    def _load_history(self):
        """Loads plugin history from a JSON file into in-memory list."""
        if os.path.exists(PLUGIN_HISTORY_FILE):
            try:
                with open(PLUGIN_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    self.history_entries = json.load(f)
                self._log(self.tr("Loaded plugin history from file."))
            except json.JSONDecodeError as e:
                self._log(self.tr(f"Error reading plugin history file (JSON error): {e}"))
                self.history_entries = [] # Reset on error
            except Exception as e:
                self._log(self.tr(f"Error loading plugin history: {e}"))
                self.history_entries = [] # Reset on error
        else:
            self._log(self.tr("No plugin history file found."))

    def _save_history(self):
        """Saves current plugin history to a JSON file."""
        try:
            with open(PLUGIN_HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.history_entries, f, indent=4, ensure_ascii=False)
            self._log(self.tr("Plugin history saved."))
        except Exception as e:
            self._log(self.tr(f"Error saving plugin history: {e}"))

    def _save_plugin_config(self):
        """Saves the list of currently loaded plugin names to a config file."""
        try:
            with open(PLUGIN_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(list(self.loaded_plugins.keys()), f, indent=4)
            self._log(self.tr("Plugin configuration saved."))
        except Exception as e:
            self._log(self.tr(f"Error saving plugin configuration: {e}"))

    def _load_plugins_from_disk_and_config(self):
        """
        Scans the plugin directory for .infoscava files, ensures corresponding .py files
        are up-to-date, and then loads/reloads plugins. Updates the config file.
        """
        self._log(self.tr("Scanning plugin directory for .infoscava files..."))
        self.loaded_plugins = {} # Reset loaded plugins to rebuild from disk
        
        found_plugins_on_disk = []
        for filename in os.listdir(PLUGIN_DIRECTORY):
            if filename.endswith(".infoscava"):
                plugin_name = os.path.splitext(filename)[0]
                plugin_json_path = os.path.join(PLUGIN_DIRECTORY, filename)
                plugin_py_path = os.path.join(PLUGIN_DIRECTORY, f"{plugin_name}.py")

                try:
                    with open(plugin_json_path, 'r', encoding='utf-8') as f:
                        plugin_data_from_json = json.load(f)
                    
                    b64_python_code = plugin_data_from_json.get('python_code')
                    if not b64_python_code:
                        self._log(self.tr(f"Skipping '{filename}': Missing 'python_code' in .infoscava file."))
                        continue

                    # Check if .py needs to be written/updated
                    write_py_file = False
                    if not os.path.exists(plugin_py_path):
                        write_py_file = True
                        self._log(self.tr(f"Python file for '{plugin_name}' not found. Will create."))
                    elif os.path.getmtime(plugin_json_path) > os.path.getmtime(plugin_py_path):
                        write_py_file = True
                        self._log(self.tr(f"'{filename}' is newer than '{os.path.basename(plugin_py_path)}'. Will update Python file."))

                    if write_py_file:
                        try:
                            decoded_code = base64.b64decode(b64_python_code).decode('utf-8')
                            with open(plugin_py_path, 'w', encoding='utf-8') as f_py:
                                f_py.write(decoded_code)
                            self._log(self.tr(f"Updated plugin Python code for: {plugin_name} at {plugin_py_path}"))
                        except Exception as e:
                            self._log(self.tr(f"Error decoding/writing Python code for '{plugin_name}': {e}"))
                            continue # Skip this plugin if .py can't be prepared

                    # Now attempt to load the plugin from the .py file
                    if self._perform_dynamic_import_and_register(plugin_name, plugin_py_path, plugin_data_from_json):
                        found_plugins_on_disk.append(plugin_name)
                    else:
                        self._log(self.tr(f"Failed to load plugin '{plugin_name}' from disk. Check history."))

                except json.JSONDecodeError as e:
                    self._log(self.tr(f"Error parsing .infoscava file '{filename}' (JSON error): {e}"))
                except Exception as e:
                    error_details = traceback.format_exc()
                    self._log(self.tr(f"Unexpected error processing '{filename}': {e}\nDetails:\n{error_details}"))
        
        # After scanning all, update the config file to reflect what's actually loaded
        self._save_plugin_config()
        self.plugin_reloaded_signal.emit() # Notify UI that plugins have been reloaded
        self._log(self.tr("Finished scanning and loading plugins from disk."))


    def _perform_dynamic_import_and_register(self, name, plugin_py_path, plugin_data_from_json):
        """
        Performs the dynamic import of a plugin's .py file and registers it.
        Assumes the .py file is already correctly written/updated on disk.
        """
        function_name = plugin_data_from_json.get('function_name')
        plugin_type = plugin_data_from_json.get('type', 'analysis_plugin')
        description = plugin_data_from_json.get('description', 'No description provided.')
        tab_title = plugin_data_from_json.get('tab_title', name)

        if not all([name, function_name]):
            self._log(self.tr(f"Skipping plugin '{name}': Missing 'name' or 'function_name' in JSON data."))
            self.plugin_failed_signal.emit(name, self.tr("Missing name or function_name in plugin JSON."))
            return False

        # Use a unique module name for importlib to avoid conflicts
        module_name = f"infoscava_plugin_{hashlib.md5(name.encode()).hexdigest()}"
        
        try:
            # Explicitly remove from sys.modules to force a fresh import
            if module_name in sys.modules:
                self._log(self.tr(f"Removing existing module '{module_name}' from sys.modules before fresh import."))
                del sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, plugin_py_path)
            if spec is None:
                error_msg = self.tr(f"Could not create module spec for '{plugin_py_path}'.")
                self._log(error_msg)
                self.plugin_failed_signal.emit(name, error_msg)
                return False
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module # Add to sys.modules for proper import handling
            spec.loader.exec_module(module) # Execute the module

            func = getattr(module, function_name, None)
            if func is None or not callable(func):
                error_msg = self.tr(f"Function '{function_name}' not found or not callable in module '{plugin_py_path}'.")
                self._log(error_msg)
                self.plugin_failed_signal.emit(name, error_msg)
                return False

            self.loaded_plugins[name] = {
                'module': module,
                'function': func,
                'type': plugin_type,
                'description': description,
                'json_path': os.path.join(PLUGIN_DIRECTORY, f"{name}.infoscava"), # Ensure correct json_path
                'plugin_py_path': plugin_py_path,
                'tab_title': tab_title
            }
            self._log(self.tr(f"Successfully loaded plugin: {name} (Type: {plugin_type}) from {os.path.basename(plugin_py_path)}."))
            self.plugin_loaded_signal.emit(name)
            return True

        except Exception as e:
            error_details = traceback.format_exc()
            error_msg = self.tr(f"Error during dynamic import/registration of plugin '{name}' from '{plugin_py_path}'. {e}\nDetails:\n{error_details}")
            self._log(error_msg)
            self.plugin_failed_signal.emit(name, error_msg)
            return False


    def load_new_plugin_file(self, source_filepath):
        """Copies a new .infoscava file and attempts to load it."""
        if not os.path.exists(source_filepath):
            self._log(self.tr(f"Error: Source plugin file not found at {source_filepath}."))
            QMessageBox.critical(None, self.tr("Plugin Load Error"), self.tr(f"Source plugin file not found: {source_filepath}"))
            return False

        dest_filename = os.path.basename(source_filepath)
        dest_filepath_json = os.path.join(PLUGIN_DIRECTORY, dest_filename)
        plugin_name = os.path.splitext(dest_filename)[0]
        dest_filepath_py = os.path.join(PLUGIN_DIRECTORY, f"{plugin_name}.py")

        if os.path.exists(dest_filepath_json):
            reply = QMessageBox.question(None, self.tr("Plugin Already Exists"),
                                         self.tr(f"A plugin with the name '{plugin_name}' already exists. Overwrite?"),
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                self._log(self.tr(f"Plugin load cancelled: '{plugin_name}' already exists and overwrite declined."))
                return False

        try:
            # Copy the .infoscava file
            shutil.copy(source_filepath, dest_filepath_json)
            self._log(self.tr(f"Copied plugin definition file from {source_filepath} to: {dest_filepath_json}"))

            # Read the copied .infoscava to get its content for .py generation
            with open(dest_filepath_json, 'r', encoding='utf-8') as f:
                plugin_data_from_json = json.load(f)
            b64_python_code = plugin_data_from_json.get('python_code')

            if not b64_python_code:
                error_msg = self.tr(f"Malformed plugin '{plugin_name}': Missing 'python_code'.")
                self._log(error_msg)
                QMessageBox.critical(None, self.tr("Plugin Load Error"), error_msg)
                # Clean up copied .infoscava
                os.remove(dest_filepath_json)
                self._log(self.tr(f"Removed malformed copied .infoscava file: {dest_filepath_json}"))
                return False

            # Decode and write the .py file
            decoded_code = base64.b64decode(b64_python_code).decode('utf-8')
            with open(dest_filepath_py, 'w', encoding='utf-8') as f_py:
                f_py.write(decoded_code)
            self._log(self.tr(f"Saved plugin Python code to: {dest_filepath_py}"))

            # Now perform dynamic import and register
            if self._perform_dynamic_import_and_register(plugin_name, dest_filepath_py, plugin_data_from_json):
                self._save_plugin_config() # Save updated config
                self.plugin_reloaded_signal.emit() # Notify UI to refresh plugin list
                self.reanalyze_requested.emit() # Request re-analysis after new plugin loaded
                QMessageBox.information(None, self.tr("Plugin Loaded"), self.tr(f"Plugin '{plugin_name}' successfully loaded."))
                return True
            else:
                self._log(self.tr(f"Failed to load copied plugin '{plugin_name}'. Check Plugin History tab for details."))
                # Clean up both .infoscava and .py if dynamic import failed
                if os.path.exists(dest_filepath_json):
                    os.remove(dest_filepath_json)
                    self._log(self.tr(f"Removed problematic copied .infoscava file: {dest_filepath_json}"))
                if os.path.exists(dest_filepath_py):
                    os.remove(dest_filepath_py)
                    self._log(self.tr(f"Removed problematic plugin Python file: {dest_filepath_py}"))
                QMessageBox.warning(None, self.tr("Plugin Load Failed"), self.tr(f"Failed to load plugin '{plugin_name}'. See Plugin History for details."))
                return False
        except json.JSONDecodeError as e:
            error_msg = self.tr(f"Error parsing plugin JSON '{dest_filename}' (JSON error): {e}")
            self._log(error_msg)
            QMessageBox.critical(None, self.tr("Plugin Load Error"), error_msg)
            # Clean up copied .infoscava if JSON is bad
            if os.path.exists(dest_filepath_json):
                os.remove(dest_filepath_json)
                self._log(self.tr(f"Removed malformed copied .infoscava file: {dest_filepath_json}"))
            return False
        except Exception as e:
            error_details = traceback.format_exc()
            error_msg = self.tr(f"An unexpected error occurred while copying or loading the plugin '{plugin_name}': {e}\nDetails:\n{error_details}")
            self._log(error_msg)
            QMessageBox.critical(None, self.tr("Error Loading Plugin"), error_msg)
            # Attempt to clean up both files if error occurred before successful registration
            if os.path.exists(dest_filepath_json):
                os.remove(dest_filepath_json)
            if os.path.exists(dest_filepath_py):
                os.remove(dest_filepath_py)
            return False

    def get_plugins_metadata(self):
        """Returns a list of currently loaded plugins with their metadata."""
        return [
            {'name': name, 'description': data['description'], 'type': data['type']}
            for name, data in self.loaded_plugins.items()
        ]

    def execute_analysis_plugins(self, filepath, file_content_bytes):
        """Executes all active analysis plugins and returns their results."""
        plugin_results = {}
        for name, data in list(self.loaded_plugins.items()): # Iterate over a copy
            if data['type'] == 'analysis_plugin':
                try:
                    self._log(self.tr(f"Executing analysis plugin: {name} for file '{os.path.basename(filepath)}'..."))
                    result = data['function'](filepath, file_content_bytes)
                    plugin_results[name] = result
                    self._log(self.tr(f"Plugin '{name}' executed successfully for '{os.path.basename(filepath)}'."))
                except Exception as e:
                    error_details = traceback.format_exc()
                    error_msg = self.tr(f"Error executing analysis plugin '{name}' for file '{os.path.basename(filepath)}': {e}\nDetails:\n{error_details}")
                    self._log(error_msg)
                    plugin_results[name] = error_msg
            # Static HTML plugins are handled at initial load, not during file analysis
        return plugin_results

    def delete_plugin(self, plugin_name):
        """Deletes a plugin's .infoscava and its permanent .py files."""
        if plugin_name not in self.loaded_plugins:
            self._log(self.tr(f"Plugin '{plugin_name}' not found for deletion."))
            return False

        plugin_data = self.loaded_plugins[plugin_name]
        json_path = plugin_data['json_path']
        plugin_py_path = plugin_data['plugin_py_path']

        try:
            # Remove from sys.modules to allow potential re-import if needed later
            module_name_hash = f"infoscava_plugin_{hashlib.md5(plugin_name.encode()).hexdigest()}"
            if module_name_hash in sys.modules:
                del sys.modules[module_name_hash]
                self._log(self.tr(f"Unloaded module '{module_name_hash}' from sys.modules."))

            if os.path.exists(json_path):
                os.remove(json_path)
                self._log(self.tr(f"Deleted plugin definition file: {json_path}"))
            
            if os.path.exists(plugin_py_path):
                os.remove(plugin_py_path)
                self._log(self.tr(f"Deleted permanent plugin Python file: {plugin_py_path}"))

            del self.loaded_plugins[plugin_name]
            self._save_plugin_config() # Update config after deletion
            self._log(self.tr(f"Plugin '{plugin_name}' successfully deleted."))
            self.plugin_deleted_signal.emit(plugin_name)
            self.reanalyze_requested.emit() # Request re-analysis after plugin deleted
            return True
        except Exception as e:
            error_msg = self.tr(f"Error deleting plugin '{plugin_name}': {e}")
            self._log(error_msg)
            QMessageBox.critical(None, self.tr("Plugin Deletion Error"), error_msg)
            return False

    def reload_plugin(self, plugin_name):
        """Reloads a specific plugin by re-reading its .infoscava file."""
        if plugin_name not in self.loaded_plugins:
            self._log(self.tr(f"Plugin '{plugin_name}' not found for reloading."))
            QMessageBox.warning(None, self.tr("Reload Error"), self.tr(f"Plugin '{plugin_name}' is not currently loaded or its definition file is missing."))
            return False

        plugin_data = self.loaded_plugins[plugin_name]
        json_path = plugin_data['json_path']

        self._log(self.tr(f"Attempting to reload plugin: {plugin_name}..."))
        
        # This will trigger the full logic in _load_plugins_from_disk_and_config
        # to re-read the .infoscava, update .py if necessary, and re-import.
        # We only need to load this specific plugin, not all.
        # So, we call _load_single_plugin directly after ensuring .py is current.
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                plugin_data_from_json = json.load(f)
            b64_python_code = plugin_data_from_json.get('python_code')
            
            plugin_py_path = plugin_data['plugin_py_path'] # Get path from loaded_plugins

            # Always re-write .py on explicit reload to ensure latest code is used
            decoded_code = base64.b64decode(b64_python_code).decode('utf-8')
            with open(plugin_py_path, 'w', encoding='utf-8') as f_py:
                f_py.write(decoded_code)
            self._log(self.tr(f"Rewrote plugin Python code for '{plugin_name}' during reload."))

            if self._perform_dynamic_import_and_register(plugin_name, plugin_py_path, plugin_data_from_json):
                self._log(self.tr(f"Plugin '{plugin_name}' reloaded successfully."))
                self._save_plugin_config() # Update config after successful reload
                self.plugin_reloaded_signal.emit() # Notify UI
                self.reanalyze_requested.emit() # Request re-analysis after plugin reloaded
                return True
            else:
                self._log(self.tr(f"Failed to reload plugin '{plugin_name}'. Check Plugin History tab for details."))
                # If reload failed, remove it from loaded_plugins to indicate its broken state
                if plugin_name in self.loaded_plugins:
                    del self.loaded_plugins[plugin_name]
                    self._save_plugin_config()
                self.plugin_reloaded_signal.emit() # Notify UI of potential removal
                self.reanalyze_requested.emit() # Request re-analysis if plugin failed to reload
                return False
        except Exception as e:
            error_details = traceback.format_exc()
            error_msg = self.tr(f"Error during reload of plugin '{plugin_name}': {e}\nDetails:\n{error_details}")
            self._log(error_msg)
            QMessageBox.critical(None, self.tr("Plugin Reload Error"), error_msg)
            return False

    def reload_all_plugins(self):
        """Reloads all plugins by rescanning the plugin directory and config."""
        self._log(self.tr("Initiating full plugin reload..."))
        self._load_plugins_from_disk_and_config() # This will re-read disk and load everything
        self._log(self.tr("All plugins reloaded."))
        self.plugin_reloaded_signal.emit() # Notify UI
        self.reanalyze_requested.emit() # Request re-analysis after all plugins reloaded

    # Removed __del__ as it's problematic for Qt widget cleanup order.
    # The closeEvent in InfoscavaMainWindow handles saving history.


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Infoscava Help"))
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        help_text = self.tr("""
        <h3>Infoscava - Universal File Analyzer</h3>
        <p><b>Developer:</b> Muhammed Shafin P (GitHub: hejhdiss)</p>
        <p>This application helps you excavate information from any file type.</p>

        <h4>Usage:</h4>
        <ul>
            <li><b>Browse File:</b> Click "Browse File" or drag and drop a file onto the application window.</li>
            <li><b>CLI:</b> Run from command line: <code>python infoscava.py --file &lt;path&gt;</code></li>
            <li><b>Clear All:</b> Use the "Clear All" button to reset the application.</li>
        </ul>

        <h4>Tabs:</h4>
        <ul>
            <li><b>Metadata:</b> Basic file info, hashes, encoding detection, entropy.</li>
            <li><b>Text:</b> View text content, change encoding.</li>
            <li><b>Search:</b> Search text content with multi-threading and highlight results.</li>
            <li><b>Hex:</b> Raw hexadecimal and ASCII dump.</li>
            <li><b>Structured:</b> Pretty-prints JSON.</li>
            <li><b>Image Metadata:</b> (If image) EXIF and GPS data.</li>
            <li><b>Base64 View:</b> Encodes file content to Base64.</li>
            <li><b>Entropy:</b> Displays Shannon entropy.</li>
            <li><b>Byte Histogram:</b> Visualizes byte frequency.</li>
            <li><b>Plugin History:</b> Logs plugin loading, execution, and deletion events.</li>
            <li><b>Dynamic Plugin Tabs:</b> Plugins can add their own tabs for custom output (e.g., HTML reports).</li>
        </ul>

        <h4>Keyboard Shortcuts:</h4>
        <ul>
            <li><b>Ctrl+O:</b> Open File</li>
            <li><b>Ctrl+R:</b> Reload Current File</li>
            <li><b><b>Ctrl+E:</b> Export Analysis</b></li>
            <li><b>Ctrl+H:</b> Show Help</li>
            <li><b>Ctrl+T:</b> Toggle Theme</li>
            <li><b>Ctrl+W:</b> Close Tab</li>
        </ul>

        <h4>Plugin System:</h4>
        <p>Infoscava supports dynamic plugins defined by <code>.infoscava</code> files. These files contain plugin metadata and Base64-encoded Python code. Plugins can perform custom analysis or generate HTML reports.</p>
        <ul>
            <li>Plugins are loaded from the <code>plugins/</code> directory relative to the application.</li>
            <li>Use the "Plugins" menu to access the "Manage Plugins" dialog for loading, reloading, and deleting plugins.</li>
        </ul>

        <h4>File Watcher:</h4>
        <p>The application automatically reloads the file if it detects changes on disk.</p>
        """)
        self.text_browser = QTextBrowser() # Changed from QTextEdit to QTextBrowser
        self.text_browser.setHtml(help_text)
        self.text_browser.setReadOnly(True)
        self.text_browser.setOpenExternalLinks(True)
        self.layout.addWidget(self.text_browser) # Corrected line

        ok_button = QPushButton(self.tr("OK"))
        ok_button.clicked.connect(self.accept)
        self.layout.addWidget(ok_button)

class SettingsManager(QObject):
    """Manages loading and saving application settings."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = self._load_settings()

    def _load_settings(self):
        """Loads settings from file or returns defaults."""
        if os.path.exists(APP_SETTINGS_FILE):
            try:
                with open(APP_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                # Validate loaded settings and apply defaults for missing keys
                for key, default_value in DEFAULT_APP_SETTINGS.items():
                    # Ensure key exists, is numeric, and for positive-only settings, check if > 0
                    if key not in loaded_settings or not isinstance(loaded_settings[key], (int, float)):
                        loaded_settings[key] = default_value
                    elif key in ['MAX_TEXT_PREVIEW_LINES', 'MAX_HEX_PREVIEW_BYTES', 'MAX_STRUCTURED_PREVIEW_LINES', 'MAX_PLUGIN_HISTORY_ENTRIES'] and loaded_settings[key] <= 0:
                        loaded_settings[key] = default_value
                return loaded_settings
            except (json.JSONDecodeError, FileNotFoundError, Exception) as e:
                # print(f"Error loading settings: {e}. Using default settings.")
                return DEFAULT_APP_SETTINGS.copy()
        return DEFAULT_APP_SETTINGS.copy()

    def save_settings(self, settings):
        """Saves current settings to file."""
        try:
            with open(APP_SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
            self.settings = settings.copy() # Update in-memory settings
        except Exception as e:
            # print(f"Error saving settings: {e}")
            pass # Fail silently for now

    def get_settings(self):
        """Returns the current application settings."""
        return self.settings.copy() # Return a copy to prevent external modification

class SettingsDialog(QDialog):
    """Dialog for managing application settings."""
    settings_saved = Signal(dict)

    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Application Settings"))
        self.current_settings = current_settings.copy() # Work on a copy
        self.setMinimumWidth(400)

        self.layout = QVBoxLayout(self)
        self.form_layout = QFormLayout()
        self.layout.addLayout(self.form_layout)

        self.widgets = {} # To store references to input widgets

        # MAX_FILE_SIZE_FOR_FULL_READ
        file_size_layout = QHBoxLayout()
        self.file_size_spinbox = QDoubleSpinBox()
        self.file_size_spinbox.setRange(0.0, 10000.0) # Up to 10000 GB
        self.file_size_spinbox.setDecimals(2)
        self.file_size_spinbox.setSingleStep(0.1)
        self.file_size_unit_combo = QComboBox()
        self.file_size_unit_combo.addItems(["Bytes", "KB", "MB", "GB"])
        file_size_layout.addWidget(self.file_size_spinbox)
        file_size_layout.addWidget(self.file_size_unit_combo)
        self.form_layout.addRow(self.tr("Max File Size for Full Read:"), file_size_layout)
        self.widgets['MAX_FILE_SIZE_FOR_FULL_READ'] = (self.file_size_spinbox, self.file_size_unit_combo)
        self._set_file_size_display(self.current_settings['MAX_FILE_SIZE_FOR_FULL_READ'])

        # Other integer settings
        settings_fields = {
            'MAX_TEXT_PREVIEW_LINES': self.tr("Max Text Preview Lines:"),
            'MAX_HEX_PREVIEW_BYTES': self.tr("Max Hex Preview Bytes:"),
            'MAX_STRUCTURED_PREVIEW_LINES': self.tr("Max Structured Preview Lines:"),
            'MAX_PLUGIN_HISTORY_ENTRIES': self.tr("Max Plugin History Entries:")
        }

        for key, label_text in settings_fields.items():
            spinbox = QSpinBox()
            spinbox.setRange(1, 1000000000) # Ensure positive values, up to 1 billion
            spinbox.setValue(self.current_settings.get(key, DEFAULT_APP_SETTINGS[key]))
            self.form_layout.addRow(label_text, spinbox)
            self.widgets[key] = spinbox

        button_layout = QHBoxLayout()
        save_button = QPushButton(self.tr("Save"))
        save_button.clicked.connect(self._save_settings)
        cancel_button = QPushButton(self.tr("Cancel"))
        cancel_button.clicked.connect(self.reject)
        button_layout.addStretch(1)
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        self.layout.addLayout(button_layout)

    def _set_file_size_display(self, size_bytes):
        """Converts bytes to human-readable and sets spinbox/combo."""
        if size_bytes == 0:
            self.file_size_spinbox.setValue(0)
            self.file_size_unit_combo.setCurrentIndex(0) # Bytes
            return

        units = ["Bytes", "KB", "MB", "GB"]
        unit_multipliers = [1, 1024, 1024**2, 1024**3]

        best_unit_index = 0
        for i, multiplier in enumerate(unit_multipliers):
            if size_bytes >= multiplier:
                best_unit_index = i
            else:
                break
        
        value_in_unit = size_bytes / unit_multipliers[best_unit_index]
        self.file_size_spinbox.setValue(value_in_unit)
        self.file_size_unit_combo.setCurrentIndex(best_unit_index)

    def _get_file_size_from_display(self):
        """Gets file size from spinbox/combo and converts to bytes."""
        value = self.file_size_spinbox.value()
        unit_index = self.file_size_unit_combo.currentIndex()
        unit_multipliers = [1, 1024, 1024**2, 1024**3]
        return int(value * unit_multipliers[unit_index])

    def _save_settings(self):
        new_settings = {}
        try:
            # File size
            new_settings['MAX_FILE_SIZE_FOR_FULL_READ'] = self._get_file_size_from_display()
            if new_settings['MAX_FILE_SIZE_FOR_FULL_READ'] < 0:
                raise ValueError("Max File Size must be non-negative.")

            # Other integer settings
            for key in ['MAX_TEXT_PREVIEW_LINES', 'MAX_HEX_PREVIEW_BYTES', 'MAX_STRUCTURED_PREVIEW_LINES', 'MAX_PLUGIN_HISTORY_ENTRIES']:
                value = self.widgets[key].value()
                if value <= 0:
                    raise ValueError(f"{self.tr(key.replace('_', ' ').title())} must be a positive number.")
                new_settings[key] = value
            
            self.settings_saved.emit(new_settings)
            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, self.tr("Invalid Setting"), self.tr(str(e)))
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error Saving Settings"), self.tr(f"An unexpected error occurred: {e}"))


class ManagePluginsDialog(QDialog):
    """Dialog for managing plugins (load, delete, reload)."""
    def __init__(self, plugin_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manage Plugins"))
        self.plugin_manager = plugin_manager
        self.setMinimumSize(400, 300)

        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.plugin_list_widget = QListWidget()
        self.layout.addWidget(self.plugin_list_widget)

        button_layout = QHBoxLayout()
        self.load_button = QPushButton(self.tr("Load New Plugin..."))
        self.load_button.clicked.connect(self._load_new_plugin_from_dialog)
        button_layout.addWidget(self.load_button)

        self.reload_selected_button = QPushButton(self.tr("Reload Selected"))
        self.reload_selected_button.clicked.connect(self._reload_selected_plugin)
        button_layout.addWidget(self.reload_selected_button)

        self.delete_button = QPushButton(self.tr("Delete Selected"))
        self.delete_button.clicked.connect(self._delete_selected_plugin)
        button_layout.addWidget(self.delete_button)

        self.reload_all_button = QPushButton(self.tr("Reload All Plugins"))
        self.reload_all_button.clicked.connect(self._reload_all_plugins)
        button_layout.addWidget(self.reload_all_button)

        self.layout.addLayout(button_layout)

        self._populate_plugin_list()
        # Connect signals from plugin manager to update this dialog
        self.plugin_manager.plugin_loaded_signal.connect(self._populate_plugin_list)
        self.plugin_manager.plugin_deleted_signal.connect(self._populate_plugin_list)
        self.plugin_manager.plugin_reloaded_signal.connect(self._populate_plugin_list)

    def _populate_plugin_list(self):
        """Populates the list widget with currently loaded plugins."""
        self.plugin_list_widget.clear()
        plugins = self.plugin_manager.get_plugins_metadata()
        if not plugins:
            self.plugin_list_widget.addItem(self.tr("No plugins loaded."))
            self.delete_button.setEnabled(False)
            self.reload_selected_button.setEnabled(False)
            return
        
        self.delete_button.setEnabled(True)
        self.reload_selected_button.setEnabled(True)
        for plugin in plugins:
            item_text = f"{plugin['name']} (Type: {plugin['type']})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, plugin['name']) # Store actual plugin name in UserRole
            self.plugin_list_widget.addItem(item)

    def _load_new_plugin_from_dialog(self):
        """Opens a file dialog to select and load a new .infoscava plugin."""
        try:
            filepath, _ = QFileDialog.getOpenFileName(self, self.tr("Select .infoscava Plugin File"),
                                                      PLUGIN_DIRECTORY, self.tr("Infoscava Plugin Files (*.infoscava)"))
            if filepath:
                self.plugin_manager.load_new_plugin_file(filepath)
                # _populate_plugin_list is already connected via signals, no need to call directly here
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error Opening File Dialog"), self.tr(f"An error occurred while opening the file dialog: {e}"))
            self.plugin_manager._log(self.tr(f"Error opening plugin file dialog: {e}\n{traceback.format_exc()}"))


    def _delete_selected_plugin(self):
        """Deletes the selected plugin from the list and disk."""
        selected_items = self.plugin_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, self.tr("No Plugin Selected"), self.tr("Please select a plugin to delete."))
            return

        reply = QMessageBox.question(self, self.tr("Confirm Deletion"),
                                     self.tr("Are you sure you want to delete the selected plugin? This will remove its files from disk."),
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            for item in selected_items:
                plugin_name = item.data(Qt.UserRole)
                self.plugin_manager.delete_plugin(plugin_name)
                # The _populate_plugin_list will be called by the signal from plugin_manager.delete_plugin

    def _reload_selected_plugin(self):
        """Reloads the selected plugin."""
        selected_items = self.plugin_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, self.tr("No Plugin Selected"), self.tr("Please select a plugin to reload."))
            return
        if len(selected_items) > 1:
            QMessageBox.warning(self, self.tr("Multiple Plugins Selected"), self.tr("Please select only one plugin to reload."))
            return

        plugin_name = selected_items[0].data(Qt.UserRole)
        self.plugin_manager.reload_plugin(plugin_name)
        # The _populate_plugin_list will be called by the signal from plugin_manager.reload_plugin

    def _reload_all_plugins(self):
        """Reloads all plugins managed by the PluginManager."""
        self.plugin_manager.reload_all_plugins()
        # The _populate_plugin_list will be called by the signal from plugin_manager.reload_all_plugins


class JsonTableViewer(QWidget):
    """
    A widget to display JSON data, attempting to render it as a table
    if it's a list of objects or a single object, otherwise falling back to text.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.stacked_widget = QStackedWidget()
        self.layout.addWidget(self.stacked_widget)

        self.table_view = QTableWidget()
        self.table_view.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_view.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_view.setSelectionMode(QTableWidget.SingleSelection)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_view.verticalHeader().setVisible(False)
        self.stacked_widget.addWidget(self.table_view) # Index 0 for table

        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setFont(QFont("Monospace", 10))
        self.text_view.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.stacked_widget.addWidget(self.text_view) # Index 1 for text

    def set_json_content(self, json_data):
        # Corrected: Use self.table_view instead of self.table_widget
        self.table_view.clear()
        self.table_view.setRowCount(0)
        self.table_view.setColumnCount(0)
        self.text_view.clear()

        if isinstance(json_data, list) and all(isinstance(item, dict) for item in json_data):
            # List of objects: display as a proper table
            self.stacked_widget.setCurrentIndex(0)
            self._populate_table_from_list_of_dicts(json_data)
        elif isinstance(json_data, dict):
            # Single object: display as a two-column table (Key | Value)
            self.stacked_widget.setCurrentIndex(0)
            self._populate_table_from_single_dict(json_data)
        else:
            # Other JSON types (list of primitives, string, number, bool, None) or errors: fallback to text
            self.stacked_widget.setCurrentIndex(1)
            try:
                self.text_view.setPlainText(json.dumps(json_data, indent=4, ensure_ascii=False))
            except TypeError: # If json_data is not JSON-serializable
                self.text_view.setPlainText(str(json_data))
        self.text_view.verticalScrollBar().setValue(0) # Reset scroll for text view

    def _populate_table_from_list_of_dicts(self, data_list):
        """Populates the internal table_view from a list of dictionaries (JSON array of objects)."""
        if not data_list:
            return

        # Collect all unique keys to form columns
        all_keys = set()
        for item in data_list:
            all_keys.update(item.keys())
        
        # Sort keys for consistent column order
        sorted_keys = sorted(list(all_keys))
        
        # Corrected: Use self.table_view instead of self.table_widget
        self.table_view.setColumnCount(len(sorted_keys))
        self.table_view.setHorizontalHeaderLabels(sorted_keys)
        self.table_view.setRowCount(len(data_list))

        for row_idx, row_dict in enumerate(data_list):
            for col_idx, key in enumerate(sorted_keys):
                value = row_dict.get(key, "") # Get value, or empty string if key not present
                # Corrected: Use self.table_view instead of self.table_widget
                self.table_view.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))
        
        # Corrected: Use self.table_view instead of self.table_widget
        self.table_view.resizeColumnsToContents()
        self.table_view.horizontalHeader().setStretchLastSection(True)

    def _populate_table_from_single_dict(self, data_dict):
        """Populates the internal table_view from a single dictionary (JSON object)."""
        # Corrected: Use self.table_view instead of self.table_widget
        self.table_view.setColumnCount(2) # Key | Value
        self.table_view.setHorizontalHeaderLabels([self.tr("Key"), self.tr("Value")])
        self.table_view.setRowCount(len(data_dict))

        for row_idx, (key, value) in enumerate(data_dict.items()):
            # Corrected: Use self.table_view instead of self.table_widget
            self.table_view.setItem(row_idx, 0, QTableWidgetItem(str(key)))
            self.table_view.setItem(row_idx, 1, QTableWidgetItem(str(value)))
        
        # Corrected: Use self.table_view instead of self.table_widget
        self.table_view.resizeColumnsToContents()
        self.table_view.horizontalHeader().setStretchLastSection(True)


# --- New Search Functionality ---

class SearchWorker(QRunnable):
    """
    A QRunnable to perform text search in a separate thread.
    Emits signals for completion.
    """
    finished = Signal(list, str, int) # Emits list of (start_pos, line_number), query, query_length

    def __init__(self, text_content, query, parent=None):
        super().__init__()
        self.text_content = text_content
        self.query = query
        self.query_length = len(query)
        self.signals = SearchWorkerSignals() # Use an internal QObject for signals

    def run(self):
        """Performs the search operation."""
        matches = [] # Stores (start_pos, line_number)
        if not self.query:
            self.signals.finished.emit(matches, self.query, self.query_length)
            return

        text_lower = self.text_content.lower()
        query_lower = self.query.lower()
        
        current_pos = 0
        line_number = 1
        
        # Pre-calculate line start positions for efficient line number lookup
        line_start_positions = [0]
        for char in self.text_content:
            if char == '\n':
                line_start_positions.append(current_pos + 1)
            current_pos += 1

        current_pos = 0
        while True:
            idx = text_lower.find(query_lower, current_pos)
            if idx == -1:
                break
            
            # Find line number for the match
            # This is a bit inefficient for very large files, but acceptable for typical text sizes.
            # A more optimized approach would be to track line numbers during the find loop.
            match_line_number = 1
            for i in range(len(line_start_positions)):
                if line_start_positions[i] > idx:
                    match_line_number = i
                    break
                match_line_number = len(line_start_positions) # If match is on the last line

            matches.append((idx, match_line_number))
            current_pos = idx + self.query_length

        self.signals.finished.emit(matches, self.query, self.query_length)

class SearchWorkerSignals(QObject):
    """Defines the signals available from a running worker thread."""
    finished = Signal(list, str, int) # Emits list of (start_pos, line_number), query, query_length

class SearchTab(QWidget):
    """
    A new tab for performing text search on the content of the TextTab.
    Uses multi-threading for search operations.
    """
    highlight_requested = Signal(list, int, int) # Emits (matches_data, current_match_index, query_length)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.text_to_search = ""
        self.search_matches = [] # Stores (start_pos, line_number)
        self.current_match_index = -1
        self.current_query = ""
        self.current_query_length = 0

        # Thread pool for search operations
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(1) # Only one search at a time

        # Search Controls
        search_control_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("Enter search query..."))
        self.search_input.returnPressed.connect(self._start_search)
        search_control_layout.addWidget(self.search_input)

        self.search_button = QPushButton(self.tr("Search"))
        self.search_button.clicked.connect(self._start_search)
        search_control_layout.addWidget(self.search_button)

        self.search_count_label = QLabel(self.tr("Matches: 0"))
        search_control_layout.addWidget(self.search_count_label)

        self.prev_match_button = QPushButton(self.tr("Previous"))
        self.prev_match_button.clicked.connect(self._find_prev_match)
        search_control_layout.addWidget(self.prev_match_button)

        self.next_match_button = QPushButton(self.tr("Next"))
        self.next_match_button.clicked.connect(self._find_next_match)
        search_control_layout.addWidget(self.next_match_button)
        self.layout.addLayout(search_control_layout)

        # Search Results Display
        self.results_list_widget = QListWidget()
        self.results_list_widget.setFont(QFont("Monospace", 9))
        self.results_list_widget.itemClicked.connect(self._on_result_item_clicked)
        self.layout.addWidget(self.results_list_widget)

    @Slot(str)
    def set_text_content(self, text_content):
        """Receives the text content from TextTab to perform searches on."""
        self.text_to_search = text_content
        self._clear_search_results()
        # If there's an active query, re-run search on new content
        if self.current_query:
            self._start_search()

    def _start_search(self):
        query = self.search_input.text()
        if not query:
            self._clear_search_results()
            return
        
        self.current_query = query
        self.current_query_length = len(query)
        self._clear_search_results() # Clear previous results before new search

        self.search_button.setEnabled(False)
        self.search_input.setEnabled(False)
        self.prev_match_button.setEnabled(False)
        self.next_match_button.setEnabled(False)
        self.results_list_widget.clear()
        self.results_list_widget.addItem(self.tr("Searching..."))

        worker = SearchWorker(self.text_to_search, query)
        worker.signals.finished.connect(self._on_search_finished)
        self.thread_pool.start(worker)

    @Slot(list, str, int)
    def _on_search_finished(self, matches, query, query_length):
        self.search_matches = matches
        self.current_query = query
        self.current_query_length = query_length

        self.search_button.setEnabled(True)
        self.search_input.setEnabled(True)
        
        self.results_list_widget.clear()
        self.search_count_label.setText(self.tr(f"Matches: {len(self.search_matches)}"))

        if not self.search_matches:
            self.results_list_widget.addItem(self.tr("No matches found."))
            self.current_match_index = -1
            self.prev_match_button.setEnabled(False)
            self.next_match_button.setEnabled(False)
            self.highlight_requested.emit([], -1, 0) # Clear highlights in TextTab
            return

        # Populate results list with snippets
        for i, (start_pos, line_num) in enumerate(self.search_matches):
            # Get the line containing the match
            line_start = self.text_to_search.rfind('\n', 0, start_pos) + 1
            line_end = self.text_to_search.find('\n', start_pos)
            if line_end == -1:
                line_end = len(self.text_to_search)
            
            line_content = self.text_to_search[line_start:line_end].strip()
            
            # Create a snippet around the match
            snippet_start = max(0, start_pos - line_start - 20) # 20 chars before
            snippet_end = min(len(line_content), start_pos - line_start + query_length + 20) # 20 chars after
            snippet = line_content[snippet_start:snippet_end]
            
            # Highlight the query in the snippet for display
            highlighted_snippet = snippet.replace(query, f"<b>{query}</b>", 1) # Highlight first occurrence
            
            item_text = f"Line {line_num}: {highlighted_snippet}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, i) # Store the index of the match
            self.results_list_widget.addItem(item)
        
        self.current_match_index = 0
        self._update_match_navigation_buttons()
        self.results_list_widget.setCurrentRow(self.current_match_index)
        self._highlight_current_match_in_text_tab()

    def _clear_search_results(self):
        self.search_matches = []
        self.current_match_index = -1
        self.current_query = ""
        self.current_query_length = 0
        self.search_count_label.setText(self.tr("Matches: 0"))
        self.results_list_widget.clear()
        self.prev_match_button.setEnabled(False)
        self.next_match_button.setEnabled(False)
        self.highlight_requested.emit([], -1, 0) # Clear highlights in TextTab

    def _update_match_navigation_buttons(self):
        if len(self.search_matches) > 1:
            self.prev_match_button.setEnabled(True)
            self.next_match_button.setEnabled(True)
        else:
            self.prev_match_button.setEnabled(False)
            self.next_match_button.setEnabled(False)

    @Slot(QListWidgetItem)
    def _on_result_item_clicked(self, item):
        index = item.data(Qt.UserRole)
        if index is not None:
            self.current_match_index = index
            self._highlight_current_match_in_text_tab()

    def _find_prev_match(self):
        if not self.search_matches:
            return
        self.current_match_index = (self.current_match_index - 1 + len(self.search_matches)) % len(self.search_matches)
        self.results_list_widget.setCurrentRow(self.current_match_index)
        self._highlight_current_match_in_text_tab()

    def _find_next_match(self):
        if not self.search_matches:
            return
        self.current_match_index = (self.current_match_index + 1) % len(self.search_matches)
        self.results_list_widget.setCurrentRow(self.current_match_index)
        self._highlight_current_match_in_text_tab()

    def _highlight_current_match_in_text_tab(self):
        if self.search_matches and self.current_match_index != -1:
            self.highlight_requested.emit(self.search_matches, self.current_match_index, self.current_query_length)
        else:
            self.highlight_requested.emit([], -1, 0) # Clear highlights


class InfoscavaMainWindow(QMainWindow):
    def __init__(self, initial_filepath=None):
        super().__init__()
        self.setWindowTitle(self.tr("Infoscava - Universal File Analyzer"))
        # Set the window icon to icon.jpg from the same directory
        self.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), "icon.jpg")))

        self.current_filepath = None
        self.file_content_bytes = b""
        self.file_metadata = {}
        self.analysis_thread = None # Keep a reference to the thread
        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.fileChanged.connect(self._on_file_changed)

        # Initialize SettingsManager and load settings
        self.settings_manager = SettingsManager(self)
        self.app_settings = self.settings_manager.get_settings()

        self._setup_ui()
        # PluginManager is initialized BEFORE main_window is shown,
        # so it can load plugins from config and history.
        self.plugin_manager = PluginManager(self.app_settings['MAX_PLUGIN_HISTORY_ENTRIES'], self) 
        self.plugin_manager.set_plugin_history_tab(self.plugin_history_tab) # Pass history tab reference
        # Connect signal for initial static plugin tab creation
        self.plugin_manager.plugin_loaded_signal.connect(self._add_static_plugin_tab_if_applicable)
        # Connect signal for plugin deletion to remove its tab
        self.plugin_manager.plugin_deleted_signal.connect(self._remove_plugin_tab)
        # New: Connect signal to re-analyze file when plugins change
        self.plugin_manager.reanalyze_requested.connect(self._reanalyze_current_file_if_loaded)

        # Connect TextTab content changes to SearchTab
        self.text_tab.text_content_changed.connect(self.search_tab.set_text_content)
        # Connect SearchTab highlight requests to TextTab
        self.search_tab.highlight_requested.connect(self.text_tab.highlight_matches)

        self._setup_menu_bar()
        self._setup_status_bar()
        self._setup_drag_and_drop()
        self._load_theme_settings() # Load theme settings at startup
        self._update_ui_with_settings() # Apply initial settings to UI elements
        

        if initial_filepath:
            self._load_file(initial_filepath)

    def _setup_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)

        self.splitter = QSplitter(Qt.Horizontal)
        self.main_layout.addWidget(self.splitter)

        self._setup_sidebar()
        self._setup_main_content_area()

    def _setup_sidebar(self):
        self.sidebar_widget = QWidget()
        self.sidebar_layout = QVBoxLayout(self.sidebar_widget)
        self.sidebar_widget.setLayout(self.sidebar_layout)

        self.browse_button = QPushButton(self.tr("Browse File"))
        self.browse_button.clicked.connect(self._browse_file)
        self.sidebar_layout.addWidget(self.browse_button)

        self.clear_button = QPushButton(self.tr("Clear All"))
        self.clear_button.clicked.connect(self._clear_all)
        self.sidebar_layout.addWidget(self.clear_button)

        self.file_tree_model = QFileSystemModel()
        self.file_tree_model.setRootPath(QDir.currentPath())
        self.file_tree = QTreeView()
        self.file_tree.setModel(self.file_tree_model)
        self.file_tree.setRootIndex(self.file_tree_model.index(QDir.currentPath()))
        self.file_tree.setColumnHidden(1, True)
        self.file_tree.setColumnHidden(2, True)
        self.file_tree.setColumnHidden(3, True)
        self.file_tree.clicked.connect(self._on_file_tree_clicked)
        self.sidebar_layout.addWidget(self.file_tree)

        self.splitter.addWidget(self.sidebar_widget)
        self.splitter.setSizes([200, 800])

    def _setup_main_content_area(self):
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_widget.setLayout(self.content_layout)

        self.file_path_display = QLineEdit(self.tr("No file selected."))
        self.file_path_display.setReadOnly(True)
        self.content_layout.addWidget(self.file_path_display)

        self.tab_widget = QTabWidget()
        self.content_layout.addWidget(self.tab_widget)

        self.metadata_tab = MetadataTab()
        self.tab_widget.addTab(self.metadata_tab, self.tr("Metadata"))

        self.text_tab = TextTab()
        self.tab_widget.addTab(self.text_tab, self.tr("Text"))

        self.search_tab = SearchTab() # New Search Tab
        self.tab_widget.addTab(self.search_tab, self.tr("Search"))

        self.hex_tab = HexView()
        self.tab_widget.addTab(self.hex_tab, self.tr("Hex View"))

        self.structured_tab = StructuredView()
        self.tab_widget.addTab(self.structured_tab, self.tr("Structured View"))

        self.image_metadata_tab = ImageMetadataTab()
        self.tab_widget.addTab(self.image_metadata_tab, self.tr("Image Metadata"))
        if not PIL_AVAILABLE:
            self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.image_metadata_tab), False)

        self.base64_tab = Base64View()
        self.tab_widget.addTab(self.base64_tab, self.tr("Base64 View"))

        self.entropy_tab = EntropyTab()
        self.tab_widget.addTab(self.entropy_tab, self.tr("Entropy"))

        self.byte_histogram_tab = ByteHistogram()
        self.tab_widget.addTab(self.byte_histogram_tab, self.tr("Byte Histogram"))
        if not MATPLOTLIB_AVAILABLE:
            self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.byte_histogram_tab), False)
        
        self.plugin_history_tab = PluginHistoryTab()
        self.tab_widget.addTab(self.plugin_history_tab, self.tr("Plugin History"))

        self.analysis_plugin_tabs = {} # To keep track of dynamically added plugin tabs (per file analysis)
        self.static_plugin_tabs = {} # To keep track of static HTML plugin tabs (loaded at startup)

        self.splitter.addWidget(self.content_widget)

    def _setup_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu(self.tr("&File"))
        open_action = QAction(self.tr("&Open File..."), self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._browse_file)
        file_menu.addAction(open_action)

        reload_action = QAction(self.tr("&Reload File"), self)
        reload_action.setShortcut(QKeySequence.Refresh)
        reload_action.triggered.connect(self._reload_current_file)
        file_menu.addAction(reload_action)

        file_menu.addSeparator()

        export_action = QAction(self.tr("&Export Analysis..."), self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._export_analysis)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction(self.tr("E&xit"), self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = menu_bar.addMenu(self.tr("&View"))
        self.theme_toggle_action = QAction(self.tr("Toggle &Theme"), self)
        self.theme_toggle_action.setShortcut(QKeySequence("Ctrl+T"))
        self.theme_toggle_action.triggered.connect(self._toggle_theme)
        view_menu.addAction(self.theme_toggle_action)

        # --- Settings Menu ---
        settings_menu = menu_bar.addMenu(self.tr("&Settings"))
        app_settings_action = QAction(self.tr("&Application Settings..."), self)
        app_settings_action.triggered.connect(self._show_settings_dialog)
        settings_menu.addAction(app_settings_action)
        # --- End Settings Menu ---

        # --- Plugins Menu ---
        plugins_menu = menu_bar.addMenu(self.tr("&Plugins"))
        # Only one entry point for plugin management
        manage_plugins_action = QAction(self.tr("&Manage Plugins..."), self)
        manage_plugins_action.triggered.connect(self._show_manage_plugins_dialog)
        plugins_menu.addAction(manage_plugins_action)
        # --- End Plugins Menu ---

        help_menu = menu_bar.addMenu(self.tr("&Help"))
        about_action = QAction(self.tr("&About Infoscava"), self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)

        help_dialog_action = QAction(self.tr("&Help..."), self)
        help_dialog_action.setShortcut(QKeySequence("Ctrl+H"))
        help_dialog_action.triggered.connect(self._show_help_dialog)
        help_menu.addAction(help_dialog_action)

    def _setup_status_bar(self):
        self.status_bar = self.statusBar()
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        self.status_bar.addPermanentWidget(self.progress_bar)

    def _setup_drag_and_drop(self):
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if os.path.isfile(filepath):
                self._load_file(filepath)
                break
        event.acceptProposedAction()

    def _load_file(self, filepath):
        if not os.path.exists(filepath):
            QMessageBox.warning(self, self.tr("File Not Found"), self.tr(f"The file '{filepath}' does not exist."))
            return
        if not os.access(filepath, os.R_OK):
            QMessageBox.warning(self, self.tr("Permission Denied"), self.tr(f"Cannot read file '{filepath}'. Permission denied."))
            return
        # Security check: Prevent loading files from sensitive system directories
        if sys.platform.startswith('linux') or sys.platform.startswith('darwin'): # Linux/macOS
            sensitive_paths = ['/proc', '/dev', '/sys']
            for sensitive_path in sensitive_paths:
                if os.path.commonpath([filepath, sensitive_path]) == sensitive_path:
                    QMessageBox.warning(self, self.tr("Invalid File Path"), self.tr(f"Loading files from '{filepath}' is not allowed for security reasons."))
                    return
        elif sys.platform.startswith('win'): # Windows
            sensitive_paths = [
                os.path.join(os.environ.get('SystemRoot', 'C:\\Windows')), # C:\Windows
                os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files')), # C:\Program Files
                os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)')), # C:\Program Files (x86)
                os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu'), # Start Menu
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Temporary Internet Files'), # IE Cache
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Temp') # Temporary files
            ]
            # Normalize paths to handle case-insensitivity and different path separators on Windows
            filepath_norm = os.path.normpath(filepath).lower()
            for sensitive_path in sensitive_paths:
                sensitive_path_norm = os.path.normpath(sensitive_path).lower()
                if filepath_norm.startswith(sensitive_path_norm):
                    QMessageBox.warning(self, self.tr("Invalid File Path"), self.tr(f"Loading files from '{filepath}' is not allowed for security reasons."))
                    return

        self.current_filepath = filepath
        self.file_path_display.setText(filepath)
        self.status_bar.showMessage(self.tr(f"Loading file: {os.path.basename(filepath)}..."))
        self.progress_bar.setValue(0) # Ensure progress bar starts at 0
        self.progress_bar.show()

        try:
            with open(filepath, 'rb') as f:
                self.file_content_bytes = f.read()
            self._start_analysis_thread(filepath) # Changed to start analysis thread
            self._start_file_watcher(filepath)
        except MemoryError:
            QMessageBox.critical(self, self.tr("Memory Error"), self.tr("File is too large to load into memory."))
            self._clear_all()
        except Exception as e:
            QMessageBox.critical(self, self.tr("File Load Error"), self.tr(f"An error occurred while loading the file: {e}"))
            self._clear_all()

    def _start_analysis_thread(self, filepath):
        # Stop any existing thread if it's running
        if self.analysis_thread and self.analysis_thread.isRunning():
            self.analysis_thread.quit()
            self.analysis_thread.wait()

        # Pass the current MAX_FILE_SIZE_FOR_FULL_READ from settings
        self.analysis_thread = FileAnalyzerThread(filepath, self.app_settings['MAX_FILE_SIZE_FOR_FULL_READ'], self)
        self.analysis_thread.finished.connect(self._on_analysis_finished)
        self.analysis_thread.error.connect(self._on_analysis_error)
        self.analysis_thread.progress.connect(self._on_analysis_progress)
        self.analysis_thread.start()

    def _on_analysis_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.status_bar.showMessage(message)

    def _on_analysis_finished(self, results):
        self.file_metadata = results
        self.metadata_tab.update_metadata(results)

        is_large_file = results.get('size', 0) > self.app_settings['MAX_FILE_SIZE_FOR_FULL_READ']

        self.text_tab.set_file_content(self.file_content_bytes, results.get('encoding'), is_large_file, self.app_settings['MAX_TEXT_PREVIEW_LINES'])
        self.hex_tab.set_file_content(self.file_content_bytes, is_large_file, self.app_settings['MAX_HEX_PREVIEW_BYTES'])
        self.structured_tab.set_file_content(self.file_content_bytes, results.get('mime_type'), results.get('encoding'), is_large_file, self.app_settings['MAX_STRUCTURED_PREVIEW_LINES'])
        self.base64_tab.set_file_content(self.file_content_bytes)
        self.entropy_tab.update_entropy(results.get('entropy'))
        self.byte_histogram_tab.plot_histogram(self.file_content_bytes)

        if PIL_AVAILABLE and results.get('mime_type', '').startswith('image/'):
            self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.image_metadata_tab), True)
            self.image_metadata_tab.update_image_data(self.current_filepath, results)
        else:
            self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.image_metadata_tab), False)

        # --- Execute Analysis Plugins and Create Tabs ---
        self._clear_analysis_plugin_tabs() # Clear old analysis plugin tabs before adding new ones
        
        # Store plugin results in self.file_metadata for export
        self.file_metadata['plugin_analysis_results'] = {} 
        plugin_raw_results = self.plugin_manager.execute_analysis_plugins(self.current_filepath, self.file_content_bytes)
        
        for plugin_name, result in plugin_raw_results.items():
            self.file_metadata['plugin_analysis_results'][plugin_name] = result # Store raw result for export

            tab_title = self.plugin_manager.loaded_plugins[plugin_name].get('tab_title', plugin_name)

            # Handle display based on output type
            if isinstance(result, dict) and result.get("infoscava_output_type") == "html":
                html_content = result.get("content")
                plugin_output_tab = QTextBrowser() # Use QTextBrowser for HTML rendering
                plugin_output_tab.setReadOnly(True)
                plugin_output_tab.setOpenExternalLinks(True)

                if isinstance(html_content, str):
                    if not html_content.strip(): # Check if content is empty or just whitespace
                        plugin_output_tab.setPlainText(self.tr(f"Plugin '{plugin_name}' returned empty HTML content."))
                        index = self.tab_widget.addTab(plugin_output_tab, self.tr(f"Plugin: {tab_title} (HTML - Empty)"))
                    else:
                        plugin_output_tab.setHtml(html_content)
                        index = self.tab_widget.addTab(plugin_output_tab, self.tr(f"Plugin: {tab_title} (HTML)"))
                else:
                    # If the plugin specified HTML output but didn't return a string, display an error.
                    plugin_output_tab.setPlainText(self.tr(f"Plugin '{plugin_name}' returned HTML output type, but the content was not a string. Type: {type(html_content)}"))
                    index = self.tab_widget.addTab(plugin_output_tab, self.tr(f"Plugin: {tab_title} (HTML Error)"))
                # Store the widget directly, not its index
                self.analysis_plugin_tabs[plugin_name] = plugin_output_tab 
            elif isinstance(result, (dict, list)): # Handle JSON output
                plugin_output_tab = JsonTableViewer() # Use the new JsonTableViewer
                plugin_output_tab.set_json_content(result)
                index = self.tab_widget.addTab(plugin_output_tab, self.tr(f"Plugin: {tab_title} (JSON)"))
                # Store the widget directly, not its index
                self.analysis_plugin_tabs[plugin_name] = plugin_output_tab
            else:
                # Existing logic for other text/str output
                plugin_output_tab = QTextEdit()
                plugin_output_tab.setReadOnly(True)
                plugin_output_tab.setFont(QFont("Monospace", 9))
                plugin_output_tab.setPlainText(str(result))
                index = self.tab_widget.addTab(plugin_output_tab, self.tr(f"Plugin: {tab_title}"))
                # Store the widget directly, not its index
                self.analysis_plugin_tabs[plugin_name] = plugin_output_tab
        # --- End Execute Analysis Plugins ---

        self.progress_bar.hide()
        self.status_bar.showMessage(self.tr("File analysis complete."), 5000)

    def _on_analysis_error(self, message):
        QMessageBox.critical(self, self.tr("Analysis Error"), message)
        self.progress_bar.hide()
        self.status_bar.showMessage(self.tr("File analysis failed."), 5000)
        self._clear_all_tabs_content()

    def _browse_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, self.tr("Select File to Analyze"))
        if filepath:
            self._load_file(filepath)

    def _clear_all(self):
        self.current_filepath = None
        self.file_content_bytes = b""
        self.file_metadata = {}
        self.file_path_display.setText(self.tr("No file selected."))
        self.status_bar.showMessage(self.tr("Ready."))
        self.progress_bar.hide()
        self.progress_bar.setValue(0) # Reset progress bar value
        self._clear_all_tabs_content()
        self._clear_analysis_plugin_tabs() # Clear all dynamic analysis plugin tabs
        # For now, keeping static tabs persistent, as they are loaded once at startup.
        if self.file_watcher.files():
            self.file_watcher.removePaths(self.file_watcher.files())

    def _clear_all_tabs_content(self):
        self.metadata_tab.update_metadata({})
        self.text_tab.set_file_content(b"", max_text_preview_lines=self.app_settings['MAX_TEXT_PREVIEW_LINES'])
        self.search_tab.set_text_content("") # Clear search tab content
        self.hex_tab.set_file_content(b"", max_hex_preview_bytes=self.app_settings['MAX_HEX_PREVIEW_BYTES'])
        self.structured_tab.set_file_content(b"", "", max_structured_preview_lines=self.app_settings['MAX_STRUCTURED_PREVIEW_LINES'])
        self.image_metadata_tab.update_image_data("", {})
        self.base64_tab.set_file_content(b"")
        self.entropy_tab.update_entropy("N/A")
        self.byte_histogram_tab.plot_histogram(b"")
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.image_metadata_tab), False)

    def _clear_analysis_plugin_tabs(self):
        """Removes all dynamically added analysis plugin tabs."""
        # Iterate over a copy of the keys to avoid issues when deleting items
        for plugin_name in list(self.analysis_plugin_tabs.keys()):
            widget = self.analysis_plugin_tabs[plugin_name]
            index = self.tab_widget.indexOf(widget) # Get current index of the widget
            if index != -1: # Ensure the widget is still in the tab widget
                self.tab_widget.removeTab(index)
                widget.deleteLater() # Ensure widget is properly deleted
            del self.analysis_plugin_tabs[plugin_name]

    @Slot(str)
    def _remove_plugin_tab(self, plugin_name):
        """Removes a plugin's tab from the QTabWidget."""
        # Check analysis plugin tabs
        if plugin_name in self.analysis_plugin_tabs:
            widget = self.analysis_plugin_tabs[plugin_name]
            index = self.tab_widget.indexOf(widget)
            if index != -1: # Add check for None
                self.tab_widget.removeTab(index)
                widget.deleteLater()
            del self.analysis_plugin_tabs[plugin_name]
            return

        # Check static plugin tabs
        for name, widget in list(self.static_plugin_tabs.items()):
            if name == plugin_name:
                index = self.tab_widget.indexOf(widget)
                if index != -1:
                    widget_to_remove = self.tab_widget.widget(index)
                    if widget_to_remove: # Add check for None
                        self.tab_widget.removeTab(index)
                        widget_to_remove.deleteLater()
                    del self.static_plugin_tabs[name]
                    return

    @Slot(str)
    def _add_static_plugin_tab_if_applicable(self, plugin_name):
        """
        Adds a tab for a static HTML plugin if it's not already added.
        This is connected to plugin_manager.plugin_loaded_signal.
        """
        if plugin_name in self.static_plugin_tabs:
            return # Already added

        plugin_info = self.plugin_manager.loaded_plugins.get(plugin_name)
        if plugin_info and plugin_info['type'] == 'static_html_plugin':
            try:
                # Execute the plugin function to get the HTML content
                html_content = plugin_info['function']()
                
                if isinstance(html_content, str):
                    plugin_output_tab = QTextBrowser()
                    plugin_output_tab.setReadOnly(True)
                    plugin_output_tab.setOpenExternalLinks(True)
                    plugin_output_tab.setHtml(html_content)
                    
                    tab_title = plugin_info.get('tab_title', plugin_name)
                    index = self.tab_widget.addTab(plugin_output_tab, self.tr(f"Plugin: {tab_title}"))
                    self.static_plugin_tabs[plugin_name] = plugin_output_tab # Store the widget itself
                    self.plugin_manager._log(self.tr(f"Created static HTML tab for plugin: {plugin_name}"))
                else:
                    self.plugin_manager._log(self.tr(f"Static HTML plugin '{plugin_name}' did not return a string. Tab not created."))
            except Exception as e:
                error_details = traceback.format_exc()
                self.plugin_manager._log(self.tr(f"Error creating static tab for plugin '{plugin_name}': {e}\nDetails:\n{error_details}"))


    def _on_file_tree_clicked(self, index):
        filepath = self.file_tree_model.filePath(index)
        if os.path.isfile(filepath):
            self._load_file(filepath)

    def _start_file_watcher(self, filepath):
        if self.file_watcher.files():
            self.file_watcher.removePaths(self.file_watcher.files())
        self.file_watcher.addPath(filepath)

    def _on_file_changed(self, path):
        if path == self.current_filepath:
            # Check if the file still exists
            if os.path.exists(path):
                QMessageBox.information(self, self.tr("File Changed"), self.tr("The loaded file has changed on disk. Reloading..."))
                self._load_file(self.current_filepath)
            else:
                # File was deleted
                QMessageBox.information(self, self.tr("File Deleted"), self.tr("The loaded file has been deleted from disk. Clearing analysis."))
                self._clear_all() # Perform a full cleanup

    @Slot()
    def _reanalyze_current_file_if_loaded(self):
        """
        Slot to re-analyze the current file if one is loaded.
        Called when plugin configuration changes (load, delete, reload).
        """
        if self.current_filepath and os.path.exists(self.current_filepath):
            self._load_file(self.current_filepath) # Re-load and re-analyze
        else:
            self._clear_all() # Just clear the UI if no file to re-analyze


    def _reload_current_file(self):
        if self.current_filepath:
            self._load_file(self.current_filepath)
        else:
            QMessageBox.information(self, self.tr("No File Loaded"), self.tr("No file is currently loaded to reload."))

    def _export_analysis(self):
        if not self.file_metadata:
            QMessageBox.warning(self, self.tr("No Analysis to Export"), self.tr("Please load and analyze a file first."))
            return

        filename, _ = QFileDialog.getSaveFileName(self, self.tr("Export Analysis"), os.path.basename(self.current_filepath or "report"),
                                                  self.tr("JSON Files (*.json);;Text Files (*.txt);;HTML Files (*.html)"))
        if not filename:
            return

        try:
            if filename.endswith('.json'):
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(self.file_metadata, f, indent=4, ensure_ascii=False)
            elif filename.endswith('.txt'):
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.tr("--- Infoscava Analysis Report ---\n\n"))
                    for key, value in self.file_metadata.items():
                        # Skip plugin_analysis_results for top-level display, handle separately
                        if key == 'plugin_analysis_results':
                            continue
                        display_value = value
                        if isinstance(value, dict):
                            display_value = json.dumps(value, indent=2, ensure_ascii=False)
                        elif isinstance(value, float):
                            if key == 'encoding_confidence':
                                display_value = f"{value:.2f}%"
                            else:
                                display_value = f"{value:.4f}"
                        elif key == 'size':
                            display_value = human_readable_size(value)
                        f.write(f"{key.replace('_', ' ').title()}: {display_value}\n")

                    if 'plugin_analysis_results' in self.file_metadata and self.file_metadata['plugin_analysis_results']:
                        f.write("\n--- Plugin Analysis Results ---\n\n")
                        for plugin_name, plugin_output in self.file_metadata['plugin_analysis_results'].items():
                            f.write(f"Plugin: {plugin_name}\n")
                            if isinstance(plugin_output, dict) and plugin_output.get("infoscava_output_type") == "html":
                                f.write(f"  Output Type: HTML (content truncated for text export)\n")
                                # For text export, just show a snippet or indicator for HTML
                                f.write(f"  Content: {plugin_output.get('content', '')[:500]}...\n\n")
                            elif isinstance(plugin_output, dict):
                                f.write(f"  Content:\n{json.dumps(plugin_output, indent=2, ensure_ascii=False)}\n\n")
                            else:
                                f.write(f"  Content:\n{str(plugin_output)}\n\n")

                    f.write("\n--- Text Content (Preview) ---\n\n")
                    f.write(self.text_tab.text_editor.toPlainText()[:self.app_settings['MAX_TEXT_PREVIEW_LINES'] * 2])
            elif filename.endswith('.html'):
                html_content = self._generate_html_report()
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(html_content)
            self.status_bar.showMessage(self.tr(f"Analysis exported to {filename}"), 5000)
        except Exception as e:
            QMessageBox.critical(self, self.tr("Export Error"), self.tr(f"Failed to export analysis: {e}"))

    def _generate_html_report(self):
        report_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{self.tr("Infoscava Analysis Report")}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f4f4f4; color: #333; }}
                h1 {{ color: #0056b3; }}
                h2 {{ color: #007bff; border-bottom: 1px solid #ccc; padding-bottom: 5px; margin-top: 20px; }}
                .section {{ background-color: #fff; border-radius: 8px; padding: 15px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .label {{ font-weight: bold; margin-right: 5px; color: #555; }}
                pre {{ background-color: #eee; padding: 10px; border-radius: 5px; overflow-x: auto; white-space: pre-wrap; word-break: break-all; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <h1>{self.tr("Infoscava Analysis Report")}</h1>
            <div class="section">
                <h2>{self.tr("File Metadata")}</h2>
                <table>
                    <tbody>
        """
        for key, value in self.file_metadata.items():
            # Skip plugin_analysis_results for top-level display, handle separately
            if key == 'plugin_analysis_results':
                continue

            display_value = value
            if isinstance(value, dict):
                display_value = "<pre>" + json.dumps(value, indent=2, ensure_ascii=False) + "</pre>"
            elif isinstance(value, float):
                if key == 'encoding_confidence':
                    display_value = f"{value:.2f}%"
                else:
                    display_value = f"{value:.4f}"
            elif key == 'size':
                display_value = human_readable_size(value)

            report_html += f"""
                        <tr>
                            <td class="label">{key.replace('_', ' ').title()}:</td>
                            <td>{display_value}</td>
                        </tr>
            """
        report_html += """
                    </tbody>
                </table>
            </div>
        """

        # Add Plugin Analysis Results
        if 'plugin_analysis_results' in self.file_metadata and self.file_metadata['plugin_analysis_results']:
            report_html += f"""
            <div class="section">
                <h2>{self.tr("Plugin Analysis Results")}</h2>
            """
            for plugin_name, plugin_output in self.file_metadata['plugin_analysis_results'].items():
                report_html += f"<h3>{self.tr('Plugin')}: {plugin_name}</h3>"
                if isinstance(plugin_output, dict) and plugin_output.get("infoscava_output_type") == "html":
                    report_html += plugin_output.get("content", "<p>No HTML content provided.</p>")
                elif isinstance(plugin_output, dict):
                    report_html += f"<pre>{json.dumps(plugin_output, indent=2, ensure_ascii=False)}</pre>"
                else:
                    report_html += f"<pre>{str(plugin_output)}</pre>"
            report_html += "</div>"


        if self.text_tab.text_editor.toPlainText():
            report_html += f"""
            <div class="section">
                <h2>{self.tr("Text Content (Preview)")}</h2>
                <pre>{self.text_tab.text_editor.toPlainText()[:self.app_settings['MAX_TEXT_PREVIEW_LINES'] * 2]}</pre>
            </div>
            """

        if self.hex_tab.hex_editor.toPlainText():
            report_html += f"""
            <div class="section">
                <h2>{self.tr("Hexadecimal View (Preview)")}</h2>
                <pre>{self.hex_tab.hex_editor.toPlainText()[:self.app_settings['MAX_HEX_PREVIEW_BYTES'] * 4]}</pre>
            </div>
            """

        if self.structured_tab.text_editor.toPlainText() or self.structured_tab.table_widget.rowCount() > 0:
            # Check which widget is currently active in structured tab
            current_structured_content = ""
            if self.structured_tab.stacked_widget.currentIndex() == 0: # Text editor is active
                current_structured_content = self.structured_tab.text_editor.toPlainText()
            else: # Table widget is active (CSV)
                # Reconstruct CSV from table for HTML export
                csv_rows = []
                # Add headers
                headers = []
                for col in range(self.structured_tab.table_widget.columnCount()):
                    header_item = self.structured_tab.table_widget.horizontalHeaderItem(col)
                    headers.append(header_item.text() if header_item else "")
                if headers:
                    # Fix: Use string concatenation instead of f-string for the problematic part
                    csv_rows.append(",".join('"' + h.replace('"', '""') + '"' for h in headers)) # Basic CSV quoting

                # Add data rows
                for row_idx in range(self.structured_tab.table_widget.rowCount()):
                    row_data = []
                    for col_idx in range(self.structured_tab.table_widget.columnCount()):
                        item = self.structured_tab.table_widget.item(row_idx, col_idx)
                        cell_value = item.text() if item else ""
                        # Fix: Use string concatenation instead of f-string for the problematic part
                        row_data.append('"' + cell_value.replace('"', '""') + '"')
                    csv_rows.append(",".join(row_data))
                current_structured_content = "\n".join(csv_rows)

            if current_structured_content:
                report_html += f"""
                <div class="section">
                    <h2>{self.tr("Structured View (Preview)")}</h2>
                    <pre>{current_structured_content[:self.app_settings['MAX_STRUCTURED_PREVIEW_LINES'] * 2]}</pre>
                </div>
                """

        if self.base64_tab.base64_text_edit.toPlainText():
            report_html += f"""
            <div class="section">
                <h2>{self.tr("Base64 Encoded Content")}</h2>
                <pre>{self.base64_tab.base64_text_edit.toPlainText()[:1000]}</pre>
            </div>
            """

        report_html += """
        </body>
        </html>
        """
        return report_html

    def _show_about_dialog(self):
        QMessageBox.about(self, self.tr("About Infoscava"),
                          self.tr("<h3>Infoscava</h3>"
                                  "<p>Universal File Analyzer</p>"
                                  "<p>Version: 2.1.9</p>"
                                  "<p>Developer: Muhammed Shafin P (GitHub: <a href='https://github.com/hejhdiss'>hejhdiss</a>)</p>"
                                  "<p>Infoscava (Info + Scava, Latin for 'dig') is designed to excavate information from any file type.</p>"))

    def _show_help_dialog(self):
        help_dialog = HelpDialog(self)
        help_dialog.exec()

    def _save_theme_preference(self, theme_name):
        """Saves the current theme preference to a file."""
        try:
            with open(THEME_SETTINGS_FILE, 'w') as f:
                json.dump({'theme': theme_name}, f)
        except Exception as e:
            pass # Removed logging

    def _load_theme_preference(self):
        """Loads the last saved theme preference from a file."""
        try:
            if os.path.exists(THEME_SETTINGS_FILE):
                with open(THEME_SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                    return settings.get('theme', 'dark') # Default to 'dark' if not found
        except Exception as e:
            pass # Removed logging
        return 'dark' # Default to dark theme if file doesn't exist or error occurs

    def _toggle_theme(self):
        """Toggles between dark and light themes."""
        current_theme = self._load_theme_preference()
        if current_theme == 'dark':
            self._set_light_theme()
        else:
            self._set_dark_theme()
    def _set_dark_theme(self):
        app = QApplication.instance()
        palette = app.palette()
        palette.setColor(QPalette.Window, QColor("#1e1e1e"))
        palette.setColor(QPalette.WindowText, QColor("#ffffff"))
        palette.setColor(QPalette.Base, QColor("#2d2d30"))
        palette.setColor(QPalette.AlternateBase, QColor("#3c3c3c"))
        palette.setColor(QPalette.ToolTipBase, QColor("#2d2d30"))
        palette.setColor(QPalette.ToolTipText, QColor("#ffffff"))
        palette.setColor(QPalette.Text, QColor("#ffffff"))
        palette.setColor(QPalette.Button, QColor("#333333"))
        palette.setColor(QPalette.ButtonText, QColor("#ffffff"))
        palette.setColor(QPalette.BrightText, QColor("red"))
        palette.setColor(QPalette.Link, QColor("#61afef"))
        palette.setColor(QPalette.Highlight, QColor("#007acc"))
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        app.setPalette(palette)

        QApplication.instance().setStyleSheet("""
            /* Reset QTreeView::branch styling to allow native indicators */
            QTreeView::branch {{
                border: none;
                background: transparent;
                padding: 0;
                margin: 0;
                width: 16px; /* Explicit width to ensure space for indicator */
                height: 16px; /* Explicit height to ensure space for indicator */
            }}
            /* General QTreeView styling for visibility */
            QTreeView {{
                background-color: #2d2d30; /* Dark background */
                color: #ffffff; /* White text */
                alternate-background-color: #3c3c3c;
                border: 1px solid #555555;
            }}
            QTreeView::item {{
                color: #ffffff;
            }}
            QTreeView::item:selected {{
                background-color: #007acc;
                color: #ffffff;
            }}
        """)
        self.status_bar.showMessage(self.tr("Switched to Dark Theme"), 3000)
        self._save_theme_preference('dark')
    

    def _set_light_theme(self):
        app = QApplication.instance()
        palette = app.palette()
        # Refined light theme colors for a production-level look
        palette.setColor(QPalette.Window, QColor("#f8f8f8")) # Main window background - soft white
        palette.setColor(QPalette.WindowText, QColor("#1e1e1e")) # Dark text for readability
        palette.setColor(QPalette.Base, QColor("#ffffff")) # Base for input fields, text areas - pure white for content
        palette.setColor(QPalette.AlternateBase, QColor("#f0f0f0")) # Alternate row colors in lists/tables
        palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
        palette.setColor(QPalette.ToolTipText, QColor("#1e1e1e"))
        palette.setColor(QPalette.Text, QColor("#1e1e1e"))
        palette.setColor(QPalette.Button, QColor("#e8e8e8")) # Light gray button background
        palette.setColor(QPalette.ButtonText, QColor("#1e1e1e"))
        palette.setColor(QPalette.BrightText, QColor("red")) # Standard bright text color
        palette.setColor(QPalette.Link, QColor("#007bff")) # Standard blue for links
        palette.setColor(QPalette.Highlight, QColor("#aaddff")) # Light blue for selection highlight
        palette.setColor(QPalette.HighlightedText, QColor("#1e1e1e")) # Dark text on highlight
        app.setPalette(palette)

        # Apply comprehensive stylesheet overrides for light theme to ensure readability and consistent look
        QApplication.instance().setStyleSheet(f"""
            QMainWindow, QWidget, QSplitter {{
                background-color: #f8f8f8; /* Soft white for main window background */
                color: #1e1e1e; /* Dark text */
            }}
            QMenuBar {{
                background-color: #e8e8e8; /* Slightly darker than main window for distinction */
                color: #1e1e1e;
                border-bottom: 1px solid #d8d8d8; /* Subtle border */
            }}
            QMenuBar::item {{
                background-color: transparent;
                color: #1e1e1e;
                padding: 5px 10px;
            }}
            QMenuBar::item:selected {{
                background-color: #d0d0d0; /* Highlight on hover */
            }}
            QMenu {{
                background-color: #ffffff; /* Pure white for dropdown menus */
                color: #1e1e1e;
                border: 1px solid #d8d8d8;
                border-radius: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px 6px 10px; /* Padding for menu items */
            }}
            QMenu::item:selected {{
                background-color: #aaddff;
                color: #1e1e1e;
            }}
            QTextEdit, QTextBrowser {{
                background-color: #ffffff; /* Pure white for text content areas */
                color: #1e1e1e;
                border: 1px solid #d8d8d8;
                border-radius: 4px;
                padding: 5px;
            }}
            QComboBox {{
                background-color: #ffffff;
                color: #1e1e1e;
                border: 1px solid #d8d8d8;
                border-radius: 4px;
                padding: 2px 5px;
                selection-background-color: #aaddff;
                selection-color: #1e1e1e;
            }}
            QLineEdit {{
                background-color: #ffffff;
                color: #1e1e1e;
                border: 1px solid #d8d8d8;
                border-radius: 4px;
                padding: 2px 5px;
            }}
            QLabel {{
                color: #1e1e1e;
            }}
            QPushButton {{
                background-color: #e8e8e8;
                color: #1e1e1e;
                border: 1px solid #c8c8c8; /* Slightly darker border for buttons */
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: #d8d8d8;
                border-color: #b8b8b8;
            }}
            QPushButton:pressed {{
                background-color: #c8c8c8;
                border-color: #a8a8a8;
            }}
            QTreeView {{
                background-color: #f5f5f5; /* Very subtle darker white for QTreeView background */
                color: #1e1e1e;
                alternate-background-color: #f0f0f0; /* Clearer alternate row color */
                border: 1px solid #d8d8d8;
                border-radius: 4px;
            }}
            QTreeView::item {{
                color: #1e1e1e;
                padding: 3px 0; /* Add some vertical padding to items */
            }}
            QTreeView::item:selected {{
                background-color: #aaddff;
                color: #1e1e1e;
            }}
            QTreeView::branch:selected {{
                background-color: #aaddff; /* Ensure branches also highlight correctly */
            }}
            /* Removed specific QTreeView::branch styling to allow native indicators */
            QStatusBar {{
                background-color: #e8e8e8;
                color: #1e1e1e;
                border-top: 1px solid #d8d8d8;
            }}
            QProgressBar {{
                background-color: #e0e0e0;
                color: #1e1e1e;
                border: 1px solid #c0c0c0;
                border-radius: 5px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: #007bff;
                border-radius: 5px;
            }}
            QTabWidget::pane {{ /* The content area below the tabs */
                border: 1px solid #d8d8d8;
                background-color: #f8f8f8; /* Matches main window background */
                border-radius: 4px;
                margin-top: -1px; /* Overlap with tab bar border */
            }}
            QTabBar::tab {{
                background: #e5e5e5; /* Light grey for inactive tabs */
                border: 1px solid #d8d8d8;
                border-bottom-color: #d8d8d8; /* Same as pane border */
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 8px 15px;
                margin-right: 2px;
                color: #1e1e1e;
            }}
            QTabBar::tab:selected {{
                background: #f8f8f8; /* Matches main window background */
                border-bottom-color: #f8f8f8; /* Make selected tab's bottom border blend with pane */
                font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{
                background: #d8d8d8; /* Slightly darker grey on hover for inactive tabs */
            }}
        """)
        self.status_bar.showMessage(self.tr("Switched to Light Theme"), 3000)
        self._save_theme_preference('light')





    def closeEvent(self, event):
        """Ensures plugin history is saved on application close."""
        self.plugin_manager._save_history()
        super().closeEvent(event)

    def _show_manage_plugins_dialog(self):
        """Shows the dialog for managing plugins."""
        dialog = ManagePluginsDialog(self.plugin_manager, self)
        dialog.exec()

    def _show_settings_dialog(self):
        """Shows the application settings dialog."""
        dialog = SettingsDialog(self.app_settings, self)
        dialog.settings_saved.connect(self._apply_settings)
        dialog.exec()

    @Slot(dict)
    def _apply_settings(self, new_settings):
        """Applies new settings to the application and saves them."""
        self.app_settings = new_settings
        self.settings_manager.save_settings(self.app_settings)
        self._update_ui_with_settings()
        # If file size limits changed, re-analyze the current file to apply new limits
        if self.current_filepath and os.path.exists(self.current_filepath):
            self._load_file(self.current_filepath)
        else:
            # If no file is loaded, clear existing content previews to reflect new limits
            self._clear_all_tabs_content()
        QMessageBox.information(self, self.tr("Settings Saved"), self.tr("Application settings updated successfully."))

    def _update_ui_with_settings(self):
        """Propagates current settings to relevant UI components."""
        self.text_tab.max_text_preview_lines = self.app_settings['MAX_TEXT_PREVIEW_LINES']
        self.hex_tab.max_hex_preview_bytes = self.app_settings['MAX_HEX_PREVIEW_BYTES']
        self.structured_tab.max_structured_preview_lines = self.app_settings['MAX_STRUCTURED_PREVIEW_LINES']
        self.plugin_manager.update_settings(self.app_settings['MAX_PLUGIN_HISTORY_ENTRIES'])

        # Re-render current content with new preview limits if a file is loaded
        if self.current_filepath and os.path.exists(self.current_filepath):
            # Re-read file content to ensure it's fresh if needed, then update tabs
            try:
                with open(self.current_filepath, 'rb') as f:
                    self.file_content_bytes = f.read()
                # Pass is_large_file based on new setting
                is_large_file = os.path.getsize(self.current_filepath) > self.app_settings['MAX_FILE_SIZE_FOR_FULL_READ']
                
                # Update content in tabs with new limits
                self.text_tab.set_file_content(self.file_content_bytes, self.file_metadata.get('encoding'), is_large_file, self.app_settings['MAX_TEXT_PREVIEW_LINES'])
                self.hex_tab.set_file_content(self.file_content_bytes, is_large_file, self.app_settings['MAX_HEX_PREVIEW_BYTES'])
                self.structured_tab.set_file_content(self.file_content_bytes, self.file_metadata.get('mime_type'), self.file_metadata.get('encoding'), is_large_file, self.app_settings['MAX_STRUCTURED_PREVIEW_LINES'])
            except Exception as e:
                # Handle potential errors during re-reading file
                self.status_bar.showMessage(self.tr(f"Error re-applying settings to current file: {e}"), 5000)
        else:
            # If no file is loaded, just clear the previews to reflect the new limits
            self._clear_all_tabs_content()


    def _load_theme_settings(self):
        """Loads the saved theme preference and applies it at startup."""
        theme_name = self._load_theme_preference()
        if theme_name == 'dark':
            self._set_dark_theme()
        else:
            self._set_light_theme()
# Assuming these Base64 strings are defined elsewhere, e.g., in your main app

def main():
    parser = argparse.ArgumentParser(description="Infoscava - Universal File Analyzer")
    parser.add_argument("--file", help="Path to the file to analyze on startup.")
    parser.add_argument("--lang", help="Set application language (e.g., 'en', 'fr').")
    args = parser.parse_args()

    app = QApplication(sys.argv)

    translator = QTranslator()
    if args.lang:
        locale = QLocale(args.lang)
        if translator.load(locale, "infoscava", "_", ":/translations"):
            app.installTranslator(translator)
        else:
            pass # Removed logging

    main_window = InfoscavaMainWindow(initial_filepath=args.file)
    main_window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
