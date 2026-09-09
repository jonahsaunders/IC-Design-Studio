"""Wrap drawing controls at their readable widths instead of clipping labels."""
from PySide6.QtCore import QSize,QRect,Qt
from PySide6.QtWidgets import QLayout,QWidgetItem


class DrawingOptionsLayout(QLayout):
    def __init__(self):
        super().__init__();self.items=[];self.setContentsMargins(0,0,0,0);self.setSpacing(7)

    def addItem(self,item):self.items.append(item)
    def insertWidget(self,index,widget):
        self.addChildWidget(widget);self.items.insert(max(0,index),QWidgetItem(widget));self.invalidate()
    def addStretch(self,*_):pass
    def count(self):return len(self.items)
    def itemAt(self,index):return self.items[index] if 0<=index<len(self.items) else None
    def takeAt(self,index):return self.items.pop(index) if 0<=index<len(self.items) else None
    def expandingDirections(self):return Qt.Orientations(0)
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):return self.arrange(QRect(0,0,width,0),True)
    def minimumSize(self):return QSize(100,0)
    def sizeHint(self):return QSize(500,34)
    def setGeometry(self,rect):super().setGeometry(rect);self.arrange(rect,False)

    def arrange(self,rect,measure):
        items=[item for item in self.items if item.widget() is not None and not item.widget().isHidden()]
        x,y,height=rect.x(),rect.y(),0
        for i,item in enumerate(items):
            size=item.sizeHint();needed=size.width()
            if item.widget().property('keepNext') and i+1<len(items):needed+=self.spacing()+items[i+1].sizeHint().width()
            if x>rect.x() and x+needed>rect.right()+1:x=rect.x();y+=height+self.spacing();height=0
            if not measure:item.setGeometry(QRect(x,y,size.width(),size.height()))
            x+=size.width()+self.spacing();height=max(height,size.height())
        return y+height-rect.y()
