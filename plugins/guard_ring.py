"""Example worker: reads a snapshot; emits commands; never edits project files."""
import json,sys,uuid
p=json.load(sys.stdin);commands=[]
for x,y,w,h in [(0,0,6000,300),(0,4700,6000,300),(0,300,300,4400),(5700,300,300,4400)]:
 commands.append({'type':'add_shape','cell_id':p['top'],'shape':{'id':uuid.uuid4().hex[:16],'kind':'rect','layer':'metal1','points':[[x,y],[x+w,y+h]],'net':'0','device_id':''}})
json.dump(commands,sys.stdout)
