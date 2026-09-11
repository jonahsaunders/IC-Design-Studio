"""Native hierarchy-preserving GDS/OASIS reader using KLayout."""
import re
from .model import example,uid,validate,NET
from .layout import kdb,shape_from_polygon


def read_layout(path):
    db=kdb();ly=db.Layout();ly.read(str(path));p=example('empty');p['name']=path.stem;p['cells']=[];p['pdk']['layers']=[]
    p['pdk']['name']='Imported layout layers'
    factor=ly.dbu/.001;warnings=['Imported layout hierarchy and geometry. Schematic/device mappings require a matching Studio sidecar.'];by={};names=set()
    from .layout_limits import MAX_CELLS
    if ly.cells()>MAX_CELLS:raise ValueError(f'The native project limit is {MAX_CELLS} cells. Import a smaller hierarchy.')
    def nm(value):
        v=value*factor
        if abs(v-round(v))>1e-6:raise ValueError('Layout coordinates do not fit the 1 nm database grid.')
        return round(v)
    for idx in ly.layer_indexes():
        info=ly.get_info(idx)
        colors=('#68a6f4','#bd98ef','#66c7ae','#e9b775','#e589a2','#83c4dc','#c0cc79')
        p['pdk']['layers'].append({'name':f'layer_{info.layer}_{info.datatype}','gds':info.layer,'datatype':info.datatype,'color':colors[info.layer%len(colors)],'width':0,'space':0})
    if not p['pdk']['layers']:raise ValueError('No drawable layers in layout.')
    for cell in ly.each_cell():
        name=re.sub('[^A-Za-z0-9_.$-]','_',cell.name)[:55]
        if not name or not re.match('[A-Za-z_]',name):name='cell_'+name
        base=name;i=1
        while name.casefold() in names:i+=1;name=base+'_'+str(i)
        names.add(name.casefold());c={'id':uid(),'name':name,'ports':[],'devices':[],'shapes':[],'layout_instances':[],'layout_texts':[]};p['cells'].append(c);by[cell.cell_index()]=c
        marker=cell.property(125)
        if isinstance(marker,str) and marker.startswith('icstudio:'):c['source_cell_id']=marker[9:]
        c['external_properties']=[[k,v] for k,v in cell.properties().items() if k!=125]
        if name!=cell.name:c['source_cell_name']=cell.name;warnings.append('Renamed external cell '+cell.name+' to '+name)
    for cell in ly.each_cell():
        c=by[cell.cell_index()]
        for idx in ly.layer_indexes():
            info=ly.get_info(idx);layer=f'layer_{info.layer}_{info.datatype}'
            for shape in cell.shapes(idx).each():
                if shape.is_text():
                    text=shape.text;c['layout_texts'].append({'layer':layer,'text':text.string,'x':nm(text.x),'y':nm(text.y),'rotation':text.trans.angle*90,'mirror':text.trans.is_mirror(),
                        'size':nm(text.size),'font':text.font,'halign':int(text.halign),'valign':int(text.valign)})
                    properties=[[k,v] for k,v in shape.properties().items() if k!=125]
                    if properties:c['layout_texts'][-1]['external_properties']=properties
                    continue
                if not (shape.is_box() or shape.is_polygon() or shape.is_path() or shape.is_simple_polygon()):raise ValueError('Unsupported GDS/OASIS shape type.')
                poly=shape.polygon
                for pt in poly.each_point_hull():nm(pt.x);nm(pt.y)
                for i in range(poly.holes()):
                    for pt in poly.each_point_hole(i):nm(pt.x);nm(pt.y)
                record=shape_from_polygon(poly.transformed(db.ICplxTrans(factor,0,False,0,0)),layer)
                marker=shape.property(127) or shape.property('icstudio_id')
                if isinstance(marker,str):record['source_shape_id']=marker[9:] if marker.startswith('icstudio:') else marker
                record['external_properties']=[[k,v] for k,v in shape.properties().items() if k not in (125,127,'icstudio_id')]
                c['shapes'].append(record)
        for i,inst in enumerate(cell.each_inst(),1):
            tr=inst.cplx_trans
            if abs(tr.mag-1)>1e-12 or tr.angle not in (0,90,180,270):raise ValueError('Non-unit magnification or non-orthogonal instance rotation requires conversion in KLayout before native editing.')
            c['layout_instances'].append({'id':uid(),'name':f'I{i}','cell':by[inst.cell_index]['id'],'x':nm(tr.disp.x),'y':nm(tr.disp.y),'rotation':int(tr.angle),'mirror':tr.is_mirror(),'nx':max(1,inst.na),'ny':max(1,inst.nb),'a':[nm(inst.a.x),nm(inst.a.y)],'b':[nm(inst.b.x),nm(inst.b.y)]})
            marker=inst.property(126)
            if isinstance(marker,str) and marker.startswith('icstudio:'):c['layout_instances'][-1]['source_instance_id']=marker[9:]
            else:
                for number in (61,98):
                    marker=inst.property(number)
                    if isinstance(marker,str) and marker.startswith('studio_'):
                        c['layout_instances'][-1]['source_instance_id']=marker[7:];break
            c['layout_instances'][-1]['external_properties']=[[k,v] for k,v in inst.properties().items() if k not in (125,126)]
    tops=list(ly.top_cells())
    if not tops:raise ValueError('Layout has no top cell.')
    p['top']=by[tops[0].cell_index()]['id'];return validate(p),warnings
