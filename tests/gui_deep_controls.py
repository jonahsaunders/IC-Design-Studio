"""Real submissions and destinations missed by a cancel-only menu sweep."""
import argparse,ast,json,os,re,sys,time,traceback
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote,urlsplit
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=ROOT/'build/deep-controls')
    out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ.update(XDG_CONFIG_HOME=str(out/'config'),XDG_DATA_HOME=str(out/'data'))
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices,QTextDocument
    from PySide6.QtWidgets import QApplication,QTextBrowser,QPushButton,QFileDialog,QLabel
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import example,digest
    from icstudio.project_templates import defaults
    from icstudio.help_navigation import heading_slug
    from icstudio.osdi import verified
    app=QApplication([]);w=Studio(recover=False);w.show();w.maybe_save=lambda:True
    errors=[];w.error=errors.append
    sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb))
    checks=[]
    def click(parent,text):
        button=next(b for b in parent.findChildren(QPushButton) if b.text().replace('&','')==text)
        assert button.isEnabled(),text
        button.click();app.processEvents()
    def wait(worker):
        deadline=time.monotonic()+30
        while worker.isRunning() and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert not worker.isRunning(),'Worker timeout'
        QTest.qWait(30)
    for ident,voltage in [('sky130A',1.8),('gf180mcuC',3.3),('gf180mcuD',3.3),('ihp-sg13g2',1.2)]:
        h=w.new_project();h.select_pdk(next(r['key'] for r in h.rows if r['id']==ident))
        h.template.setCurrentIndex(h.template.findData('inverter'))
        assert float(h.supply.text())==voltage,(ident,h.supply.text())
        from icstudio.project_hub import preview
        expected=defaults(preview(h.current_pdk()))
        assert (h.nmos.currentData(),h.pmos.currentData())==(expected['NMOS'],expected['PMOS'])
        h.supply.setText(str(voltage*.9));h.show_page('pdks');h.show_page('new');assert float(h.supply.text())==voltage*.9
        h.supply.setText('not a voltage');before=digest(w.project);h.create_button.click();wait(h.worker)
        assert h.isVisible() and digest(w.project)==before and h.state.text()
        h.supply.setText(str(voltage));h.create_button.click();wait(h.worker)
        assert not h.isVisible(),h.state.text()
        assert w.project['template']['supply']==voltage and w.project['template']['models']=={k:expected[k] for k in ('NMOS','PMOS')}
    checks.append('All four PDK revisions: core model/supply defaults, draft retention, invalid submission, actual install-and-create')
    w.set_project(example())
    w.live_session_widget.show();click(w.live_session_widget,'Check schematic')
    assert 'electrical findings' in w.check_note.text(),w.check_note.text()
    checks.append('Collaboration Check schematic runs electrical checks')
    w.runtime_dialog();d=w._runtime_dialog
    library=out/'custom model.osdi';library.write_bytes(b'Hash-only test fixture; never simulated')
    with patch.object(QFileDialog,'getOpenFileNames',return_value=([str(library)],'')):click(d,'Select libraries…')
    assert len(verified(w.project))==1
    click(d,'Verify files');assert any('hashes and platform match' in b.text() for b in d.findChildren(QLabel))
    library.write_bytes(b'changed');click(d,'Verify files');assert any('missing or changed' in b.text() for b in d.findChildren(QLabel))
    click(d,'Clear');assert not w.project.get('simulation_runtime')
    with patch.object(QFileDialog,'getExistingDirectory',return_value=str(out)):click(d,'Load folder…')
    assert len(verified(w.project))==1
    click(d,'Clear');d.close()
    checks.append('Runtime Select libraries, Load folder, Verify files and Clear; changed libraries rejected')
    from tests.test_native_migration import divider
    from icstudio.native_migration import review_path
    from icstudio.xschem_compat import review_project
    from icstudio.osdi import configure
    source=divider(out/'program-source',include=True)
    for mode,p in [('generic',example()),('native',review_path(source)['candidate']),('capture',review_project(source)['candidate'])]:
        p['simulation_runtime']={'osdi':configure([library])};w.set_project(p)
        folder=out/('spice-'+mode);folder.mkdir();path=folder/'circuit.cir'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(path),'')),patch.object(QFileDialog,'getExistingDirectory',return_value=str(folder)):
            w.export_spice()
        if mode!='generic':path=folder/(p['name']+'-spice')/'source.cir'
        assert 'pre_osdi runtime-osdi/model-0.osdi' in path.read_text(encoding='utf-8')
        assert (path.parent/'runtime-osdi/model-0.osdi').read_bytes()==library.read_bytes()
    w.set_project(example())
    checks.append('Generic, native and captured SPICE export controls retain explicitly configured model libraries')
    guides=set()
    for source in (ROOT/'icstudio').glob('*.py'):
        for node in ast.walk(ast.parse(source.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='open_editor_doc' and node.args and isinstance(node.args[0],ast.Constant):guides.add(node.args[0].value)
    for guide in sorted(guides):
        assert (ROOT/'docs'/guide).is_file(),guide
        w.open_editor_doc(guide)
        if guide.startswith('CAPABILITY_MATRIX'):w._compatibility_dialog.close();continue
        d=w._document_dialog;b=d.findChild(QTextBrowser)
        assert b.toPlainText().strip() and b.source().isLocalFile(),guide
        d.close()
    w.open_editor_doc('GETTING_STARTED.md');d=w._document_dialog;b=d.findChild(QTextBrowser)
    b.anchorClicked.emit(QUrl('PDK_GUIDE.md'));assert b.source().toLocalFile().endswith('PDK_GUIDE.md') and 'Open PDK setup' in b.toPlainText()
    b.anchorClicked.emit(QUrl('REFERENCE_COMPATIBILITY_REPAIRS.md#linux-and-windows-physical-verification'))
    QTest.qWait(30)
    assert 'Linux and Windows physical verification' in b.toPlainText()
    assert b.verticalScrollBar().value()>0,'Heading anchor did not scroll'
    click(d,'Back');assert b.source().toLocalFile().endswith('PDK_GUIDE.md')
    click(d,'Back');assert b.source().toLocalFile().endswith('GETTING_STARTED.md')
    click(d,'Forward');assert b.source().toLocalFile().endswith('PDK_GUIDE.md')
    b.anchorClicked.emit(QUrl('../SIMULATION_SETUP.md'));assert b.toPlainText().strip() and b.source().toLocalFile().endswith('SIMULATION_SETUP.md')
    with patch.object(QDesktopServices,'openUrl',return_value=True) as opened:
        b.anchorClicked.emit(QUrl('https://github.com/jonahsaunders/IC-Design-Studio/releases'))
        assert opened.call_args.args[0].toString().endswith('/releases')
        b.anchorClicked.emit(QUrl('README.md#start-in-three-steps'))
        assert '/blob/' in opened.call_args.args[0].toString() and opened.call_args.args[0].fragment()=='start-in-three-steps'
    d.grab().save(str(out/'help-navigation.png'));d.close()
    checks.append(str(len(guides))+' help entry points, relative documents, parent paths, heading anchors, Back/Forward and external URL dispatch')
    # Match rendered heading text, including inline formatting, and explicit HTML IDs.
    anchor_cache={};links=0;failures=[]
    documents=[ROOT/n for n in ('README.md','CONTRIBUTING.md','SIMULATION_SETUP.md','THIRD_PARTY_NOTICES.md')]
    documents += sorted((ROOT/'docs').rglob('*.md'))+sorted((ROOT/'examples').rglob('*.md'))
    for path in documents:
        text=path.read_text(encoding='utf-8')
        for ref in re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)',text)+re.findall(r'(?:href|src)="([^"]+)"',text):
            url=urlsplit(ref)
            if url.scheme or url.netloc:continue
            target=(path.parent/unquote(url.path)).resolve() if url.path else path
            links+=1
            if not target.exists():failures.append(str(path.relative_to(ROOT))+': '+ref);continue
            if not url.fragment or target.suffix.lower()!='.md':continue
            if target not in anchor_cache:
                source=target.read_text(encoding='utf-8');doc=QTextDocument();doc.setMarkdown(source,QTextDocument.MarkdownDialectGitHub|QTextDocument.MarkdownNoHTML);block=doc.begin();seen={};anchors=set(re.findall(r'(?:id|name)="([^"]+)"',source))
                while block.isValid():
                    if block.blockFormat().headingLevel():
                        base=heading_slug(block.text());count=seen.get(base,0);seen[base]=count+1;anchors.add(base+('-'+str(count) if count else ''))
                    block=block.next()
                anchor_cache[target]=anchors
            if unquote(url.fragment) not in anchor_cache[target]:failures.append(str(path.relative_to(ROOT))+': '+ref)
    (out/'links.json').write_text(json.dumps(dict(documents=len(documents),local_links=links,failures=failures),indent=2))
    assert not failures,failures
    checks.append(str(links)+' local document links, including heading fragments')
    assert not errors,errors
    w.saved_hash=digest(w.project);w.close();app.processEvents()
    (out/'checks.json').write_text(json.dumps(dict(status='passed',checks=checks),indent=2));print(json.dumps(checks))

if __name__=='__main__':main()
