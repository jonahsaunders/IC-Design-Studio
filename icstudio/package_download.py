"""Download a desktop release into a user-selected file, including split Linux packages."""
import hashlib
import json
from pathlib import Path
import re
import sys

from PySide6.QtCore import QIODevice, QSaveFile, QStandardPaths, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QVBoxLayout)

from . import __version__
from .transfer_progress import ProgressRate, size

REPO = 'jonahsaunders/IC-Design-Studio'
RELEASE = f'https://github.com/{REPO}/releases'
METADATA = f'https://api.github.com/repos/{REPO}/releases/tags/v{__version__}'


def packages(release, windows):
    prefix = 'IC-Design-Studio-' + __version__ + '-'
    choices = {}
    parts = {}
    for asset in release.get('assets', []):
        name = asset['name']
        if not name.startswith(prefix) or not name.isascii():
            continue
        suffix = name[len(prefix):]
        url = RELEASE + '/download/v' + __version__ + '/' + name
        if asset.get('browser_download_url') != url:
            continue
        if windows and suffix in ('Windows-x64-Setup.exe', 'Windows-x64-Portable.zip'):
            choices[name] = [asset]
        elif not windows and suffix == 'Linux-x86_64.tar.gz':
            choices[name] = [asset]
        elif not windows and re.fullmatch(r'Linux-x86_64\.tar\.gz\.part[0-9]{3}', suffix):
            parts[int(suffix[-3:])] = asset
    if len(parts) >= 2 and sorted(parts) == list(range(1, max(parts) + 1)):
        choices.setdefault(prefix+'Linux-x86_64.tar.gz', [parts[i] for i in sorted(parts)])
    return choices


class DownloadDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('Download desktop tools')
        self.resize(520, 180)
        self.network = QNetworkAccessManager(self)
        self.reply = self.output = None
        self.options = {}
        layout = QVBoxLayout(self)
        self.choice = QComboBox()
        self.choice.setAccessibleName('Desktop package')
        layout.addWidget(self.choice)
        self.bar = QProgressBar()
        self.bar.setAccessibleName('Package download progress')
        layout.addWidget(self.bar)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        layout.addLayout(row)
        releases = QPushButton('Release page')
        releases.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(RELEASE)))
        row.addWidget(releases)
        row.addStretch()
        self.action = QPushButton('Download…')
        self.action.clicked.connect(self.start)
        row.addWidget(self.action)
        self.dismiss = QPushButton('Close')
        self.dismiss.clicked.connect(self.reject)
        row.addWidget(self.dismiss)
        self.timer = QTimer(self, interval=500)
        self.timer.timeout.connect(self.update_progress)
        self.lookup()

    def request(self, url):
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(60000)
        request.setRawHeader(b'User-Agent', b'IC-Design-Studio')
        self.reply = self.network.get(request)
        self.reply.setReadBufferSize(1024 * 1024)
        return self.reply

    def lookup(self):
        self.action.setEnabled(False)
        self.bar.setRange(0, 0)
        self.status.setText('Finding desktop packages…')
        self.archive_digest = None
        self.read_json(METADATA, self.found_release)

    def read_json(self, url, callback, digest=None):
        self.json_callback = callback
        self.json_digest = digest
        self.json_data = bytearray()
        reply = self.request(url)
        reply.readyRead.connect(self.read_metadata)
        reply.finished.connect(self.finish_metadata)

    def read_metadata(self):
        reply = self.sender()
        if self.reply is reply:
            self.json_data.extend(bytes(reply.readAll()))
            if len(self.json_data) > 4 * 1024 * 1024:
                self.options = {}
                self.fail('The release information is too large.')

    def finish_metadata(self):
        reply = self.sender()
        if self.reply is not reply:
            return
        self.reply = None
        reply.deleteLater()
        callback, self.json_callback = self.json_callback, None
        try:
            if reply.error() != QNetworkReply.NoError:
                raise ValueError(reply.errorString())
            self.json_data.extend(bytes(reply.readAll()))
            if self.json_digest and 'sha256:'+hashlib.sha256(self.json_data).hexdigest() != self.json_digest:
                raise ValueError('The release manifest checksum does not match.')
            callback(json.loads(self.json_data))
        except (ValueError, TypeError, KeyError) as exc:
            self.options = {}
            self.fail('Could not load the release. ' + str(exc))

    def found_release(self, release):
        if sys.platform not in ('win32','linux'):
            raise ValueError('Desktop packages are available for Windows x64 and Linux x86_64.')
        self.options = packages(release, sys.platform == 'win32')
        if not self.options:
            raise ValueError('No desktop package for this system in the release.')
        for name, assets in self.options.items():
            if len(assets) > 1:
                url = RELEASE+'/download/v'+__version__+'/'+name+'.parts.json'
                manifest = next((a for a in release['assets'] if a['browser_download_url']==url), None)
                if not manifest:
                    raise ValueError('The split archive manifest is missing.')
                self.read_json(url, self.check_manifest, manifest.get('digest'))
                return
        self.show_choices()

    def check_manifest(self, manifest):
        name, assets = next(iter(self.options.items()))
        parts = [dict(name=a['name'], bytes=a['size'], sha256=a['digest'].removeprefix('sha256:')) for a in assets]
        archive = manifest['archive']
        if (manifest['format']!='split-tar-gz' or manifest['schema']!=1 or manifest['parts']!=parts
                or archive['name']!=name or archive['bytes']!=sum(a['size'] for a in assets)
                or not re.fullmatch('[0-9a-f]{64}',archive['sha256'])):
            raise ValueError('The release archive and its parts do not match.')
        self.archive_digest = archive['sha256']
        self.show_choices()

    def show_choices(self):
        self.choice.clear()
        for name, assets in sorted(self.options.items(), key=lambda item: not item[0].endswith('.exe')):
            self.choice.addItem(name + '  (' + size(sum(a['size'] for a in assets)) + ')', name)
        self.status.setText('Choose a package and where to save it.')
        self.idle()

    def idle(self):
        self.timer.stop()
        self.action.setEnabled(True)
        self.action.setText('Download…' if self.options else 'Retry')
        self.choice.setEnabled(True)
        self.dismiss.setText('Close')
        self.bar.setRange(0, 100)

    def start(self):
        if self.reply:
            return
        if not self.options:
            self.lookup()
            return
        name = self.choice.currentData()
        folder = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        filename, _ = QFileDialog.getSaveFileName(self, 'Save desktop package', str(Path(folder) / name))
        if not filename:
            return
        self.output = QSaveFile(filename)
        if not self.output.open(QIODevice.WriteOnly):
            self.status.setText(self.output.errorString())
            self.output = None
            return
        self.assets = iter(self.options[name])
        self.total = sum(a['size'] for a in self.options[name])
        self.received = 0
        self.rate = ProgressRate()
        self.archive_hash = hashlib.sha256() if self.archive_digest else None
        self.choice.setEnabled(False)
        self.action.setEnabled(False)
        self.dismiss.setText('Cancel download')
        self.bar.setRange(0, 100 if self.total else 0)
        self.update_progress()
        self.timer.start()
        self.next_part()

    def update_progress(self):
        if self.output is None:
            return
        self.status.setText(self.rate.describe(self.received, self.total))
        if self.total:
            self.bar.setValue(min(99, self.received * 100 // self.total))

    def next_part(self):
        asset = next(self.assets, None)
        if asset is None:
            if self.archive_hash and self.archive_hash.hexdigest()!=self.archive_digest:
                self.fail('The assembled archive checksum does not match the release.')
                return
            if not self.output.commit():
                self.fail(self.output.errorString())
                return
            self.status.setText('Saved ' + self.output.fileName())
            self.output = None
            self.idle()
            self.bar.setValue(100)
            return
        self.asset = asset
        self.part_hash = hashlib.sha256()
        self.part_start = self.received
        reply = self.request(asset['browser_download_url'])
        reply.readyRead.connect(self.read_part)
        reply.finished.connect(self.finish_part)

    def read_part(self):
        if self.sender() is self.reply:
            self.write_part()

    def write_part(self):
        block = bytes(self.reply.readAll())
        if self.output.write(block) != len(block):
            self.fail(self.output.errorString())
            return
        self.part_hash.update(block)
        if self.archive_hash:self.archive_hash.update(block)
        self.received += len(block)

    def finish_part(self):
        reply = self.sender()
        if self.reply is not reply:
            return
        self.write_part()
        if self.reply is not reply:
            return
        self.reply = None
        reply.deleteLater()
        if reply.error() != QNetworkReply.NoError:
            self.fail(reply.errorString())
        elif self.received - self.part_start != self.asset['size']:
            self.fail('The package transfer was incomplete.')
        elif self.asset.get('digest') and self.asset['digest'] != 'sha256:' + self.part_hash.hexdigest():
            self.fail('The package checksum does not match the release.')
        else:
            self.next_part()

    def fail(self, reason):
        self.json_callback = None
        reply, self.reply = self.reply, None
        if reply is not None:
            reply.abort()
            reply.deleteLater()
        if self.output is not None:
            self.output.cancelWriting()
            self.output = None
        self.idle()
        self.bar.setValue(0)
        self.status.setText(reason)

    def reject(self):
        if self.reply is not None:
            downloading = self.output is not None
            if not downloading:self.options = {}
            self.fail('Download cancelled.')
            if downloading:
                return
        super().reject()


def show(parent):
    dialog = getattr(parent, '_package_download', None)
    if dialog is None:
        dialog = DownloadDialog(parent)
        parent._package_download = dialog
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
