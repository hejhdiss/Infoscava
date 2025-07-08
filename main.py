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
    QSpinBox, QCheckBox, QTextBrowser # Import QTextBrowser
)
from PySide6.QtCore import (
    Qt, QThread, Signal, QRunnable, QThreadPool, QUrl, QTimer,
    QFileSystemWatcher, QCoreApplication, QTranslator, QLocale, QSize,
    QPoint, QRect, QDir, Slot, QObject # QObject imported for the new thread worker
)
from PySide6.QtGui import (
    QIcon, QTextCharFormat, QTextCursor, QSyntaxHighlighter,
    QTextDocument, QFont, QColor, QPalette, QDesktopServices,
    QImage, QPixmap, QPainter, QBrush, QKeySequence, QAction, QFontDatabase
)

MAX_FILE_SIZE_FOR_FULL_READ = 20 * 1024 * 1024
MAX_TEXT_PREVIEW_LINES = 10000
MAX_HEX_PREVIEW_BYTES = 16384
MAX_STRUCTURED_PREVIEW_LINES = 100

SUPPORTED_ENCODINGS = [
    "UTF-8", "UTF-16", "UTF-16BE", "UTF-16LE", "UTF-32", "UTF-32BE", "UTF-32LE", "UTF-7",
    "ASCII", "ISO-8859-1", "ISO-8859-2", "ISO-8859-3", "ISO-8859-4", "ISO-8859-5",
    "ISO-8859-6", "ISO-8859-7", "ISO-8859-8", "ISO-8859-9", "ISO-8859-10", "ISO-8859-11",
    "ISO-8859-13", "ISO-8859-14", "ISO-8859-15", "ISO-8859-16",
    "Windows-1250", "Windows-1251", "Windows-1252", "Windows-1253", "Windows-1254",
    "Windows-1255", "Windows-1256", "Windows-1257", "Windows-1258",
    "CP437", "CP720", "CP737", "CP775", "CP850", "CP852", "CP855", "CP856", "CP857",
    "CP858", "CP860", "CP861", "CP862", "CP863", "CP864", "CP865", "CP866", "CP869",
    "GB2312", "GBK", "GB18030", "Big5", "HKSCS", "Shift-JIS", "EUC-JP", "ISO-2022-JP",
    "EUC-KR", "ISO-2022-KR", "KOI8-R", "KOI8-U", "Macintosh", "EBCDIC", "ISCII",
    "TSCII", "VISCII", "JIS X 0201", "JIS X 0208", "JIS X 0213", "ANSEL",
    "MacCyrillic", "MacCroatian", "MacGreek", "MacTurkish", "DEC-MCS", "HP-Roman8"
]

# Path for theme settings file
THEME_SETTINGS_FILE = os.path.join(os.path.expanduser('~'), '.infoscava_theme.json')

def human_readable_size(size_bytes):
    if size_bytes == 0:
        return "0 Bytes"
    units = ("Bytes", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {units[i]}"

def calculate_hash(filepath, hash_algo):
    hasher = hash_algo()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        return f"Error: {e}"

def detect_encoding(filepath):
    try:
        with open(filepath, 'rb') as f:
            raw_data = f.read(1024 * 1024)
        result = chardet.detect(raw_data)
        return result['encoding'], result['confidence']
    except Exception as e:
        return None, 0.0

def calculate_shannon_entropy(filepath):
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
    mime_type, _ = mimetypes.guess_type(filepath)
    if mime_type:
        return mime_type
    _, ext = os.path.splitext(filepath)
    ext = ext.lower()
    if ext == '.json': return 'application/json'
    if ext == '.xml': return 'application/xml'
    if ext == '.csv': return 'text/csv'
    if ext in ['.jpg', '.jpeg']: return 'image/jpeg'
    if ext == '.png': return 'image/png'
    if ext == '.gif': return 'image/gif'
    if ext == '.bmp': return 'image/bmp'
    if ext == '.txt': return 'text/plain'
    if ext == '.bin': return 'application/octet-stream'
    return 'application/octet-stream'

# Refactored FileAnalyzerWorker to inherit from QThread for more explicit threading
class FileAnalyzerThread(QThread):
    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(int, str)

    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self.filepath = filepath

    def run(self):
        results = {}
        try:
            self.progress.emit(0, self.tr("Starting analysis..."))

            file_stat = os.stat(self.filepath)
            results['filename'] = os.path.basename(self.filepath)
            results['filepath'] = self.filepath
            results['size'] = file_stat.st_size
            results['last_modified'] = datetime.datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            results['mime_type'] = get_mime_type(self.filepath)
            self.progress.emit(10, self.tr("Basic info gathered."))

            encoding, confidence = detect_encoding(self.filepath)
            results['encoding'] = encoding
            results['encoding_confidence'] = confidence
            self.progress.emit(30, self.tr("Encoding detected."))

            results['sha256_hash'] = calculate_hash(self.filepath, hashlib.sha256)
            self.progress.emit(60, self.tr("SHA-256 calculated."))
            results['md5_hash'] = calculate_hash(self.filepath, hashlib.md5)
            self.progress.emit(90, self.tr("MD5 calculated."))

            results['entropy'] = calculate_shannon_entropy(self.filepath)
            self.progress.emit(95, self.tr("Entropy calculated."))

            if PIL_AVAILABLE and results['mime_type'].startswith('image/'):
                try:
                    with Image.open(self.filepath) as img:
                        results['image_format'] = img.format
                        results['image_dimensions'] = f"{img.width}x{img.height}"
                        results['image_mode'] = img.mode
                        exif_data = {}
                        if hasattr(img, '_getexif'):
                            # Check if _getexif() returns a dictionary or None
                            raw_exif = img._getexif()
                            if raw_exif is not None: # Added check for NoneType
                                for tag, value in raw_exif.items():
                                    decoded = ExifTags.TAGS.get(tag, tag)
                                    if isinstance(value, bytes):
                                        try:
                                            value = value.decode('utf-8', errors='ignore')
                                        except:
                                            pass
                                    exif_data[decoded] = value

                        results['exif_data'] = exif_data

                        gps_info = {}
                        if 'GPSInfo' in exif_data:
                            gps_data = exif_data[ExifTags.TAGS['GPSInfo']] if 'GPSInfo' in ExifTags.TAGS else exif_data['GPSInfo']
                            if 1 in gps_data and 2 in gps_data:
                                lat_ref = gps_data[1]
                                lat_tuple = gps_data[2]
                                latitude = sum(float(x) / 60**i for i, x in enumerate(lat_tuple))
                                if lat_ref == 'S': latitude = -latitude
                                gps_info['Latitude'] = latitude
                            if 3 in gps_data and 4 in gps_data:
                                lon_ref = gps_data[3]
                                lon_tuple = gps_data[4]
                                longitude = sum(float(x) / 60**i for i, x in enumerate(lon_tuple))
                                if lon_ref == 'W': longitude = -longitude
                                gps_info['Longitude'] = longitude
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
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(self.tr(f"Error during analysis: {e}"))

class MetadataTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.labels = {}
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
            label_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.labels[key] = label_value
            row_layout.addWidget(label_name)
            row_layout.addWidget(label_value, 1)
            row_layout.addStretch(1)
            self.layout.addLayout(row_layout)

        self.layout.addStretch(1)

    def update_metadata(self, metadata):
        self.labels['filename'].setText(metadata.get('filename', self.tr("N/A")))
        self.labels['filepath'].setText(metadata.get('filepath', self.tr("N/A")))
        self.labels['mime_type'].setText(metadata.get('mime_type', self.tr("N/A")))
        self.labels['size'].setText(human_readable_size(metadata.get('size', 0)))
        self.labels['last_modified'].setText(metadata.get('last_modified', self.tr("N/A")))
        self.labels['encoding'].setText(metadata.get('encoding', self.tr("N/A")))
        self.labels['encoding_confidence'].setText(f"{metadata.get('encoding_confidence', 0.0):.2f}%")
        self.labels['sha256_hash'].setText(metadata.get('sha256_hash', self.tr("N/A")))
        self.labels['md5_hash'].setText(metadata.get('md5_hash', self.tr("N/A")))
        self.labels['entropy'].setText(f"{metadata.get('entropy', 0.0):.4f}")

class TextHighlighter(QSyntaxHighlighter):
    def __init__(self, parent):
        super().__init__(parent)
        self.highlight_format = QTextCharFormat()
        self.highlight_range = None
        self.additional_highlights = []

    def highlightBlock(self, text):
        if self.highlight_range:
            start, length = self.highlight_range
            if start <= self.currentBlock().position() + len(text) and start + length >= self.currentBlock().position():
                relative_start = max(0, start - self.currentBlock().position())
                relative_end = min(len(text), start + length - self.currentBlock().position())
                self.setFormat(relative_start, relative_end - relative_start, self.highlight_format)

        for pos, length, fmt in self.additional_highlights:
            if pos <= self.currentBlock().position() + len(text) and pos + length >= self.currentBlock().position():
                relative_start = max(0, pos - self.currentBlock().position())
                relative_end = min(len(text), pos + length - self.currentBlock().position())
                self.setFormat(relative_start, relative_end - relative_start, fmt)

    def set_highlight_format(self, format):
        self.highlight_format = format
        self.highlight_range = None
        self.additional_highlights = []

    def set_highlight_range(self, start, length):
        self.highlight_range = (start, length)

    def add_additional_highlights(self, ranges_and_formats):
        self.additional_highlights.extend([(pos, length, fmt) for pos, length in ranges_and_formats for fmt in [fmt]])

class TextTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.file_content = b""
        self.current_encoding = "UTF-8"

        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel(self.tr("Encoding:")))
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(SUPPORTED_ENCODINGS)
        self.encoding_combo.setCurrentText("UTF-8")
        self.encoding_combo.currentTextChanged.connect(self._redecode_text)
        control_layout.addWidget(self.encoding_combo)

        control_layout.addStretch(1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("Search text..."))
        self.search_input.returnPressed.connect(self._perform_search)
        self.search_input.textChanged.connect(self._clear_search_highlight)
        control_layout.addWidget(self.search_input)

        self.search_count_label = QLabel(self.tr("Matches: 0"))
        control_layout.addWidget(self.search_count_label)

        self.prev_match_button = QPushButton(self.tr("Previous"))
        self.prev_match_button.clicked.connect(self._find_prev_match)
        control_layout.addWidget(self.prev_match_button)

        self.next_match_button = QPushButton(self.tr("Next"))
        self.next_match_button.clicked.connect(self._find_next_match)
        control_layout.addWidget(self.next_match_button)

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
        self.matches = []
        self.current_match_index = -1

    def _handle_contents_change(self, position, charsRemoved, charsAdded):
        self.line_number_area.update_width()
        self.line_number_area.update()

    def set_file_content(self, raw_bytes, encoding_hint=None, is_large=False):
        self.file_content = raw_bytes
        self.is_large_file = is_large
        if is_large:
            self.text_editor.setPlainText(self.tr(f"File too large for full display. Showing first {MAX_TEXT_PREVIEW_LINES} lines.\n"))
            self.text_editor.append(self.tr("--- Preview Mode ---"))
            try:
                decoded_text = self.file_content.decode(encoding_hint or "utf-8", errors='replace')
                lines = decoded_text.splitlines()
                self.text_editor.append("\n".join(lines[:MAX_TEXT_PREVIEW_LINES]))
            except Exception as e:
                self.text_editor.append(self.tr(f"Could not decode preview with {encoding_hint}: {e}"))
                self.text_editor.append(self.tr("Attempting with UTF-8..."))
                try:
                    self.text_editor.append(self.file_content.decode("utf-8", errors='replace'))
                except Exception as e:
                    self.text_editor.append(self.tr(f"Could not decode with UTF-8: {e}"))
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
            self._clear_search_highlight()
        except LookupError:
            self.text_editor.setPlainText(self.tr(f"Error: Encoding '{encoding}' not supported by Python. Please choose another."))
            self._clear_search_highlight()
        except Exception as e:
            self.text_editor.setPlainText(self.tr(f"Error decoding with '{encoding}': {e}\n\nAttempting with UTF-8 (replace errors)..."))
            try:
                self.text_editor.setPlainText(self.file_content.decode("utf-8", errors='replace'))
            except Exception as e_utf8:
                self.text_editor.setPlainText(self.tr(f"Critical Error: Could not decode with any fallback: {e_utf8}"))
            self._clear_search_highlight()

    def _perform_search(self):
        query = self.search_input.text()
        if not query:
            self._clear_search_highlight()
            return

        self.matches = []
        document = self.text_editor.document()
        cursor = QTextCursor(document)
        format = QTextCharFormat()
        format.setBackground(QColor("yellow"))
        format.setForeground(QColor("black"))

        self.highlighter.set_highlight_format(QTextCharFormat())
        self.highlighter.rehighlight()

        cursor.beginEditBlock()
        while not cursor.isNull() and not cursor.atEnd():
            cursor = document.find(query, cursor, QTextDocument.FindCaseSensitively)
            if not cursor.isNull():
                self.matches.append(cursor.selectionStart())
        cursor.endEditBlock()

        self.search_count_label.setText(self.tr(f"Matches: {len(self.matches)}"))

        if self.matches:
            self.current_match_index = 0
            self._highlight_current_match()
            self._scroll_to_match(self.matches[0])
        else:
            self.current_match_index = -1

    def _clear_search_highlight(self):
        self.highlighter.set_highlight_format(QTextCharFormat())
        self.highlighter.rehighlight()
        self.matches = []
        self.current_match_index = -1
        self.search_count_label.setText(self.tr("Matches: 0"))

    def _highlight_current_match(self):
        if not self.matches or self.current_match_index == -1:
            return

        self.highlighter.set_highlight_format(QTextCharFormat())
        self.highlighter.rehighlight()

        current_pos = self.matches[self.current_match_index]
        query_len = len(self.search_input.text())

        format = QTextCharFormat()
        format.setBackground(QColor("orange"))
        format.setForeground(QColor("black"))

        self.highlighter.set_highlight_format(format)
        self.highlighter.set_highlight_range(current_pos, query_len)
        self.highlighter.rehighlight()

        other_format = QTextCharFormat()
        other_format.setBackground(QColor("yellow"))
        other_format.setForeground(QColor("black"))
        self.highlighter.add_additional_highlights(
            [(pos, query_len) for i, pos in enumerate(self.matches) if i != self.current_match_index],
            other_format
        )
        self.highlighter.rehighlight()

    def _scroll_to_match(self, position):
        cursor = QTextCursor(self.text_editor.document())
        cursor.setPosition(position)
        self.text_editor.setTextCursor(cursor)
        self.text_editor.ensureCursorVisible()

    def _find_prev_match(self):
        if not self.matches:
            return
        self.current_match_index = (self.current_match_index - 1) % len(self.matches)
        self._highlight_current_match()
        self._scroll_to_match(self.matches[self.current_match_index])

    def _find_next_match(self):
        if not self.matches:
            return
        self.current_match_index = (self.current_match_index + 1) % len(self.matches)
        self._highlight_current_match()
        self._scroll_to_match(self.matches[self.current_match_index])

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
        # Ensure editor.document() is not None before calling blockCount()
        if self.editor.document():
            return QSize(self.editor.fontMetrics().horizontalAdvance(str(self.editor.document().blockCount())) + 10, 0)
        return QSize(50, 0) # Default size if document is not ready

    @Slot()
    def _on_block_count_changed(self):
        """Slot to handle blockCountChanged signal and trigger update_width."""
        self.update_width()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor(240, 240, 240))

        # Ensure editor and its document are valid before proceeding
        if not self.editor or not self.editor.document():
            painter.end()
            return

        # Corrected: firstVisibleBlock is a method of QTextEdit, not QTextDocument
        block = self.editor.firstVisibleBlock()
        
        # Ensure the block is valid before proceeding with its properties
        if not block.isValid():
            painter.end()
            return

        block_number = block.blockNumber()
        top = int(self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).top())
        bottom = top + int(self.editor.blockBoundingRect(block).height())

        # Corrected: Get current line from editor's cursor directly
        current_line_number = self.editor.textCursor().blockNumber() + 1 

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor(120, 120, 120))
                if block_number + 1 == current_line_number:
                    painter.setPen(QColor("blue"))
                    painter.setFont(QFont(painter.font().family(), painter.font().pointSize(), QFont.Bold))

                painter.drawText(0, top, self.width() - 5, self.editor.fontMetrics().height(),
                                 Qt.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + int(self.editor.blockBoundingRect(block).height())
            block_number += 1
        painter.end()

    def update_width(self):
        # Ensure editor.document() is not None before calling blockCount()
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

    def set_file_content(self, raw_bytes, is_large=False):
        self.file_content = raw_bytes
        self.is_large_file = is_large
        self._update_hex_display()

    def _update_hex_display(self):
        bytes_per_line = int(self.width_combo.currentText())
        show_non_printables = self.toggle_non_printables_checkbox.isChecked()
        hex_output = []
        data_to_display = self.file_content

        if self.is_large_file:
            data_to_display = self.file_content[:MAX_HEX_PREVIEW_BYTES]
            hex_output.append(self.tr(f"File too large for full hex dump. Showing first {MAX_HEX_PREVIEW_BYTES} bytes.\n"))
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

        self.structured_text_edit = QTextEdit()
        self.structured_text_edit.setReadOnly(True)
        self.structured_text_edit.setFont(QFont("Monospace", 10))
        self.structured_text_edit.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layout.addWidget(self.structured_text_edit)

    def set_file_content(self, raw_bytes, mime_type, encoding_hint="utf-8", is_large=False):
        self.structured_text_edit.clear()
        decoded_content = ""
        try:
            decoded_content = raw_bytes.decode(encoding_hint, errors='replace')
        except Exception:
            try:
                decoded_content = raw_bytes.decode("utf-8", errors='replace')
            except Exception as e:
                self.structured_text_edit.setPlainText(self.tr(f"Could not decode file to text: {e}"))
                return

        if is_large:
            self.structured_text_edit.append(self.tr(f"File too large for full structured display. Showing first {MAX_STRUCTURED_PREVIEW_LINES} lines/rows.\n"))
            self.structured_text_edit.append(self.tr("--- Preview Mode ---\n"))

        if 'json' in mime_type:
            try:
                data = json.loads(decoded_content)
                pretty_json = json.dumps(data, indent=4)
                if is_large:
                    lines = pretty_json.splitlines()
                    self.structured_text_edit.append("\n".join(lines[:MAX_STRUCTURED_PREVIEW_LINES]))
                else:
                    self.structured_text_edit.setPlainText(pretty_json)
            except json.JSONDecodeError as e:
                self.structured_text_edit.setPlainText(self.tr(f"Invalid JSON: {e}\n\nRaw content:\n{decoded_content[:1000]}..."))
            except Exception as e:
                self.structured_text_edit.setPlainText(self.tr(f"Error processing JSON: {e}\n\nRaw content:\n{decoded_content[:1000]}..."))
        elif 'xml' in mime_type:
            try:
                root = ET.fromstring(decoded_content)
                pretty_xml = ET.tostring(root, encoding='unicode', pretty_print=True)
                if is_large:
                    lines = pretty_xml.splitlines()
                    self.structured_text_edit.append("\n".join(lines[:MAX_STRUCTURED_PREVIEW_LINES]))
                else:
                    self.structured_text_edit.setPlainText(pretty_xml)
            except ET.ParseError as e:
                self.structured_text_edit.setPlainText(self.tr(f"Invalid XML: {e}\n\nRaw content:\n{decoded_content[:1000]}..."))
            except Exception as e:
                self.structured_text_edit.setPlainText(self.tr(f"Error processing XML: {e}\n\nRaw content:\n{decoded_content[:1000]}..."))
        elif 'csv' in mime_type or 'text/plain' in mime_type:
            try:
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(decoded_content[:1024])
                reader = csv.reader(io.StringIO(decoded_content), dialect)
                data = list(reader)

                table_output = []
                if is_large:
                    data = data[:MAX_STRUCTURED_PREVIEW_LINES]
                for row in data:
                    table_output.append(", ".join(row))
                self.structured_text_edit.setPlainText(self.tr(f"Detected delimiter: '{dialect.delimiter}'\n\n") + "\n".join(table_output))

            except csv.Error as e:
                self.structured_text_edit.setPlainText(self.tr(f"Could not parse as CSV. Trying to display as plain text.\nError: {e}\n\nRaw content:\n{decoded_content[:1000]}..."))
                self.structured_text_edit.setPlainText(decoded_content)
            except Exception as e:
                self.structured_text_edit.setPlainText(self.tr(f"Error processing CSV: {e}\n\nRaw content:\n{decoded_content[:1000]}..."))
        else:
            self.structured_text_edit.setPlainText(self.tr("Unsupported structured format or not detected. Displaying raw text.\n\n") + decoded_content)
        self.structured_text_edit.verticalScrollBar().setValue(0)

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
            <li><b>Text:</b> View text content, change encoding, search and highlight.</li>
            <li><b>Hex:</b> Raw hexadecimal and ASCII dump.</li>
            <li><b>Structured:</b> Pretty-prints JSON, XML, CSV.</li>
            <li><b>Image Metadata:</b> (If image) EXIF and GPS data.</li>
            <li><b>Base64 View:</b> Encodes file content to Base64.</li>
            <li><b>Entropy:</b> Displays Shannon entropy.</li>
            <li><b>Byte Histogram:</b> Visualizes byte frequency.</li>
        </ul>

        <h4>Keyboard Shortcuts:</h4>
        <ul>
            <li><b>Ctrl+O:</b> Open File</li>
            <li><b>Ctrl+R:</b> Reload Current File</li>
            <li><b>Ctrl+E:</b> Export Analysis</li>
            <li><b>Ctrl+H:</b> Show Help</li>
            <li><b>Ctrl+T:</b> Toggle Theme</li>
            <li><b>Ctrl+W:</b> Close Tab</li>
        </ul>

        <h4>File Watcher:</h4>
        <p>The application automatically reloads the file if it detects changes on disk.</p>
        """)
        self.text_browser = QTextBrowser() # Changed from QTextEdit to QTextBrowser
        self.text_browser.setHtml(help_text)
        self.text_browser.setReadOnly(True)
        self.text_browser.setOpenExternalLinks(True)
        self.layout.addWidget(self.text_browser)

        ok_button = QPushButton(self.tr("OK"))
        ok_button.clicked.connect(self.accept)
        self.layout.addWidget(ok_button)

class InfoscavaMainWindow(QMainWindow):
    def __init__(self, initial_filepath=None):
        super().__init__()
        self.setWindowTitle(self.tr("Infoscava - Universal File Analyzer"))
        # Set the window icon to icon.jpg from the same directory
        self.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), "icon.jpg")))

        self.current_filepath = None
        self.file_content_bytes = b""
        self.file_metadata = {}
        # Removed QThreadPool as we are now using QThread directly
        self.analysis_thread = None # Keep a reference to the thread
        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.fileChanged.connect(self._on_file_changed)

        self._setup_ui()
        self._setup_menu_bar()
        self._setup_status_bar()
        self._setup_drag_and_drop()
        self._load_theme_settings() # Load theme settings at startup

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

        # Removed the redundant file_path_label
        # self.file_path_label = QLabel(self.tr("No file loaded."))
        # self.main_layout.addWidget(self.file_path_label)

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

        help_menu = menu_bar.addMenu(self.tr("&Help"))
        about_action = QAction(self.tr("&About Infoscava"), self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)

        help_dialog_action = QAction(self.tr("&Help..."), self)
        help_dialog_action.setShortcut(QKeySequence("Ctrl+H"))
        help_dialog_action.triggered.connect(self._show_help_dialog) # Corrected connection
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
        if os.path.commonprefix([filepath, '/proc']) == '/proc' or os.path.commonprefix([filepath, '/dev']) == '/dev':
            QMessageBox.warning(self, self.tr("Invalid File Path"), self.tr(f"Loading files from '{filepath}' is not allowed for security reasons."))
            return

        self.current_filepath = filepath
        self.file_path_display.setText(filepath)
        self.status_bar.showMessage(self.tr(f"Loading file: {os.path.basename(filepath)}..."))
        self.progress_bar.setValue(0)
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

        self.analysis_thread = FileAnalyzerThread(filepath, self)
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

        is_large_file = results.get('size', 0) > MAX_FILE_SIZE_FOR_FULL_READ

        self.text_tab.set_file_content(self.file_content_bytes, results.get('encoding'), is_large_file)
        self.hex_tab.set_file_content(self.file_content_bytes, is_large_file)
        self.structured_tab.set_file_content(self.file_content_bytes, results.get('mime_type'), results.get('encoding'), is_large_file)
        self.base64_tab.set_file_content(self.file_content_bytes)
        self.entropy_tab.update_entropy(results.get('entropy'))
        self.byte_histogram_tab.plot_histogram(self.file_content_bytes)

        if PIL_AVAILABLE and results.get('mime_type', '').startswith('image/'):
            self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.image_metadata_tab), True)
            self.image_metadata_tab.update_image_data(self.current_filepath, results)
        else:
            self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.image_metadata_tab), False)

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
        self._clear_all_tabs_content()
        if self.file_watcher.files():
            self.file_watcher.removePaths(self.file_watcher.files())

    def _clear_all_tabs_content(self):
        self.metadata_tab.update_metadata({})
        self.text_tab.set_file_content(b"")
        self.hex_tab.set_file_content(b"")
        self.structured_tab.set_file_content(b"", "")
        self.image_metadata_tab.update_image_data("", {})
        self.base64_tab.set_file_content(b"")
        self.entropy_tab.update_entropy("N/A")
        self.byte_histogram_tab.plot_histogram(b"")
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.image_metadata_tab), False)

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
            QMessageBox.information(self, self.tr("File Changed"), self.tr("The loaded file has changed on disk. Reloading..."))
            self._load_file(self.current_filepath)

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
                        f.write(f"{key.replace('_', ' ').title()}: {value}\n")
                    f.write("\n--- Text Content (Preview) ---\n\n")
                    f.write(self.text_tab.text_editor.toPlainText()[:MAX_TEXT_PREVIEW_LINES * 2])
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

        if self.text_tab.text_editor.toPlainText():
            report_html += f"""
            <div class="section">
                <h2>{self.tr("Text Content (Preview)")}</h2>
                <pre>{self.text_tab.text_editor.toPlainText()[:MAX_TEXT_PREVIEW_LINES * 2]}</pre>
            </div>
            """

        if self.hex_tab.hex_editor.toPlainText():
            report_html += f"""
            <div class="section">
                <h2>{self.tr("Hexadecimal View (Preview)")}</h2>
                <pre>{self.hex_tab.hex_editor.toPlainText()[:MAX_HEX_PREVIEW_BYTES * 4]}</pre>
            </div>
            """

        if self.structured_tab.structured_text_edit.toPlainText():
            report_html += f"""
            <div class="section">
                <h2>{self.tr("Structured View (Preview)")}</h2>
                <pre>{self.structured_tab.structured_text_edit.toPlainText()[:MAX_STRUCTURED_PREVIEW_LINES * 2]}</pre>
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
                                  "<p>Version: 1.0.0</p>"
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
            print(f"Warning: Could not save theme preference: {e}")

    def _load_theme_preference(self):
        """Loads the last saved theme preference from a file."""
        try:
            if os.path.exists(THEME_SETTINGS_FILE):
                with open(THEME_SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                    return settings.get('theme', 'dark') # Default to 'dark' if not found
        except Exception as e:
            print(f"Warning: Could not load theme preference: {e}")
        return 'dark' # Default to dark theme if file doesn't exist or error occurs

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
        # Clear any specific stylesheet overrides for dark theme
        QApplication.instance().setStyleSheet("")
        self.status_bar.showMessage(self.tr("Switched to Dark Theme"), 3000)
        self._save_theme_preference('dark')

    def _set_light_theme(self):
        app = QApplication.instance()
        palette = app.palette()
        palette.setColor(QPalette.Window, QColor("#f0f0f0"))
        palette.setColor(QPalette.WindowText, QColor("#1e1e1e"))
        palette.setColor(QPalette.Base, QColor("#ffffff"))
        palette.setColor(QPalette.AlternateBase, QColor("#e0e0e0"))
        palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
        palette.setColor(QPalette.ToolTipText, QColor("#1e1e1e"))
        palette.setColor(QPalette.Text, QColor("#1e1e1e"))
        palette.setColor(QPalette.Button, QColor("#e0e0e0")) # Slightly darker button for contrast
        palette.setColor(QPalette.ButtonText, QColor("#1e1e1e"))
        palette.setColor(QPalette.BrightText, QColor("red"))
        palette.setColor(QPalette.Link, QColor("#0000ff"))
        palette.setColor(QPalette.Highlight, QColor("#aaddff"))
        palette.setColor(QPalette.HighlightedText, QColor("#1e1e1e"))
        app.setPalette(palette)
        
        # Apply comprehensive stylesheet overrides for light theme to ensure readability
        QApplication.instance().setStyleSheet("""
            QMainWindow, QWidget, QTabWidget, QSplitter {
                background-color: #f0f0f0;
                color: #1e1e1e;
            }
            QMenuBar {
                background-color: #e0e0e0; /* Lighter background for menu bar */
                color: #1e1e1e; /* Dark text for menu bar */
            }
            QMenuBar::item {
                background-color: transparent;
                color: #1e1e1e;
            }
            QMenuBar::item:selected {
                background-color: #c0c0c0; /* Highlight on hover */
            }
            QMenu {
                background-color: #f8f8f8; /* Lighter background for dropdown menus */
                color: #1e1e1e;
                border: 1px solid #d0d0d0;
            }
            QMenu::item:selected {
                background-color: #aaddff;
                color: #1e1e1e;
            }
            QTextEdit, QTextBrowser {
                background-color: #ffffff;
                color: #1e1e1e;
            }
            QComboBox {
                background-color: #ffffff;
                color: #1e1e1e;
                selection-background-color: #aaddff;
                selection-color: #1e1e1e;
            }
            QLineEdit {
                background-color: #ffffff;
                color: #1e1e1e;
            }
            QLabel {
                color: #1e1e1e;
            }
            QPushButton {
                background-color: #e0e0e0;
                color: #1e1e1e;
                border: 1px solid #c0c0c0;
                border-radius: 4px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QTreeView {
                background-color: #ffffff;
                color: #1e1e1e;
                alternate-background-color: #f5f5f5;
                border: 1px solid #d0d0d0;
            }
            QTreeView::item {
                color: #1e1e1e;
            }
            QTreeView::item:selected {
                background-color: #aaddff;
                color: #1e1e1e;
            }
            QTreeView::branch:selected {
                background-color: #aaddff; /* Ensure branches also highlight correctly */
            }
            QTreeView::branch:open:has-children {
                image: url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAKUlEQVQYlWNgYGD4TwW/oYlBTAz/g4GBYQYg/wPjEwMDAxMgBgBw7wJc20g/JAAAAABJRU5ErkJggg==); /* Example: small open triangle for light theme */
            }
            QTreeView::branch:closed:has-children {
                image: url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAJ0lEQVQYlWNgoD/gPxD+B8Q/wPjEwMDAxMgBgBw7wJc20g/JAAAAABJRU5ErkJggg==); /* Example: small closed triangle for light theme */
            }
            QStatusBar {
                background-color: #e0e0e0;
                color: #1e1e1e;
            }
            QProgressBar {
                background-color: #c0c0c0;
                color: #1e1e1e;
                border: 1px solid #a0a0a0;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #007bff;
                border-radius: 5px;
            }
        """)
        self.status_bar.showMessage(self.tr("Switched to Light Theme"), 3000)
        self._save_theme_preference('light')

    def _toggle_theme(self):
        app = QApplication.instance()
        # Determine current theme based on window background color
        # Using a reliable indicator like the main window's background color
        if app.palette().color(QPalette.Window).name() == "#1e1e1e":
            self._set_light_theme()
        else:
            self._set_dark_theme()

    def _load_theme_settings(self):
        """Loads the theme preference and applies it at startup."""
        preferred_theme = self._load_theme_preference()
        if preferred_theme == 'light':
            self._set_light_theme()
        else:
            self._set_dark_theme() # Default to dark if no preference or 'dark'

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
            print(f"Warning: Could not load translation for language '{args.lang}'")

    main_window = InfoscavaMainWindow(initial_filepath=args.file)
    main_window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
