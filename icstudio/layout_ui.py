"""KLayout-inspired layer visibility, selection controls and hierarchy navigation."""
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtWidgets import QLineEdit,QHBoxLayout,QComboBox,QTreeWidget,QTreeWidgetItem,QLabel,QMenu,QInputDialog
from .model import clone
from .ui_style import icon

class LayoutMixin:
    def make_ui(self):
        super().make_ui();self.layout.locked_layers=set();self.layout.hierarchy_depth=None
        page=self.navtabs.widget(2);v=page.layout();self.layer_search=QLineEdit();self.layer_search.setPlaceholderText('Find layer by name or GDS number…');self.layer_search.textChanged.connect(self.filter_layers);v.insertWidget(1,self.layer_search)
        row=QHBoxLayout()
        for title,fn in [('All',lambda:self.show_layers('all')),('None',lambda:self.show_layers('none')),('Solo',lambda:self.show_layers('solo'))]:row.addWidget(self.button(title,fn=fn))
        v.insertLayout(2,row);self.layers.setContextMenuPolicy(Qt.CustomContextMenu);self.layers.customContextMenuRequested.connect(self.layer_context)
        self.layers.itemClicked.disconnect();self.layers.itemClicked.connect(lambda it:self.layer_combo.setCurrentText(it.data(Qt.UserRole) or it.text()))
        v.addWidget(QLabel('CELL HIERARCHY'));self.physical_tree=QTreeWidget();self.physical_tree.setHeaderHidden(True);self.physical_tree.setMaximumHeight(200);self.physical_tree.itemDoubleClicked.connect(self.enter_layout_cell);v.addWidget(self.physical_tree)
        row=QHBoxLayout();row.addWidget(QLabel('Show depth'));self.depth_combo=QComboBox();self.depth_combo.addItems(['All levels','This cell','1 level','2 levels','3 levels']);self.depth_combo.currentIndexChanged.connect(self.set_hierarchy_depth);row.addWidget(self.depth_combo);row.addWidget(self.button('Fit selection',fn=self.fit_selection));v.addLayout(row)
    def refresh(self,fit=False):
        super().refresh(fit)
        if not hasattr(self,'layer_search'):return
        self.layers.blockSignals(True)
        for i,l in enumerate(self.project['pdk']['layers']):
            it=self.layers.item(i);it.setData(Qt.UserRole,l['name']);it.setText(l['name']+f'  {l["gds"]}/{l["datatype"]}'+('  · locked' if l['name'] in self.layout.locked_layers else ''));it.setToolTip(f'{l["name"]}\nGDS {l["gds"]} / {l["datatype"]}\n'+('Locked for selection' if l['name'] in self.layout.locked_layers else 'Selectable'))
        self.layers.blockSignals(False);self.filter_layers();self.physical_tree.clear();by={c['id']:c for c in self.project['cells']}
        def node(cid,parent,seen):
            c=by[cid];it=QTreeWidgetItem(parent,[c['name']]);it.setData(0,Qt.UserRole,cid);it.setIcon(0,icon('cell'));it.setExpanded(True)
            if cid in seen:return
            for inst in c.get('layout_instances',[]):
                child=node(inst['cell'],it,seen|{cid});child.setText(0,inst['name']+' → '+by[inst['cell']]['name']+f'  [{inst.get("nx",1)}×{inst.get("ny",1)}]')
            return it
        node(self.cid,self.physical_tree,set())
    def layer_changed(self,item):
        name=item.data(Qt.UserRole) or item.text()
        if item.checkState()==Qt.Checked:self.layout.visible_layers.add(name)
        else:self.layout.visible_layers.discard(name)
        self.layout.update()
    def filter_layers(self,*args):
        if not hasattr(self,'layer_search'):return
        query=self.layer_search.text().lower()
        for i in range(self.layers.count()):self.layers.item(i).setHidden(query not in self.layers.item(i).text().lower())
    def show_layers(self,mode):
        names={l['name'] for l in self.project['pdk']['layers']};self.layout.visible_layers=names if mode=='all' else set() if mode=='none' else {self.layer_combo.currentText()};self.refresh()
    def layer_context(self,pos):
        it=self.layers.itemAt(pos)
        if not it:return
        name=it.data(Qt.UserRole);self.layer_combo.setCurrentText(name);menu=QMenu(self);menu.addAction('Show only this layer',lambda:self.show_layers('solo'));menu.addAction('Show all layers',lambda:self.show_layers('all'))
        def lock():
            if name in self.layout.locked_layers:self.layout.locked_layers.remove(name)
            else:self.layout.locked_layers.add(name)
            self.refresh()
        menu.addAction('Unlock selection' if name in self.layout.locked_layers else 'Lock selection',lock);menu.addAction('Move selected shapes here',lambda:self.guard(lambda:self.move_to_layer(name)));menu.exec(self.layers.viewport().mapToGlobal(pos))
    def move_to_layer(self,name):
        ids=set(self.selection)
        if not ids:raise ValueError('Select layout shapes first.')
        def edit(p):
            c=next(c for c in p['cells'] if c['id']==self.cid)
            if any(s['id'] in ids and s['layer'] in self.layout.locked_layers for s in c['shapes']):raise ValueError('Unlock selected shapes before moving layers.')
            for s in c['shapes']:
                if s['id'] in ids:s['layer']=name
        self.commit(edit,'Move shapes to layer')
    def enter_layout_cell(self,item,col=0):
        if not self.flush_inspector():return
        self.cid=item.data(0,Qt.UserRole);self.selection=[];self.mode_combo.setCurrentIndex(1);self.refresh(True)
    def set_hierarchy_depth(self,index):self.layout.hierarchy_depth=None if index==0 else index-1;self.render_physical_hierarchy();self.layout.update()
    def fit_selection(self):
        canvas=self.layout if self.current_mode=='layout' else self.schematic;objects=[s for s in canvas.cell['shapes' if self.current_mode=='layout' else 'devices'] if s['id'] in self.selection]
        if not objects:return
        box=canvas.bounds(objects[0])
        for obj in objects[1:]:box=box.united(canvas.bounds(obj))
        margin=max(box.width(),box.height())*.1+10;box.adjust(-margin,-margin,margin,margin);canvas.auto_fit=False;canvas.scale=min(canvas.width()/box.width(),canvas.height()/box.height());canvas.offset=QPointF(canvas.width()/2-box.center().x()*canvas.scale,canvas.height()/2-box.center().y()*canvas.scale);canvas.update();self.update_canvas_footer()
