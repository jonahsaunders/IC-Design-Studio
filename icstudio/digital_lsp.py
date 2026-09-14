"""Optional stdio LSP client; runs a user-selected SystemVerilog language server."""
import json
from pathlib import Path
import tempfile
from urllib.parse import unquote,urlparse

from PySide6.QtCore import QObject,QProcess,QTimer,Qt
from PySide6.QtGui import QKeySequence,QShortcut,QTextCursor
from PySide6.QtWidgets import QFileDialog,QInputDialog,QMenu


def frame(message):
    data=json.dumps(message,ensure_ascii=False).encode('utf-8')
    return b'Content-Length: '+str(len(data)).encode()+b'\r\n\r\n'+data


class Decoder:
    def __init__(self):self.buffer=b''

    def feed(self,data):
        self.buffer+=data;messages=[]
        if len(self.buffer)>16*1024**2:raise ValueError('Language server response exceeds 16 MiB.')
        while b'\r\n\r\n' in self.buffer:
            header,body=self.buffer.split(b'\r\n\r\n',1)
            fields=dict(line.lower().split(b':',1) for line in header.split(b'\r\n'))
            length=int(fields[b'content-length'])
            if not 0<=length<=16*1024**2:raise ValueError('Invalid language server message length.')
            if len(body)<length:break
            messages.append(json.loads(body[:length]));self.buffer=body[length:]
        return messages


class LanguageClient(QObject):
    def __init__(self,window):
        super().__init__(window);self.w=window;self.process=QProcess(self);self.decoder=Decoder()
        self.ready=False;self.pending={};self.serial=0;self.documents={};self.folder=None;self.uri=None
        self.process.readyReadStandardOutput.connect(self.receive)
        self.process.readyReadStandardError.connect(lambda:self.process.readAllStandardError())
        self.process.finished.connect(self.finished)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(350);self.timer.timeout.connect(self.sync)
        window.editor.textChanged.connect(lambda:self.timer.start() if self.ready else None)
        window.files.currentRowChanged.connect(lambda:self.timer.start() if self.ready else None)
        QShortcut(QKeySequence('Ctrl+Space'),window.editor,activated=lambda:window.attempt(self.complete))
        QShortcut(QKeySequence('F12'),window.editor,activated=lambda:window.attempt(self.definition))
        from .digital_workspace import table
        self.diagnostics=table(['Working source','Line','Severity','Diagnostic'])
        window.result_tabs.addTab(self.diagnostics,'Live diagnostics');window.shell.result_choice.addItem('Live diagnostics')
        self.diagnostics.cellDoubleClicked.connect(lambda r,c:self.open_location(self.diagnostics.item(r,0).data(Qt.UserRole)))

    def start(self):
        if not self.w.config:raise ValueError('Open an RTL cell first.')
        executable,_=QFileDialog.getOpenFileName(self.w,'Choose a SystemVerilog language server',self.w.studio.settings.value('digital/language_server',''))
        if not executable:return
        args,ok=QInputDialog.getText(self.w,'Language server','Arguments as a JSON array (for example ["--stdio"])',text=self.w.studio.settings.value('digital/language_server_args','[]'))
        if not ok:return
        argv=json.loads(args)
        if not isinstance(argv,list) or any(not isinstance(a,str) for a in argv):raise ValueError('Use a JSON array of argument strings.')
        self.stop();self.w.studio.settings.setValue('digital/language_server',executable);self.w.studio.settings.setValue('digital/language_server_args',args)
        root=Path(self.w.studio.jobs_dir)/self.w.project_id/'language';root.mkdir(parents=True,exist_ok=True)
        self.folder=tempfile.TemporaryDirectory(prefix='session-',dir=root);self.root=Path(self.folder.name).resolve();self.cell=self.w.cell_id
        self.w.sync_file()
        from .digital_flow import stage_sources
        stage_sources(self.w.config,self.root)
        self.process.setWorkingDirectory(str(self.root));self.process.start(executable,argv)
        if not self.process.waitForStarted(3000):raise ValueError(self.process.errorString())
        self.request('initialize',{'processId':None,'rootUri':self.root.as_uri(),
            'workspaceFolders':[{'uri':self.root.as_uri(),'name':self.w.config['top']}],
            'capabilities':{'general':{'positionEncodings':['utf-16']},'textDocument':{'completion':{'completionItem':{'snippetSupport':False}},'synchronization':{'dynamicRegistration':False}}}},self.initialized)
        self.w.message.setText('Starting language server…')

    def send(self,message):self.process.write(frame({'jsonrpc':'2.0',**message}))

    def request(self,method,params,callback):
        if self.process.state()!=QProcess.Running:raise ValueError('Start a language server from More → Language server.')
        self.serial+=1;self.pending[self.serial]=callback;self.send({'id':self.serial,'method':method,'params':params})

    def initialized(self,result):
        if result.get('capabilities',{}).get('positionEncoding','utf-16')!='utf-16':
            self.stop();raise ValueError('The language server must support UTF-16 positions.')
        sync=result.get('capabilities',{}).get('textDocumentSync',0)
        self.sync_kind=sync.get('change',0) if isinstance(sync,dict) else sync
        self.send({'method':'initialized','params':{}});self.ready=True;self.sync();self.w.message.setText('Language server ready · Ctrl+Space complete · F12 definition')

    def sync(self):
        if not self.ready:return
        if self.cell!=self.w.cell_id:self.stop();return
        self.w.sync_file();self.uri=None
        for source in self.w.config['files']:
            path=self.root/source['path'];path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source['text'])
            if source['role'] not in ('rtl','include','testbench'):continue
            uri=path.as_uri();old=self.documents.get(uri)
            if old is None:
                self.send({'method':'textDocument/didOpen','params':{'textDocument':{'uri':uri,'languageId':'systemverilog','version':1,'text':source['text']}}});self.documents[uri]=(1,source['text'])
            elif old[1]!=source['text']:
                change={'text':source['text']}
                if self.sync_kind==2:
                    lines=old[1].split('\n');change['range']={'start':{'line':0,'character':0},'end':{'line':len(lines)-1,'character':len(lines[-1].encode('utf-16-le'))//2}}
                self.send({'method':'textDocument/didChange','params':{'textDocument':{'uri':uri,'version':old[0]+1},'contentChanges':[change]}});self.documents[uri]=(old[0]+1,source['text'])
            if source['path']==self.w.files.currentItem().text():self.uri=uri

    def params(self):
        self.sync()
        if not self.uri:raise ValueError('Select an RTL source file.')
        cursor=self.w.editor.textCursor()
        return {'textDocument':{'uri':self.uri},'position':{'line':cursor.blockNumber(),'character':cursor.positionInBlock()}}

    def definition(self):
        def show(value):
            locations=value if isinstance(value,list) else [value] if value else []
            if not locations:self.w.message.setText('No definition returned.');return
            menu=QMenu(self.w)
            for loc in locations:
                target={'uri':loc.get('uri',loc.get('targetUri')),'range':loc.get('range',loc.get('targetSelectionRange'))}
                menu.addAction(target['uri'].rsplit('/',1)[-1]+':'+str(target['range']['start']['line']+1)).triggered.connect(lambda checked=False,t=target:self.open_location(t))
            if len(locations)==1:self.open_location(target)
            else:menu.exec(self.w.editor.mapToGlobal(self.w.editor.cursorRect().bottomRight()))
        self.request('textDocument/definition',self.params(),show)

    def complete(self):
        params=self.params();revision=self.w.editor.document().revision();uri=self.uri
        def show(value):
            if revision!=self.w.editor.document().revision() or uri!=self.uri:return
            items=value.get('items',[]) if isinstance(value,dict) else value or [];menu=QMenu(self.w)
            for item in items[:100]:
                def insert(item=item):
                    if revision!=self.w.editor.document().revision() or uri!=self.uri:return
                    edit=item.get('textEdit');cursor=self.w.editor.textCursor()
                    if edit:
                        span=edit.get('range',edit.get('replace'));start,end=span['start'],span['end']
                        cursor.setPosition(self.w.editor.document().findBlockByNumber(start['line']).position()+start['character'])
                        cursor.setPosition(self.w.editor.document().findBlockByNumber(end['line']).position()+end['character'],QTextCursor.KeepAnchor)
                    else:cursor.select(QTextCursor.WordUnderCursor)
                    cursor.insertText(edit['newText'] if edit else item.get('insertText',item['label']))
                menu.addAction(item['label']).triggered.connect(lambda checked=False,fn=insert:fn())
            if items:menu.exec(self.w.editor.mapToGlobal(self.w.editor.cursorRect().bottomRight()))
            else:self.w.message.setText('No completions returned.')
        self.request('textDocument/completion',params,show)

    def open_location(self,location):
        if not self.folder:return
        uri=location['uri'];path=Path(unquote(urlparse(uri).path)).resolve()
        if not path.is_relative_to(self.root):self.w.message.setText('Definition is outside the captured source workspace: '+str(path));return
        relative=path.relative_to(self.root).as_posix();index=next((i for i,f in enumerate(self.w.config['files']) if f['path']==relative),None)
        if index is None:return
        self.w.files.setCurrentRow(index);self.w.shell.source_mode.setCurrentIndex(0);self.w.shell.reveal_source()
        block=self.w.editor.document().findBlockByNumber(location['range']['start']['line'])
        if block.isValid():self.w.editor.setTextCursor(QTextCursor(block));self.w.editor.centerCursor()

    def receive(self):
        try:
            for message in self.decoder.feed(bytes(self.process.readAllStandardOutput())):
                if 'method' in message and 'id' in message:
                    self.send({'id':message['id'],'error':{'code':-32601,'message':'Client method unavailable'}})
                elif message.get('method')=='textDocument/publishDiagnostics':
                    params=message['params'];rows=[]
                    if params['uri'] not in self.documents:continue
                    if params.get('version',self.documents[params['uri']][0])!=self.documents[params['uri']][0]:continue
                    for d in params['diagnostics']:
                        rows.append({**d,'uri':params['uri'],'path':Path(unquote(urlparse(params['uri']).path)).name,'line':d['range']['start']['line']+1})
                    from .digital_workspace import fill
                    fill(self.diagnostics,rows,['path','line','severity','message'])
                elif message.get('id') in self.pending:
                    callback=self.pending.pop(message['id'])
                    if 'error' in message:self.w.message.setText(str(message['error'].get('message','Language server error')))
                    else:callback(message.get('result'))
        except Exception as exc:self.w.message.setText('Language server: '+str(exc))

    def finished(self,*_):self.ready=False

    def stop(self):
        self.ready=False;self.timer.stop()
        if self.process.state()!=QProcess.NotRunning:self.send({'method':'exit'});self.process.terminate();self.process.waitForFinished(1000)
        if self.process.state()!=QProcess.NotRunning:self.process.kill();self.process.waitForFinished(1000)
        if self.folder:self.folder.cleanup();self.folder=None
        self.pending={};self.documents={};self.uri=None;self.decoder=Decoder()
