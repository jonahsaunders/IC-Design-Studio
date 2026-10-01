"""Stable document URLs and heading navigation for the offline help browser."""
import re


def heading_slug(text):
    return re.sub(r'[^\w\s-]', '', text.lower()).replace(' ', '-')


def install_heading_anchors(browser):
    from PySide6.QtGui import QTextCursor,QTextCharFormat
    # Qt's Markdown reader renders headings without creating HTML anchor names.
    counts={};block=browser.document().begin()
    while block.isValid():
        if block.blockFormat().headingLevel() and block.text():
            base=heading_slug(block.text());count=counts.get(base,0);counts[base]=count+1
            cursor=QTextCursor(block);cursor.movePosition(QTextCursor.NextCharacter,QTextCursor.KeepAnchor)
            fmt=QTextCharFormat();fmt.setAnchor(True);fmt.setAnchorNames([base+('-'+str(count) if count else '')]);cursor.mergeCharFormat(fmt)
        block=block.next()
    if browser.source().hasFragment():browser.scrollToAnchor(browser.source().fragment())


def connect_navigation(browser,dialog):
    from pathlib import Path
    import sys
    from PySide6.QtCore import QTimer,QUrl
    from PySide6.QtGui import QDesktopServices
    browser.setOpenLinks(False)
    def navigate(url):
        target=browser.source().resolved(url)
        path=Path(target.toLocalFile())
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
        if target.isLocalFile() and path==root/'README.md':
            # The landing page contains HTML picture/table/details elements
            # that Qt's Markdown reader drops, including their surrounding text.
            # Open the matching source revision in the user's web browser.
            from .build_identity import identity
            revision=identity()['commit']
            if not re.fullmatch('[0-9a-f]{40}',revision):revision='experimental'
            web=QUrl('https://github.com/jonahsaunders/IC-Design-Studio/blob/'+revision+'/README.md');web.setFragment(target.fragment())
            QDesktopServices.openUrl(web)
        elif target.isLocalFile() and path.suffix.lower()=='.md':browser.setSource(target)
        else:QDesktopServices.openUrl(target)
    def changed(url):
        dialog.setWindowTitle(Path(url.path()).stem.replace('_',' '))
        install_heading_anchors(browser)
        # setSource restores scroll state after sourceChanged; navigate after
        # that restoration and after Qt lays out the newly rendered Markdown.
        if url.hasFragment():QTimer.singleShot(0,lambda:browser.scrollToAnchor(url.fragment()) if browser.source()==url else None)
    browser.anchorClicked.connect(navigate);browser.sourceChanged.connect(changed)
