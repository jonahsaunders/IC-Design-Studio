"""Direct electrical label tools and whole-net inspector."""
from PySide6.QtCore import Qt,QPointF
from PySide6.QtWidgets import QLabel,QInputDialog,QLineEdit,QCheckBox,QListWidget
from . import net_labels,wiring
from .model import clone

class NetLabelMixin:
    def begin_label(self,kind='net_label',name=None,reattach=None):
        if not self.flush_inspector():return
        if kind=='ground':name='0'
        elif name is None:
            name,ok=QInputDialog.getText(self,'Place net label','Net name (matching names connect within this cell):',text=getattr(self,'_last_net_label','out'))
            if not ok:return
            name=name.strip()
            from .model import NET
            if not NET.fullmatch(name):raise ValueError('Invalid net name. Use VDD, out, or 0 for ground.')
        self._last_net_label=name;self.mode_combo.setCurrentIndex(0);self.cancel_tool()
        self.schematic.label_placement={'kind':kind,'name':name,'rotation':0,'reattach':reattach};self.schematic.tool='label';self.schematic.drag=self.schematic.snap(self.schematic.model(self.schematic.rect().center()));self.schematic.label_raw=self.schematic.drag;self.schematic.setFocus();self.schematic.update();self.sync_tools()
        self.canvas_message('Place '+('ground' if kind=='ground' else name)+' · click a pin, wire, or empty space · R rotates · Esc cancels')

    def place_label(self,anchor):
        spec=self.schematic.label_placement
        if not spec:return
        result=[]
        def edit(p):
            c=next(c for c in p['cells'] if c['id']==self.cid)
            if spec.get('reattach'):
                l=next(l for l in c['labels'] if l['id']==spec['reattach']);l['anchor']=clone(anchor);result.append(l['id'])
            else:
                result.append(net_labels.add(c,spec['name'],clone(anchor),p,spec['kind']));c['labels'][-1]['rotation']=spec['rotation']
        self.commit(edit,'Reattach label' if spec.get('reattach') else 'Place '+spec['name']);self.cancel_tool();self.select(result,'schematic');self.schematic.setFocus()
        self.canvas_message('Label placed · drag its text or symbol without changing its connection · L adds a label · G adds ground')

    def build_label_inspector(self,l):
        self.clear_form();self._inspector_dirty=False;self._inspected_device=False;self.inspected_id=l['id']
        title=QLabel('Ground' if l['kind']=='ground' else 'Net label');title.setProperty('role','title');self.form.addWidget(title)
        f=self.section('Connection');self.field('Net name',l['name'],'label:name',f);self.field('Text offset X',l['offset'][0],'label:x',f);self.field('Text offset Y',l['offset'][1],'label:y',f)
        self.label_whole=QCheckBox('Rename every label on this net');self.label_whole.setChecked(True);f.addRow(self.label_whole)
        self.property_error=QLabel();self.property_error.setWordWrap(True);self.property_error.hide();self.form.addWidget(self.property_error)
        self.apply_button=self.button('Apply changes',fn=lambda:self.apply_inspector(False),role='primary');self.reset_button=self.button('Reset',fn=self.build_inspector);self.apply_button.setEnabled(False);self.reset_button.setEnabled(False);self.form.addWidget(self.apply_button);self.form.addWidget(self.reset_button)
        self.form.addWidget(self.button('Inspect whole net  N',fn=lambda:self.inspect_net(l['name']),role='secondary'))
        self.form.addWidget(self.button('Reattach…',fn=lambda:self.begin_label(l['kind'],l['name'],l['id'])))
        note=QLabel('Drag the artwork to move it. Its electrical anchor stays attached. Reattach changes the connection. Delete removes this label.');note.setWordWrap(True);self.form.addWidget(note);self.form.addStretch();self._building_inspector=False

    def apply_inspector(self,is_device):
        if 'label:name' not in self.form_fields:return super().apply_inspector(is_device)
        try:
            ident=self.inspected_id;name=self.form_fields['label:name'].text().strip();offset=[float(self.form_fields['label:'+a].text()) for a in ('x','y')];whole=self.label_whole.isChecked()
            def edit(p):
                c=next(c for c in p['cells'] if c['id']==self.cid);net_labels.rename(c,ident,name,p,whole);next(l for l in c['labels'] if l['id']==ident)['offset']=offset
            self._inspector_dirty=False;self.commit(edit,'Edit net label');return True
        except Exception as exc:
            self._inspector_dirty=True;self.property_error.setText(str(exc));self.property_error.show();return False

    def inspect_net(self,name=None):
        if self.current_mode!='schematic' or not self.flush_inspector():return
        if name is None:
            names=set()
            for o in self.cell.get('wires',[])+self.cell.get('labels',[]):
                if o['id'] in self.selection:names.add(o.get('net',o.get('name')))
            for d in self.cell['devices']:
                if d['id'] in self.selection:names.update(d['nets'].values())
            names=sorted(names or {n for d in self.cell['devices'] for n in d['nets'].values()}|{w['net'] for w in self.cell.get('wires',[])})
            if not names:return
            if len(names)==1:name=names[0]
            else:
                name,ok=QInputDialog.getItem(self,'Inspect net','Net in this cell:',names,0,False)
                if not ok:return
        self.net=name
        for canvas in (self.schematic,self.layout):canvas.set_data(self.cell,self.project['pdk'],self.selection,name)
        self.build_net_inspector();self.reveal_properties()

    def build_net_inspector(self):
        info=net_labels.describe(self.cell,self.net,self.project);self.clear_form();self._inspector_dirty=False;self._inspected_device=False
        title=QLabel(self.net);title.setProperty('role','title');title.setWordWrap(True);self.form.addWidget(title)
        note=QLabel(f'{len(info["pins"])} terminals · {info["wires"]} wire paths · {info["conductors"]} physical conductors\nMatching labels connect separate conductors within this cell.');note.setWordWrap(True);self.form.addWidget(note)
        self.net_members=QListWidget();self.net_members.setAccessibleName('Net terminals')
        for member in info['pins']:
            self.net_members.addItem(member['device']+'.'+member['pin']);self.net_members.item(self.net_members.count()-1).setData(Qt.UserRole,member['device_id'])
        self.net_members.itemActivated.connect(lambda item:self.select([item.data(Qt.UserRole)],'schematic'));self.form.addWidget(self.net_members)
        self.form.addWidget(self.button('Select all members',fn=lambda:self.select(info['ids'],'schematic')))
        self.form.addWidget(self.button('Clear highlight',fn=lambda:self.select(self.selection,'schematic')));self._building_inspector=False
