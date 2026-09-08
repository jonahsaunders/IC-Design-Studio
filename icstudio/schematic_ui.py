"""Manual schematic editing, electrical transactions and keyboard commands."""
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QAction,QKeySequence,QShortcut
from PySide6.QtWidgets import QApplication,QLineEdit,QPlainTextEdit,QMenu,QLabel,QHBoxLayout,QWidget
from .model import clone,uid,digest,validate
from . import wiring


from .label_ui import NetLabelMixin
from . import net_labels

class SchematicMixin(NetLabelMixin):
    def make_ui(self):
        for cell in self.project['cells']:wiring.migrate(cell,self.project)
        super().make_ui()
        self.schematic.label_requested.connect(lambda anchor:self.guard(lambda:self.place_label(anchor)))
        self.schematic.wire_added.connect(lambda points:self.guard(lambda:self.place_wire(points)))
        self.schematic.wire_segment_moved.connect(lambda ident,index,x,y:self.guard(lambda:self.move_wire_segment(ident,index,x,y)))

    def set_project(self,project,path=None):
        if self.process:raise ValueError('Stop the active job before switching projects.')
        project=clone(project)
        for cell in project['cells']:wiring.migrate(cell,project)
        super().set_project(project,path)

    def commit(self,fn,label='Edit'):
        def transaction(p):
            if getattr(self,'_capture_raw_transaction',False):fn(p);return
            before={c['id']:clone(c) for c in p['cells']}
            fn(p)
            for cell in p['cells']:
                old=before.get(cell['id'])
                if old is None:wiring.migrate(cell,p);continue
                if 'wires' not in cell:continue
                oldids={d['id'] for d in old['devices']}
                for d in cell['devices']:
                    # Placed/duplicated devices start unconnected, including ground.
                    if d['id'] not in oldids:d['net_labels']={}
                    else:d['net_labels']={pin:name for pin,name in d.get('net_labels',{}).items() if pin in d['nets']}
                moved={w['id'] for w in cell['wires'] if any(v['id']==w['id'] and v['points']!=w['points'] for v in old.get('wires',[]))}
                wiring.keep_connections(cell,wiring.pins(old,{'cells':list(before.values())}),p,moved)
                net_labels.reconcile(cell,old,p)
                wiring.rebuild(cell,p)
        return super().commit(transaction,label)

    def place_wire(self,points):
        result=[]
        def edit(p):
            cell=next(c for c in p['cells'] if c['id']==self.cid);result.extend(wiring.add_wire(cell,points,p))
        self.commit(edit,'Place wire')
        if result and result[0]:
            note='Wire placed · click to start another · Esc returns to Select'
            if result[1]:note='Connected net merged: '+', '.join(result[1])+' · Ctrl+Z to undo'
            self.canvas_message(note)

    def connect(self,a,ap,b,bp):
        # Compatibility command uses the same stored-path transaction.
        pos=wiring.pins(self.cell,self.project);start,end=pos[(a,ap)],pos[(b,bp)]
        self.place_wire(wiring.clean([start,[end[0],start[1]],end]))

    def move_wire_segment(self,ident,index,dx,dy):
        def edit(p):
            c=next(c for c in p['cells'] if c['id']==self.cid);w=next(w for w in c['wires'] if w['id']==ident)
            a,b=w['points'][index:index+2];shift=[0,dy] if a[1]==b[1] else [dx,0]
            contacts={tuple(pt) for pt in wiring.pins(c,p).values()}|{tuple(pt) for other in c['wires'] if other['id']!=ident for pt in other['points']}|{tuple(pt) for pt in c.get('junctions',[])}
            for label in c.get('labels',[]):
                anchor=label['anchor']
                if anchor['kind']=='wire' and anchor['id']==ident and wiring.on_segment(anchor['point'],a,b):anchor['point']=[anchor['point'][0]+shift[0],anchor['point'][1]+shift[1]]
            w['points']=wiring.segment_drag(w['points'],index,dx,dy)
            for point in contacts:
                if list(point) not in (a,b) and wiring.on_segment(point,a,b) and any(shift):
                    c['wires'].append({'id':uid(),'points':[list(point),[point[0]+shift[0],point[1]+shift[1]]]})
        self.commit(edit,'Move wire segment')

    def move(self,ids,x,y,mode):
        if mode!='schematic':return super().move(ids,x,y,mode)
        def edit(p):
            c=next(c for c in p['cells'] if c['id']==self.cid)
            for d in c['devices']:
                if d['id'] in ids:d['x']+=x;d['y']+=y
            for w in c.get('wires',[]):
                if w['id'] in ids:
                    w['points']=[[a+x,b+y] for a,b in w['points']]
                    for l in c.get('labels',[]):
                        a=l['anchor']
                        if a['kind']=='wire' and a['id']==w['id']:a['point']=[a['point'][0]+x,a['point'][1]+y]
            for l in c.get('labels',[]):
                if l['id'] in ids and not (l['anchor'].get('id') in ids):l['offset']=[l['offset'][0]+x,l['offset'][1]+y]
        self.guard(lambda:self.commit(edit,'Move selection'))

    def delete(self):
        if isinstance(QApplication.focusWidget(),(QLineEdit,QPlainTextEdit)):return
        if self.current_mode!='schematic':return super().delete()
        if not self.selection:return
        ids=set(self.selection)
        def edit(p):
            c=next(c for c in p['cells'] if c['id']==self.cid)
            c['labels']=[l for l in c.get('labels',[]) if l['id'] not in ids]
            c['devices']=[d for d in c['devices'] if d['id'] not in ids]
            if 'wires' in c:c['wires']=[w for w in c['wires'] if w['id'] not in ids]
            else:wiring.migrate(c,p)
            c['layout_pins']=[pin for pin in c.get('layout_pins',[]) if pin['device_id'] not in ids]
            for shape in c['shapes']:
                if shape.get('device_id') in ids:shape['device_id']=''
        self.commit(edit,'Delete selection');self.select([])

    def duplicate(self):
        if self.current_mode!='schematic':return super().duplicate()
        ids=set(self.selection);newids=[]
        if not ids:return
        def edit(p):
            c=next(c for c in p['cells'] if c['id']==self.cid);names={d['name'] for d in c['devices']}
            mapping={}
            for group in ('devices','wires','labels'):
                for item in list(c.get(group,[])):
                    if item['id'] not in ids:continue
                    new=clone(item);new['id']=uid();newids.append(new['id']);mapping[item['id']]=new['id']
                    if group=='devices':
                        name=new['name'];i=2
                        while name+'_'+str(i) in names:i+=1
                        new['name']=name+'_'+str(i);names.add(new['name']);new['net_labels']={};new['x']+=40;new['y']+=40
                    elif group=='labels':
                        a=new['anchor']
                        if a.get('id') in mapping:
                            a['id']=mapping[a['id']]
                            if a['kind']=='wire':a['point']=[a['point'][0]+40,a['point'][1]+40]
                        elif a['kind']=='point':a['point']=[a['point'][0]+40,a['point'][1]+40]
                        else:new['offset']=[new['offset'][0]+40,new['offset'][1]+40]
                    else:new['points']=[[x+40,y+40] for x,y in new['points']]
                    c[group].append(new)
        self.commit(edit,'Duplicate selection');self.select(newids,'schematic')

    def rotate(self,angle=90):
        if not self.flush_inspector():return
        if getattr(self.schematic,'label_placement',None):
            l=self.schematic.label_placement;l['rotation']=(l['rotation']+angle)%360;self.schematic.update();return
        if self.schematic.placement:
            d=self.schematic.placement;d['rotation']=(d['rotation']+angle)%360;self.schematic.update()
            self.canvas_message('Place '+d['name']+' · '+str(d['rotation'])+'° · R / Shift+R rotate · Esc cancels');self.schematic.setFocus();return
        if self.current_mode=='layout':
            if angle==90:return super().rotate()
            def edit(p):
                for i in next(c for c in p['cells'] if c['id']==self.cid).get('layout_instances',[]):
                    if i['id'] in self.selection:i['rotation']=(i.get('rotation',0)+angle)%360
        else:
            if not any(d['id'] in self.selection for d in self.cell['devices']+self.cell.get('labels',[])):return
            def edit(p):
                for d in next(c for c in p['cells'] if c['id']==self.cid)['devices']+next(c for c in p['cells'] if c['id']==self.cid).get('labels',[]):
                    if d['id'] in self.selection:d['rotation']=(d['rotation']+angle)%360
        self.commit(edit,'Rotate counterclockwise' if angle<0 else 'Rotate clockwise')
        (self.layout if self.current_mode=='layout' else self.schematic).setFocus()

    def add_junction(self):
        if self.current_mode!='schematic':return
        pos=self.schematic.drag
        if pos is None:return
        point=[pos.x(),pos.y()]
        def edit(p):
            c=next(c for c in p['cells'] if c['id']==self.cid);hits=[w for w in c.get('wires',[]) if any(wiring.on_segment(point,a,b) for a,b in zip(w['points'],w['points'][1:]))]
            if len(hits)<2:raise ValueError('Point at a wire crossing to add or remove a junction.')
            junctions=c.setdefault('junctions',[])
            if point in junctions:junctions.remove(point)
            else:
                # Merge the labels of intentionally joined networks as for a wire.
                junctions.append(point);groups=wiring.graph(c,p);root=groups[('wire',hits[0]['id'])]
                wiring.merge_labels(c,groups,root,project=p)
        self.commit(edit,'Toggle wire junction')

    def build_inspector(self):
        if self.current_mode=='schematic' and self.net:return self.build_net_inspector()
        labels=[l for l in self.cell.get('labels',[]) if l['id'] in self.selection] if self.current_mode=='schematic' else []
        if len(self.selection)==1 and labels:return self.build_label_inspector(labels[0])
        wires=[w for w in self.cell.get('wires',[]) if w['id'] in self.selection] if self.current_mode=='schematic' else []
        if not wires:return super().build_inspector()
        self.clear_form();self._inspector_dirty=False;self._inspected_device=False
        title=QLabel('Wire' if len(self.selection)==1 else f'{len(self.selection)} objects selected');title.setProperty('role','title');self.form.addWidget(title)
        if len(self.selection)==1:
            wire=wires[0];self.form.addWidget(self.button('Inspect whole net  N',fn=lambda:self.inspect_net(wire.get('net')),role='secondary'));self.form.addWidget(QLabel('Net: '+wire.get('net','Unconnected')));self.form.addWidget(QLabel(f'{len(wire["points"])-1} segments'))
        note=QLabel('Drag a wire segment to move it while keeping its ends attached. Delete removes the selected wire. W starts a new wire.');note.setWordWrap(True);self.form.addWidget(note)
        self.form.addWidget(self.button('Delete selection',fn=self.delete,role='secondary'));self.form.addStretch();self._building_inspector=False

    def make_actions(self):
        super().make_actions();menus={m.title().replace('&',''):m for m in self._menus}
        # Keep the menu actions alive too: PySide's borrowed menu wrappers can
        # otherwise become invalid when a temporary menuAction wrapper dies.
        self._menu_actions=list(self.menuBar().actions())
        # Remove old widget-only bindings so one QAction owns each command.
        for shortcut in self.findChildren(QShortcut):
            if shortcut.key().toString() in ('R','W','P','Delete','Del'):shortcut.setEnabled(False);shortcut.deleteLater()
        def editor_action(menu,title,fn,key):
            a=self.action(menu,title,fn,key);a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            for widget in (self.schematic,self.layout,self.outline,self.tree):widget.addAction(a)
            return a
        for a in list(menus['Edit'].actions()):
            if a.text() in ('Rotate 90°','Delete selection'):
                menus['Edit'].removeAction(a);self._commands=[(g,item) for g,item in self._commands if item!=a];a.deleteLater()
        self.rotate_action=editor_action(menus['Edit'],'Rotate clockwise',self.rotate,'R')
        self.rotate_back_action=editor_action(menus['Edit'],'Rotate counterclockwise',lambda:self.rotate(-90),'Shift+R')
        self.delete_action=editor_action(menus['Edit'],'Delete selection',self.delete,'Delete')
        self.wire_action=editor_action(menus['Design'],'Place wire',lambda:self.set_tool(1),'W')
        self.place_action=editor_action(menus['Design'],'Place component…',self.show_library,'P')
        self.label_action=editor_action(menus['Design'],'Place net label…',self.begin_label,'L')
        self.ground_action=editor_action(menus['Design'],'Place ground',lambda:self.begin_label('ground'),'G')
        self.net_action=editor_action(menus['Design'],'Inspect whole net',self.inspect_net,'N')
        self.junction_action=editor_action(menus['Design'],'Toggle junction at pointer',self.add_junction,'J')
        for a in menus['View'].actions():
            if a.text()=='Fit design':
                a.setShortcut(QKeySequence('F'));a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                for widget in (self.schematic,self.layout,self.outline,self.tree):widget.addAction(a)
        self.action(menus['Help'],'Keyboard shortcuts and wiring',self.wiring_help,'Ctrl+/')
        self.rotate_button=self.button('Rotate  R','rotate',self.rotate_action.trigger,tip='Rotate clockwise (R); counterclockwise (Shift+R). Works while placing a device.')
        self.tool_layout.insertWidget(3,self.rotate_button)
        self.label_button=self.button('Label  L',fn=self.label_action.trigger,tip='Place a net label (L)')
        self.ground_button=self.button('Ground  G',fn=self.ground_action.trigger,tip='Place an electrical ground symbol (G)')
        self.tool_layout.insertWidget(4,self.label_button);self.tool_layout.insertWidget(5,self.ground_button)
        self.more_tools=self.button('More…',tip='Additional schematic tools')
        more=QMenu(self.more_tools)
        for action in (self.rotate_action,self.rotate_back_action,self.label_action,self.ground_action,self.net_action):more.addAction(action)
        self.more_tools.setMenu(more);self.tool_layout.insertWidget(3,self.more_tools)
        # Menus get unique, real Qt mnemonics; literal ampersands are not hints.
        named_actions=set()
        for menu in self.findChildren(QMenu):
            used=set()
            for action in menu.actions():
                if action.isSeparator():continue
                if action in named_actions:
                    existing=action.text();index=existing.find('&')
                    if 0<=index<len(existing)-1:used.add(existing[index+1].lower())
                    continue
                named_actions.add(action)
                text=action.text().replace('&','and')
                for index,char in enumerate(text):
                    if char.isalpha() and char.lower() not in used:
                        used.add(char.lower());action.setText(text[:index]+'&'+text[index:]);break
        self.sync_tools()

    def sync_tools(self):
        super().sync_tools()
        if hasattr(self,'rotate_button'):
            if hasattr(self,'label_button'):
                self.label_button.setVisible(self.current_mode=='schematic');self.ground_button.setVisible(self.current_mode=='schematic')
            self.rotate_button.setVisible(self.current_mode=='schematic')
            self.adapt_tools()
            self.rotate_button.setEnabled(bool(self.schematic.placement or getattr(self.schematic,'label_placement',None)) or any(d['id'] in self.selection for d in self.cell['devices']+self.cell.get('labels',[])))

    def adapt_tools(self):
        super().adapt_tools()
        if not hasattr(self,'more_tools'):return
        compact=self.toolstrip.width()<820;schematic=self.current_mode=='schematic'
        self.more_tools.setVisible(schematic and compact)
        for button in (self.rotate_button,self.label_button,self.ground_button):button.setVisible(schematic and not compact)
        for i in (0,1):self.tool_buttons[i].setMinimumWidth(self.tool_buttons[i].sizeHint().width())
        self.place_button.setMinimumWidth(self.place_button.sizeHint().width())
        self.more_tools.setMinimumWidth(self.more_tools.sizeHint().width())

    def wiring_help(self):
        self.text_dialog('Wiring and keyboard shortcuts',
            'MANUAL WIRES\nW: start Wire. Click a pin, a wire, or empty space. Click to lock each bend. Finish on a pin/wire, or press Enter to finish at the last clicked point. Space or Tab flips the next elbow. Backspace removes the last click. Esc cancels the current path; Esc again selects. Right-click cancels and selects. Middle-drag pans.\n\n'
            'NET LABELS AND GROUND\nL: enter a net name, then click a wire or pin to attach it. G: click to place ground (net 0). Place on empty space to start a new conductor. Drag the label artwork independently; Reattach in the inspector changes its electrical anchor. R / Shift+R rotate a label or ground. N inspects and highlights a whole net, including remote same-name labels. Compact windows keep these commands in More.\n\n'
            'CONNECTIONS\nA solid dot is a junction. A bridge is a crossing without a connection. J at a crossing adds/removes an explicit junction. Pins and wire endpoints that touch are connected. New devices have open terminals: ground is not assigned automatically. In Connections, enter 0 to ground a conductor, or a named label to connect it to another identically labelled conductor. Clear a label to remove that named connection.\n\n'
            'EDITING\nSelect a wire and drag its segment to reposition it; the wire ends remain attached. Delete removes the wire and recalculates connectivity. Device moves/rotations stretch the terminal leads while preserving remote bends. Ctrl+Z undoes a complete gesture.\n\n'
            'KEYBOARD\nR: rotate clockwise. Shift+R: counterclockwise. Both work while placing and with a selected device. P: device library. F: fit. Arrow keys: move selection; Shift+arrows: larger step. Ctrl+D: duplicate. Ctrl+S: save. Ctrl+Z / Ctrl+Shift+Z: undo/redo. F5: run. Shift+F5: stop. F6: ERC. F7: DRC. Ctrl+K: command palette.\n\n'
            'Underlined menu letters use Alt+letter (for example Alt+F opens File), then the underlined command letter. Editor keys operate in the canvas/project selection; text fields retain normal typing shortcuts.')
