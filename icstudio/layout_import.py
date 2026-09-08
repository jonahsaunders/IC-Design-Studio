"""Native hierarchy-preserving GDS/OASIS reader using KLayout."""
import re
from .model import example,uid,validate,NET
from .layout import kdb,shape_from_polygon


def read_layout(path):
    db=kdb();ly=db.Layout();ly.read(str(path));p=example('empty');p['name']=path.stem;p['cells']=[];p['pdk']['layers']=[]
    factor=ly.dbu/.001;warnings=['Imported layout hierarchy and geometry. Schematic/device mappings require a matching Studio sidecar.'];by={};names=set()
    if ly.cells()>100:raise ValueError('The native project limit is 100 cells. Import a smaller hierarchy.')
    def nm(value):
        v=value*factor
        if abs(v-round(v))>1e-6:raise ValueError('Layout coordinates do not fit the 1 nm database grid.')
        return round(v)
    for idx in ly.layer_indexes():
        info=ly.get_info(idx);p['pdk']['layers'].append({'name':f'layer_{info.layer}_{info.datatype}','gds':info.layer,'datatype':info.datatype,'color':'#68a6f4','width':0,'space':0})
    if not p['pdk']['layers']:raise ValueError('No drawable layers in layout.')
    for cell in ly.each_cell():
        name=re.sub('[^A-Za-z0-9_.$-]','_',cell.name)[:55]
        if not name or not re.match('[A-Za-z_]',name):name='cell_'+name
        base=name;i=1
        while name.casefold() in names:i+=1;name=base+'_'+str(i)
        names.add(name.casefold());c={'id':uid(),'name':name,'ports':[],'devices':[],'shapes':[],'layout_instances':[],'layout_texts':[]};p['cells'].append(c);by[cell.cell_index()]=c
        if name!=cell.name:c['source_cell_name']=cell.name;warnings.append('Renamed external cell '+cell.name+' to '+name)
    for cell in ly.each_cell():
        c=by[cell.cell_index()]
        for idx in ly.layer_indexes():
            info=ly.get_info(idx);layer=f'layer_{info.layer}_{info.datatype}'
            for shape in cell.shapes(idx).each():
                if shape.is_text():
                    text=shape.text;c['layout_texts'].append({'layer':layer,'text':text.string,'x':nm(text.x),'y':nm(text.y),'rotation':text.trans.angle*90,'mirror':text.trans.is_mirror()});continue
                if not (shape.is_box() or shape.is_polygon() or shape.is_path() or shape.is_simple_polygon()):raise ValueError('Unsupported GDS/OASIS shape type.')
                poly=shape.polygon
                for pt in poly.each_point_hull():nm(pt.x);nm(pt.y)
                for i in range(poly.holes()):
                    for pt in poly.each_point_hole(i):nm(pt.x);nm(pt.y)
                c['shapes'].append(shape_from_polygon(poly.transformed(db.ICplxTrans(factor,0,False,0,0)),layer))
        for i,inst in enumerate(cell.each_inst(),1):
            tr=inst.cplx_trans
            if abs(tr.mag-1)>1e-12 or tr.angle not in (0,90,180,270):raise ValueError('Non-unit magnification or non-orthogonal instance rotation requires conversion in KLayout before native editing.')
            c['layout_instances'].append({'id':uid(),'name':f'I{i}','cell':by[inst.cell_index]['id'],'x':nm(tr.disp.x),'y':nm(tr.disp.y),'rotation':int(tr.angle),'mirror':tr.is_mirror(),'nx':max(1,inst.na),'ny':max(1,inst.nb),'a':[nm(inst.a.x),nm(inst.a.y)],'b':[nm(inst.b.x),nm(inst.b.y)]})
            marker=inst.property(126)
            if isinstance(marker,str) and marker.startswith('icstudio:'):c['layout_instances'][-1]['source_instance_id']=marker[9:]
    tops=list(ly.top_cells())
    if not tops:raise ValueError('Layout has no top cell.')
    p['top']=by[tops[0].cell_index()]['id'];return validate(p),warnings
