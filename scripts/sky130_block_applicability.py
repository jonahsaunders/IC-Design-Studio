"""Review bounded SKY130 block applicability without promoting deck mentions.

Each periphery source record is retained. Absent-operand decisions measure the
actual final GDS, including hierarchy. They apply only to the named constraints;
absence of a selector never automatically discharges an entire device family.
The additional error catalog and unreviewed execution semantics remain blockers.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import klayout.db as k
from scripts.sky130_rule_inventory import SOURCE_LOCK_SHA256, REVISION, manual_rows

NAMED_CELL_GROUPS={
    'li_vpp_exception_cells':('s8rf2_xcmvpp_hd5_*',),
    'm1_contact_exception_cells':('s8cell_ee_plus_sseln_a','s8cell_ee_plus_sseln_b',
        's8cell_ee_plus_sselp_a','s8cell_ee_plus_sselp_b','s8fpls_pl8','s8fs_cmux4_fm'),
    'phv_contact_exception_cells':('s8fs_gwdlvx4','s8fs_gwdlvx8','s8fs_hvrsw_x4',
        's8fs_hvrsw8','s8fs_hvrsw264','s8fs_hvrsw520'),
    'nshort_contact_exception_cells':('s8fs_rdecdrv','s8fs_rdec8','s8fs_rdec32','s8fs_rdec264','s8fs_rdec520'),
    'cpmm_exception_cells':('PadPLfp','padPLhp','padPLstg','padPLwlbi'),
}


def named_cell_counts(names):
    # Only the one explicitly published trailing wildcard is expanded. All
    # other exception cell names must match literally, including underscores.
    return {key:sum(any(name.startswith(pattern[:-1]) if pattern.endswith('*') else name==pattern
                       for pattern in patterns) for name in names)
            for key,patterns in NAMED_CELL_GROUPS.items()}


def tap_interactions(diff,tap):
    # Include corner touches and even invalid overlaps. Such cases must never
    # be called absent merely because they have no positive-length butt edge.
    return tap.merged().interacting(diff.merged()).count()


def gates_outside_standard_cells(diff,poly,standard_cells):
    return ((diff&poly)-standard_cells).count()


def special_label_counts(labels):
    counts=Counter(labels)
    result={label+'_labels':counts[label] for label in ('hv_bb','hv_lv','shv_nwell')}
    # Conservatively include the related condiode variants/capitalizations:
    # a label requiring review cannot disappear through exact-case matching.
    result['condiode_labels']=sum(n for label,n in counts.items() if label.strip().casefold().startswith('condiode'))
    return result


def selector_for(row):
    """Explicit review map; a new/renamed rule receives no inherited exemption."""
    rule=row['rule']
    groups={
        ('dnwell.2','dnwell.3','dnwell.4','dnwell.5','dnwell.7'):((64,18),),
        ('nwell.5','nwell.7'):((64,18),),
        ('nwell.6',):('nwell_holes',),
        ('hvtr.1','hvtr.2','hvtr.3'):((18,20),),
        ('hvi.1','hvi.2a','hvi.2b','hvi.4','hvi.5'):((75,20),),
        ('nsm.1','nsm.2','nsm.3','nsm.3a','nsm.3b'):((61,20),(22,0)),
        ('x.13','x.14'):((81,2),),
        ('x.19','x.23b','x.23c'):((81,1),),
        ('x.26',):('advSeal_6um_cells',),
        ('x.16',):((81,10),),
        ('x.21',):((84,44),),
        ('x.25',):((82,44),),
        ('x.10',):((65,13),(66,13)),
        ('x.2a',):((81,79),),
        ('x.2c',):((74,22),),
        ('x.15b',):((91,44),'cpmm_exception_cells'),
        ('x.24',):('condiode_labels',),
        ('poly.1b',):((125,44),),
        # poly.X.1 expressly exempts W/L checks inside areaid.sc. A gate
        # crossing that boundary is still counted as an unreviewed operand.
        ('poly.X.1',):('gates_outside_sc',),
        # Published gds_layers.csv maps TUNM to 80:20. These eight rows all
        # constrain TUNM itself or gates selected by it; they do not require
        # a tunnel implant on an otherwise ordinary low-voltage transistor.
        ('tunm.1','tunm.2','tunm.3','tunm.4','tunm.5','tunm.6a','tunm.7','tunm.8'):((80,20),),
        ('difftap.4','difftap.5','difftap.6','difftap.7'):('tap_interacting_diff',),
        ('poly.3','poly.9'):((66,13),),
        ('poly.15',):((65,13),),
        ('li.7.-',):((67,13),),
        ('lvtn.1a','lvtn.2','lvtn.3a','lvtn.3b','lvtn.9','lvtn.10','lvtn.12','lvtn.13','lvtn.14'):((125,44),),
        ('ncm.X.2','ncm.X.3','ncm.1','ncm.2a','ncm.2b','ncm.5','ncm.6','ncm.7','ncm.8'):((92,44),),
        ('rpm.1a','rpm.2','rpm.6','rpm.7','rpm.8'):((86,20),),
        ('rpm.1b','rpm.1c','rpm.1d','rpm.1e','rpm.1f','rpm.1g','rpm.1h','rpm.1i','rpm.1j','rpm.1k',
         'rpm.3','rpm.4','rpm.5','rpm.9'):('prec_resistor',),
        # C3 defines Hdiff/Htap/Hnwell by intersection with HVI. HV_nwell
        # additionally includes wells overlapping areaid.hl: omitting that
        # second operand could silently exempt unmarked high-voltage wells.
        ('hvnwell.8','hvdifftap.17','hvdifftap.18','hvdifftap.20'):((75,20),(81,63)),
        ('hvnwell.9','hvnwell.10','hvdifftap.14','hvdifftap.14a','hvdifftap.15a','hvdifftap.15b',
         'hvdifftap.16','hvdifftap.19','hvdifftap.21','hvdifftap.22','hvdifftap.23','hvdifftap.24',
         'hvpoly.13','hvpoly.14','hvntm.3','hvntm.7'):((75,20),),
        ('hvntm.X.1','hvntm.1','hvntm.2','hvntm.4','hvntm.5','hvntm.6a','hvntm.6b','hvntm.9','hvntm.10'):((125,20),),
        # C3 defines hv_source/drain through diff.hv (65:8), and hvPoly /
        # hvFET_gate through connection / butting to that marked operand.
        # This discharges only the listed marked-geometry constraints. The
        # independent obligation to identify operating voltages and propagate
        # their tags (hv.X.1, hv.X.4, hvnwell.11) deliberately stays unresolved.
        ('hv.diff.1a','hv.diff.1b','hv.diff.2','hv.diff.3a','hv.diff.3b',
         'hv.poly.1','hv.poly.2','hv.poly.3','hv.poly.4','hv.poly.6a','hv.poly.6b',
         'hv.poly.7','hv.poly.8'):((65,8),),
        ('hv.X.3',):((65,8),'hv_bb_labels'),
        ('hv.X.5',):((65,8),'hv_lv_labels'),
        ('hv.nwell.1',):('shv_nwell_labels',),
        # Every denmos/depmos gate, source and drain definition in C3
        # includes areaid.en. This is a geometric absence proof, not evidence
        # that an electrically high-voltage device has been tagged correctly.
        ('denmos.1','denmos.2','denmos.3','denmos.4','denmos.5','denmos.6','denmos.7','denmos.8',
         'denmos.10','denmos.11','denmos.12','denmos.13',
         'depmos.1','depmos.2','depmos.3','depmos.4','depmos.5','depmos.6','depmos.7','depmos.8',
         'depmos.10','depmos.11','depmos.12','extd.1','extd.2','extd.3'):((81,57),),
        ('rfdiode.1.-','rfdiode.2.-','rfdiode.3.-'):((81,125),),
        # VHVGate and VHVSourceDrain explicitly include VHVI in C3. Its
        # absence proves these selected targets absent, not correct voltage
        # tagging of terminals under the separate vhvi.vhv.1 requirement.
        ('vhvi.1.-','vhvi.2.-','vhvi.3.-','vhvi.4.-','vhvi.5.-','vhvi.6.-',
         'vhvi.7.-','vhvi.8.-','vhvi.vhv.5'):((74,21),),
        ('npc.5','licon.2b','licon.2c','licon.2d'):('slotted_licon',),
        ('licon.1b','licon.1c'):('prec_resistor',),
        ('licon.10',):('Var_channel',),
        ('licon.11c',):('phv_contact_exception_cells',),
        ('licon.11d',):('nshort_contact_exception_cells',),
        ('li.1a.-','li.3a.-'):('li_vpp_exception_cells',),
        ('m1.4a',):('m1_contact_exception_cells',),
        # These exact rows constrain larger via options only inside areaid.mt.
        # Ordinary outside-module square size/enclosure is checked separately.
        ('via.1b','via.4b','via.4c','via.5b','via.5c',
         'via2.1d','via2.4a','via3.1a'):((81,10),),
        # C3 defines photoDiode as deep nwell overlapping areaid.po. Requiring
        # both drawn inputs absent avoids hiding an incomplete marked device.
        ('photo.1','photo.2','photo.3','photo.4','photo.5','photo.6',
         'photo.7','photo.8','photo.9','photo.10','photo.11'):((64,18),(81,81)),
        ('poly.X.1a',):('dummy_poly_labels',),
        ('m1.-',):((62,24),),('m2.-',):((105,52),),
        ('m3.-',):((107,24),),('m4.-',):((112,4),),
        ('pad.2','pad.3'):((76,20),),
        # RDL/CCU1M purposes are explicit in the hash-locked installed map
        # checked by the mandatory global profile. Enclosure rdl.3 requires
        # PAD absent as well; absent RDL alone would conceal a missing layer.
        ('rdl.1','rdl.2','rdl.4','rdl.6'):((74,20),),
        ('rdl.3',):((74,20),(76,20)),
        ('rdl.5',):((74,20),(93,0)),
    }
    for names,selectors in groups.items():
        if rule in names:return selectors
    # Each of these table rows constrains a named marked operand. Their source
    # tables are identity-checked below; table-name matching is never coverage.
    table=Path(row['source']).name
    by_table={
        'p030-varac_dotdash.csv':('Var_channel',),
        'p036-capm_dotdash.csv':((89,44),),
        'p037-vpp_dotdash.csv':((82,64),),
        'p043-indm_dotdash.csv':((82,24),),
        'p046-mf_dotdash.csv':((71,17),(76,44)),
        'p056-pwres_dotdash_dotdash.csv':((64,13),),
    }
    return by_table.get(table)


def review_row(row, counts):
    flags=set(row['flags']);state='execution-review-required';reason='No executable per-rule semantic binding has been established.';witnesses={}
    if 'CU' in flags:
        state='other-backend';reason='Published CU flag; this captured profile uses the aluminium backend.'
    elif flags&{'NC','RR'}:
        state='advisory';reason='Published '+','.join(sorted(flags&{'NC','RR'}))+' flag. Retained as a guideline; not promoted to an executed pass.'
    elif row['value'].upper() in ('N/A','NA'):
        state='upstream-na';reason='The pinned source explicitly supplies NA/N/A; no numeric requirement or executed pass is invented.'
    elif 'F' in flags and all(counts.get(str(pair))==0 for pair in ((81,10),(81,12))):
        state='absent-operand';reason='Frame-only constraint; both frame and module identifiers are absent from this block.'
        witnesses={str(pair):counts[str(pair)] for pair in ((81,10),(81,12))}
    elif row['rule']=='x.20':
        state='definition-required';reason='IP_block pin-centre spacing is described, but the pinned table supplies no value or unit.'
    elif row['rule']=='x.17':
        state='advisory';reason='The pinned description explicitly says the floating-label warning is not a gate for tapeout. It is retained, not claimed executed.'
    else:
        selectors=selector_for(row)
        if selectors is not None:
            witnesses={str(key):counts.get(str(key)) for key in selectors}
            if all(value==0 for value in witnesses.values()):
                state='absent-operand';reason='Every explicitly reviewed operand is absent in the measured final GDS; this is not a passing non-empty rule test.'
            else:reason='An operand is present or its measurement is missing; the absent-operand disposition is refused.'
    return dict(id=row['id'],rule=row['rule'],source=row['source'],record=row['record'],
                source_sha256=row['source_sha256'],disposition=state,reason=reason,witnesses=witnesses)


def source_rows(source):
    source=Path(source);data=(source/'source-lock.json').read_bytes()
    if hashlib.sha256(data).hexdigest()!=SOURCE_LOCK_SHA256:raise ValueError('Unexpected source lock.')
    lock=json.loads(data);rows=[]
    for name,identity in sorted(lock['files'].items()):
        path=(source/name).resolve()
        if not path.is_relative_to(source.resolve()):raise ValueError('Source path outside captured root.')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=identity['sha256']:raise ValueError('Changed captured source: '+name)
        if re.fullmatch(r'docs/rules/periphery/p\d{3}-.+\.csv',name):
            rows.extend(manual_rows(raw,name))
    if len(rows)!=601 or len({r['id'] for r in rows})!=601:raise ValueError('Incomplete manual inventory.')
    return rows


def audit(path,source):
    rows=source_rows(source);path=Path(path);layout=k.Layout();layout.read(str(path))
    if len(layout.top_cells())!=1 or abs(layout.dbu-.001)>1e-12:raise ValueError('Expected one top and a 1 nm database grid.')
    top=layout.top_cell()
    def region(pair):return k.Region(top.begin_shapes_rec(layout.layer(*pair))).merged()
    selectors={(81,10),(81,12)}
    for row in rows:selectors.update(selector_for(row) or ())
    counts={str(pair):region(pair).count() for pair in selectors if isinstance(pair,tuple)}
    counts['Var_channel']=(region((66,20))&region((65,44))&(region((64,20))-region((75,20)))-region((81,2))).count()
    counts['prec_resistor']=(region((86,20))&region((66,20)).interacting(region((66,13)))&region((94,20))).count()
    counts['nwell_holes']=sum(p.holes() for p in region((64,20)).each())
    counts['advSeal_6um_cells']=sum(c.name.startswith('advSeal_6um') for c in layout.each_cell())
    counts['tap_interacting_diff']=tap_interactions(region((65,20)),region((65,44)))
    counts['gates_outside_sc']=gates_outside_standard_cells(region((65,20)),region((66,20)),region((81,4)))
    counts.update(named_cell_counts([c.name for c in layout.each_cell()]))
    counts['slotted_licon']=sum(p.is_box() and sorted((p.bbox().width(),p.bbox().height()))==[190,2000] for p in region((66,44)).each())
    texts=[];it=top.begin_shapes_rec(layout.layer(83,44))
    while not it.at_end():
        if it.shape().is_text():texts.append(it.shape().text.string)
        it.next()
    counts['dummy_poly_labels']=sum(text=='dummy_poly' for text in texts)
    # These special-purpose labels can be placed on different drawing/text
    # purposes. Search every layer, recursively, rather than assuming 83:44.
    label_counts=Counter()
    for layer in layout.layer_indexes():
        it=top.begin_shapes_rec(layer);it.shape_flags=k.Shapes.STexts
        while not it.at_end():
            label_counts[it.shape().text.string]+=1
            it.next()
    counts.update(special_label_counts(label_counts.elements()))
    reviewed=[review_row(row,counts) for row in rows]
    return dict(schema=1,status='partial-applicability-review',qualified=False,chunk_complete=False,
        gds_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),top=top.name,
        source_revision=REVISION,source_lock_sha256=SOURCE_LOCK_SHA256,
        checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        operand_counts=dict(sorted(counts.items())),counts=dict(Counter(r['disposition'] for r in reviewed)),rows=reviewed,
        scope='Periphery applicability only. An absent operand is a block-specific proof, not device qualification. Native execution, error-catalog reconciliation, density interpretation and electrical acceptance remain separate.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('gds',type=Path);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=audit(a.gds,a.source);a.output.write_bytes((json.dumps(result,indent=2)+'\n').encode())
    print(json.dumps({key:value for key,value in result.items() if key not in ('rows','operand_counts')}))
