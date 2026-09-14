"""Authoritative instance and terminal records read from the captured OpenDB."""
import json


def script(output):
    from .engines import tcl_word
    return r'''
proc studio_json {value} {
  return "\"[string map [list "\\" "\\\\" "\"" "\\\"" "\n" "\\n" "\t" "\\t" "\r" "\\r"] $value]\""
}
set block [[ord::get_db] getChip]
set block [$block getBlock]
set units [$block getDbUnitsPerMicron]
set out [open OUTPUT w]
puts $out "\{\"version\":1,\"instances\":\["
set separator ""
foreach inst [$block getInsts] {
  set bbox [$inst getBBox]
  puts $out "$separator\{\"name\":[studio_json [$inst getName]],\"database_id\":[$inst getId],\"master\":[studio_json [[$inst getMaster] getName]],\"orientation\":[studio_json [$inst getOrient]],\"bbox\":\[[$bbox xMin],[$bbox yMin],[$bbox xMax],[$bbox yMax]\],\"pins\":\["
  set pin_separator ""
  foreach pin [$inst getITerms] {
    set net [$pin getNet]
    set net_name ""
    if {$net != "NULL"} {set net_name [$net getName]}
    puts $out "$pin_separator\{\"name\":[studio_json [[$pin getMTerm] getName]],\"net\":[studio_json $net_name],\"direction\":[studio_json [[$pin getMTerm] getIoType]]\}"
    set pin_separator ","
  }
  puts $out "\]\}"
  set separator ","
}
puts $out "\],\"dbu_per_micron\":$units\}"
close $out
'''.replace('OUTPUT', tcl_word(str(output)))


def merge_preview(preview, path):
    data=json.loads(path.read_text());scale=data['dbu_per_micron'];records=[]
    for item in data['instances']:
        x1,y1,x2,y2=item['bbox']
        records.append({**item,'x':x1/scale,'y':y1/scale,'width':(x2-x1)/scale,'height':(y2-y1)/scale})
    preview['components']=records;preview['database']='OpenDB checkpoint'
    return preview
