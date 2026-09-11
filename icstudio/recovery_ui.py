"""Truthful recovery status and explicit retries without weakening durability."""
from pathlib import Path
from PySide6.QtWidgets import QFileDialog
from . import recovery
from .model import digest, uid


class RecoveryUIMixin:
    def reset_recovery_status(self):
        if getattr(self,'_recovery_queue',None):self._recovery_queue.flush()
        self._recovery_epoch=getattr(self,'_recovery_epoch',0)+1
        self._recovery_error=None;self._recovery_hash=None

    def queue_recovery(self,*,validated=False):
        if not getattr(self,'_recovery_queue',None):
            from .recovery_queue import RecoveryQueue
            self._recovery_queue=RecoveryQueue(self)
            self._recovery_queue.completed.connect(self.recovery_completed)
        self._recovery_queue.request(self.project,self.recovery_dir,self.path,
                                     getattr(self,'_recovery_epoch',0),validated)
        self.update_save_status()

    def recovery_completed(self,result):
        if (result['epoch']!=getattr(self,'_recovery_epoch',0) or
            result['project_id']!=self.project['id'] or result['directory']!=str(self.recovery_dir)):
            return
        self._recovery_error=result['error']
        if not result['error']:self._recovery_hash=result['hash']
        else:self.statusBar().showMessage('Recovery failed: '+result['error']+' · File → Recovery to retry',12000)
        self.update_save_status()

    def finish_recovery(self,discard=False):
        if getattr(self,'_recovery_queue',None):return self._recovery_queue.flush(discard)
        return True

    def update_save_status(self,current_hash=None):
        current_hash=current_hash or digest(self.project)
        if self.saved_hash==current_hash:text='Saved to disk'
        elif self._recovery_error:text='Unsaved · recovery failed'
        elif self._recovery_hash==current_hash:text='Unsaved · recovery available'
        elif getattr(self,'_recovery_queue',None) and self._recovery_queue.busy:text='Unsaved · recovery pending'
        else:text='Unsaved · recovery not yet written'
        self.save_label.setText(text)
        self.save_label.setToolTip(self._recovery_error or ('Recovery folder: '+str(self.recovery_dir)))

    def save_recovery(self,*,validated=False,notify=True):
        self.finish_recovery(discard=True)
        try:
            recovery.write(self.project,self.recovery_dir,self.path,validated=validated)
        except Exception as exc:
            message=('Recovery save failed. Your edits remain open. Use File → Recovery to retry or choose a working folder, or use Save As on another drive. '+str(exc))
            changed=message!=self._recovery_error
            self._recovery_error=message
            self.update_save_status()
            if notify and changed:self.error(message)
            elif notify:self.statusBar().showMessage(message,12000)
            return False
        self._recovery_error=None;self._recovery_hash=digest(self.project)
        self.update_save_status();return True

    def retry_recovery(self):
        if not self.flush_inspector():return False
        return self.save_recovery()

    def choose_recovery_folder(self):
        if not self.flush_inspector():return False
        folder=QFileDialog.getExistingDirectory(self,'Choose recovery folder',str(self.recovery_root))
        if not folder:return False
        return self.use_recovery_folder(folder)

    def use_recovery_folder(self,folder):
        # Publish an actual durable snapshot before changing any session path.
        self.finish_recovery()
        root=Path(folder).resolve();directory=root/uid()
        recovery.write(self.project,directory,self.path)
        previous=list(self.settings.value('storage/previous_recovery_roots',[]) or [])
        if str(self.recovery_root) not in previous:previous.append(str(self.recovery_root))
        self.settings.setValue('storage/previous_recovery_roots',previous[-8:])
        self.settings.setValue('storage/recovery_root',str(root))
        self.recovery_root=root;self.recovery_dir=directory
        self._recovery_error=None;self._recovery_hash=digest(self.project)
        self.update_save_status();return True
