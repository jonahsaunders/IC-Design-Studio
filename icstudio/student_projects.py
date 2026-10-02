"""Small editable labs, with independent reference testbenches for RTL lessons."""
from .model import clone, device, example, uid, validate
from .student_design_labs import DIGITAL_LABS

DIGITAL = {
    'gates': ('input wire a,b,select, output wire parity,mux',
              'assign parity = a ^ b; assign mux = select ? b : a;',
              'reg a,b,select; wire parity,mux; integer i;', 'a,b,select,parity,mux',
              '''for (i=0;i<8;i=i+1) begin
                {select,b,a}=i; #2;
                if (parity !== (a ^ b) || mux !== (select ? b : a)) $fatal(1,"Truth table mismatch");
              end'''),
    'counter': ('input wire clk,reset,enable, output reg [3:0] count',
                'always @(posedge clk) if(reset) count<=0; else if(enable) count<=count+1;',
                'reg clk=0,reset=1,enable=0; wire [3:0] count; integer i,expected; always #5 clk=~clk;', 'clk,reset,enable,count',
                '''repeat(2) @(negedge clk); reset=0; expected=0;
                for(i=0;i<40;i=i+1) begin
                  enable=(i%3!=0); @(posedge clk); #1;
                  if(enable) expected=(expected+1)%16;
                  if(count !== expected[3:0]) $fatal(1,"Counter enable/wrap mismatch");
                  @(negedge clk);
                end
                reset=1; @(posedge clk); #1; if(count !== 0) $fatal(1,"Reset mismatch");'''),
    'pulse': ('input wire clk,reset,request, output reg pulse',
              '''reg previous;
              always @(posedge clk) if(reset) begin previous<=0; pulse<=0; end
              else begin pulse<=request && !previous; previous<=request; end''',
              'reg clk=0,reset=1,request=0; wire pulse; integer i; reg previous,expected; always #5 clk=~clk;', 'clk,reset,request,pulse',
              '''repeat(2) @(negedge clk); reset=0; previous=0;
              for(i=0;i<20;i=i+1) begin
                request=(i%5<3); expected=request && !previous;
                @(posedge clk); #1; if(pulse !== expected) $fatal(1,"Pulse width or edge mismatch");
                previous=request; @(negedge clk);
              end'''),
    'pwm': ('input wire clk,reset, input wire [2:0] duty, output wire pwm',
            'reg [2:0] phase; always @(posedge clk) if(reset) phase<=0; else phase<=phase+1; assign pwm=(phase<duty);',
            'reg clk=0,reset=1; reg [2:0] duty=0; wire pwm; integer d,i,ones; always #5 clk=~clk;', 'clk,reset,duty,pwm',
            '''repeat(2) @(negedge clk); reset=0;
            for(d=0;d<8;d=d+1) begin
              duty=d; ones=0;
              for(i=0;i<8;i=i+1) begin @(posedge clk); #1; if(pwm===1) ones=ones+1; else if(pwm!==0) $fatal(1,"Unknown PWM"); @(negedge clk); end
              if(ones!=d) $fatal(1,"Duty mismatch");
            end'''),
    'average': ('input wire clk,reset,valid, input wire [3:0] data, output reg [3:0] average, output reg ready',
                '''reg [5:0] sum; reg [1:0] count;
                wire [5:0] total=sum+{2'b0,data};
                always @(posedge clk) begin
                  if(reset) begin sum<=0; count<=0; average<=0; ready<=0; end
                  else begin ready<=0; if(valid) begin
                    if(count==3) begin average<=(total+6'd2)>>2; ready<=1; sum<=0; count<=0; end
                    else begin sum<=total; count<=count+1; end
                  end end
                end''',
                'reg clk=0,reset=1,valid=0; reg [3:0] data=0; wire [3:0] average; wire ready; integer i,sum,count,expected; always #5 clk=~clk;', 'clk,reset,valid,data,average,ready',
                '''repeat(2) @(negedge clk); reset=0; sum=0; count=0;
                for(i=0;i<40;i=i+1) begin
                  valid=(i%3!=0); data=(i<24 ? i%16 : 15); expected=0;
                  if(valid) begin sum=sum+data; count=count+1; if(count==4) expected=1; end
                  @(posedge clk); #1;
                  if(ready !== expected[0]) $fatal(1,"Average handshake mismatch");
                  if(expected) begin
                    if(average !== ((sum+2)/4)) $fatal(1,"Rounding or overflow mismatch");
                    sum=0;count=0;
                  end
                  @(negedge clk);
                end'''),
    'serial': ('input wire clk,reset,start, input wire [7:0] data, output reg tx,busy',
               '''reg [9:0] frame; reg [3:0] bit_index;
               always @(posedge clk) begin
                 if(reset) begin tx<=1; busy<=0; frame<=10'h3ff; bit_index<=0; end
                 else if(!busy) begin
                   if(start) begin frame<={1'b1,data,1'b0}; tx<=0; busy<=1; bit_index<=0; end
                 end else begin
                   frame<={1'b1,frame[9:1]}; tx<=frame[1]; bit_index<=bit_index+1;
                   if(bit_index==8) begin tx<=1; busy<=0; end
                 end
               end''',
               'reg clk=0,reset=1,start=0; reg [7:0] data=0; wire tx,busy; integer word_index,i; reg [7:0] expected; always #5 clk=~clk;', 'clk,reset,start,data,tx,busy',
               '''repeat(2) @(negedge clk); reset=0;
               for(word_index=0;word_index<4;word_index=word_index+1) begin
                 data=(word_index==0 ? 8'h00 : word_index==1 ? 8'hff : word_index==2 ? 8'ha5 : 8'h3c); expected=data; start=1;
                 @(posedge clk); #1; if(tx!==0 || busy!==1) $fatal(1,"Start bit mismatch");
                 @(negedge clk); start=0; data=0;
                 for(i=0;i<8;i=i+1) begin @(posedge clk); #1; if(tx!==expected[i]) $fatal(1,"Serial bit mismatch"); @(negedge clk); end
                 @(posedge clk); #1; if(tx!==1 || busy!==0) $fatal(1,"Stop bit mismatch"); @(negedge clk);
               end
               start=1; @(negedge clk); reset=1; @(posedge clk); #1;
               if(tx!==1 || busy!==0) $fatal(1,"Mid-frame reset mismatch");'''),
}
DIGITAL.update(DIGITAL_LABS)


def digital_project(kind):
    ports, body, declarations, bindings, checks = DIGITAL[kind]
    p = example('empty'); p['name'] = 'Student lab · '+kind
    top = 'lab_'+kind
    p['cells'][0]['digital'] = dict(version=1, top=top, testbench='lab_tb', include_dirs=['.'], defines={},
        waveform='wave.vcd', timeout=60, files=[
            dict(path=kind+'.sv', role='rtl', text=f'module {top}({ports});\n{body}\nendmodule\n'),
            dict(path='lab_tb.sv', role='testbench', text=f'''`timescale 1ns/1ps
module lab_tb;
{declarations}
{top} dut({bindings});
initial begin
  $dumpfile("wave.vcd"); $dumpvars(0,lab_tb);
  {checks}
  $display("STUDENT_CHECKS PASS {kind}"); $finish;
end
initial begin #100000; $fatal(1,"Testbench timeout"); end
endmodule
''')])
    return validate(p)


def divider(loaded=False, hierarchy=False):
    p = example('empty'); p['name'] = 'Student divider'; c = p['cells'][0]
    rs = [device('R','R1',420,180,value='10k',nets={'p':'vin','n':'out'}),
          device('R','R2',650,300,value='10k',nets={'p':'out','n':'0'})]
    c['devices'] = [device('V','V1',180,180,value='1.8',nets={'p':'vin','n':'0'})]
    if hierarchy:
        child = dict(id=uid(),name='divider',ports=['IN','OUT','GND'],devices=rs,shapes=[])
        for d in rs:d['nets']={k:{'vin':'IN','out':'OUT','0':'GND'}[v] for k,v in d['nets'].items()}
        p['cells'].append(child)
        c['devices'].append(device('X','XDIV',420,180,cell=child['id'],nets={'IN':'vin','OUT':'out','GND':'0'}))
    else:c['devices'] += rs
    if loaded:c['devices'].append(device('R','Rload',850,300,value='10k',nets={'p':'out','n':'0'}))
    p['analysis']['type']='op';return validate(p)


def create(starter):
    from .example_schematics import arrange
    return arrange(_create(starter))


def _create(starter):
    if starter in DIGITAL_LABS:
        from .student_design_labs import faulty_digital
        return faulty_digital(starter)
    if starter.startswith('gmid-'):
        from .student_design_labs import mos_lab
        return mos_lab(starter)
    if starter.startswith('layout-'):
        from .student_design_labs import layout_lab
        return layout_lab(starter)
    if starter in DIGITAL:return digital_project(starter)
    if starter=='divider-build':
        p=divider();p['cells'][0]['devices']=[d for d in p['cells'][0]['devices'] if d['name']!='R2'];return p
    if starter=='load-build':return divider()
    if starter in ('divider','loaded-divider','hierarchy'):
        return divider(starter=='loaded-divider',starter=='hierarchy')
    if starter in ('rc','rc-ac'):
        p=example('rc');p['analysis'].update(stop='60u',step='100n')
        p['cells'][0]['devices'][0]['source']['period']='200u'
        if starter=='rc-ac':p['analysis'].update(type='ac',start='10',end='1meg',points=240)
        return validate(p)
    if starter in ('current_mirror','differential_pair','amplifier'):
        from .project_templates import create as template
        p,_,_=template(example('empty')['pdk'],starter)
        if starter=='amplifier':p['analysis'].update(type='ac',start='10',end='100meg',points=200)
        return p
    if starter=='layout':
        from .getting_started import example_copy,examples
        return example_copy(next(e for e in examples() if e['id']=='common-centroid'))
    if starter.startswith('sar'):
        from .sar_example import sar_project
        p=sar_project();c=p['mixed_signal']
        if starter=='sar-hold':c['stimuli']['vin']=[[0,.93],[3.5e-6,.93],[3.501e-6,.2]]
        elif starter=='sar-settling':
            c.update(period=1e-8,rise=1e-10,max_step=1e-10);c['stimuli']['vin']=[[0,.3]]
        elif starter=='sar-weight':next(d for d in p['cells'][0]['devices'] if d['name']=='Rbit3')['value']='20k'
        elif starter=='sar-repeat':
            c.pop('verification');c.update(cycles=18)
            c['inputs'][0]['values']=[int(i<2) for i in range(18)]
            c['inputs'][1]['values']=[int(i in (2,9)) for i in range(18)]
            c['stimuli']['vin']=[[0,.4],[8e-6,.4],[8.001e-6,1.2]]
        return validate(p)
    if starter=='capstone':
        from .student_capstone import project
        p=project()
        # Three explicit repair tasks, one per capstone milestone.
        next(d for d in p['cells'][0]['devices'] if d['name']=='Cfilter')['value']='1n'
        files=p['cells'][1]['digital']['files']
        files[0]['text']=files[0]['text'].replace('if (!cmp)','if (cmp)')
        files[1]['text']=files[1]['text'].replace('>> 2','>> 1')
        return p
    raise ValueError('Unknown student starter: '+starter)
