"""Direct text-note properties using the normal draft, commit and undo flow."""
import math
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel,QPlainTextEdit


class AnnotationMixin:
    def reveal_properties(self):
        super().reveal_properties()
        if 'annotation:text' in self.form_fields:self.form_fields['annotation:text'].setFocus()

    def build_annotation_inspector(self,note):
        self.clear_form();self._inspector_dirty=False;self._inspected_device=False;self.inspected_id=note['id']
        title=QLabel('Annotation');title.setProperty('role','title');self.form.addWidget(title)
        text=QPlainTextEdit(note['text']);text.setAccessibleName('Annotation text');text.setMinimumHeight(110)
        self.form_fields['annotation:text']=text;self.form.addWidget(text);text.textChanged.connect(self.inspector_changed)
        position=self.section('Position');self.field('X',note['x'],'annotation:x',position);self.field('Y',note['y'],'annotation:y',position)
        self.property_error=QLabel();self.property_error.setTextFormat(Qt.PlainText);self.property_error.setWordWrap(True);self.property_error.hide();self.form.addWidget(self.property_error)
        self.apply_button=self.button('Apply changes',fn=lambda:self.apply_inspector(False),role='primary')
        self.reset_button=self.button('Reset',fn=self.build_inspector)
        self.apply_button.setEnabled(False);self.reset_button.setEnabled(False)
        self.form.addWidget(self.apply_button);self.form.addWidget(self.reset_button)
        self.form.addWidget(self.button('Delete annotation',fn=self.delete,role='secondary'))
        hint=QLabel('Drag to move. Delete removes the selected note; Undo restores it. Double-click or Enter opens these properties.');hint.setWordWrap(True);self.form.addWidget(hint);self.form.addStretch();self._building_inspector=False

    def build_annotation_group_inspector(self):
        self.clear_form();self._inspector_dirty=False;self._inspected_device=False
        self.form.addWidget(QLabel(str(len(self.selection))+' objects selected'))
        hint=QLabel('Move, duplicate or delete the selection together. Select one annotation to edit its text.');hint.setWordWrap(True);self.form.addWidget(hint)
        self.form.addWidget(self.button('Duplicate selection',fn=self.duplicate))
        self.form.addWidget(self.button('Delete selection',fn=self.delete));self.form.addStretch();self._building_inspector=False

    def apply_inspector(self,is_device):
        if 'annotation:text' not in self.form_fields:return super().apply_inspector(is_device)
        try:
            ident=self.inspected_id;cid=self.cid;text=self.form_fields['annotation:text'].toPlainText()
            x,y=(float(self.form_fields['annotation:'+a].text()) for a in ('x','y'))
            if not text.strip() or len(text)>2000:raise ValueError('Enter annotation text of 1–2,000 characters.')
            if any(not math.isfinite(v) or abs(v)>1e7 for v in (x,y)):raise ValueError('Enter finite annotation coordinates between -10,000,000 and 10,000,000.')
            def edit(p):
                cell=next(c for c in p['cells'] if c['id']==cid)
                note=next((n for n in cell.get('annotations',[]) if n['id']==ident),None)
                if note is None:raise ValueError('This annotation was removed. Select another object.')
                note.update(text=text,x=x,y=y)
            self._inspector_dirty=False;self.commit(edit,'Edit annotation');return True
        except Exception as exc:
            self._inspector_dirty=True;self.property_error.setText(str(exc));self.property_error.show();return False
