"""Beacon Run lessons share an editable VGA project and one regression bench."""

from .model import example, validate

STARTER = 'beacon_run'
FILE_NAMES = ('beacon_timing.v','beacon_game.v','beacon_run.v','beacon_tb.sv')
TOPIC = 'Beacon Run · VGA Playground'

COLORS = '''if (upper_left) rgb = 6'b11_00_00;
else if (upper_right) rgb = 6'b00_11_00;
else if (lower_left) rgb = 6'b00_00_11;
else if (lower_right) rgb = 6'b11_11_00;'''
BOARD = '''if (rover) rgb = 6'b00_11_11;
else if (beacon) rgb = 6'b11_10_00;
else if (home) rgb = 6'b00_10_00;
else if (upper_left) rgb = 6'b11_00_00;'''
MOVE = '''if (buttons[0] && !buttons[1] && rover_x > 1) next_x = rover_x - 1'b1;
else if (buttons[1] && !buttons[0] && rover_x < 78) next_x = rover_x + 1'b1;
if (buttons[2] && !buttons[3] && rover_y > 1) next_y = rover_y - 1'b1;
else if (buttons[3] && !buttons[2] && rover_y < 58) next_y = rover_y + 1'b1;'''
FINISH = '''// Replace from `end else if (frame_tick)` through its matching end.
end else if (frame_tick) begin
  if (buttons[4]) begin
    rover_x <= 8; rover_y <= 8; obstacle_x <= 30;
    collected <= 0; won <= 0;
  end else if (!won) begin
    obstacle_x <= next_obstacle;
    if (hit_obstacle) begin
      rover_x <= 8; rover_y <= 8;
      collected <= 0;
    end else begin
      rover_x <= next_x; rover_y <= next_y;
      collected <= collected | touched;
      if (entered_home && (&collected)) won <= 1;
    end
  end
end

// In beacon_run.v, replace the first 'if (rover)' with these lines.
if (won && !border) rgb = 6'b00_11_00;
else if (obstacle) rgb = 6'b11_00_00;
else if (rover) rgb = 6'b00_11_11;'''

# Key, title, engineering target, prediction, options, concept, editor steps, solution.
STAGES = (
    ('timing', 'Draw a VGA test card',
     'Produce a 640 × 480 active image inside an 800 × 525 raster. Use 96 clocks of active-low HSync, two lines of active-low VSync, black blanking, and a distinct marker in each corner.',
     'What happens to RGB outside the visible raster?', ('It is driven to black.', 'It repeats the last pixel.', 'It carries the rover position.'),
     'Horizontal and vertical counters define where a pixel lands. Sync pulses mark scan boundaries and blanking hides porch and sync pixels.',
     ['Open beacon_timing.v. Set the active-low HSync interval to 656 ≤ x < 752.',
      'Open beacon_run.v. Color upper-right green, lower-left blue, and lower-right yellow. Keep the corners above the border in the priority chain.',
      'Open VGA Playground. Look for all four colors and a continuous gray border.'],
     'assign hsync = !(x >= 656 && x < 752);\n\n'+COLORS),
    ('board', 'Draw the board and rover',
     'Draw a cyan rover on the home tile, amber beacons at (12,8), (12,12) and (8,12), and a green home pad. Preserve the working border, corners and blanking.',
     'Which object should win when the rover is on the home pad?', ('The rover.', 'The home pad.', 'Both colors are added together.'),
     'Taking x and y above bit 2 divides the raster into 8 × 8 pixel tiles. Comparing tile coordinates gives the renderer and collision rules the same grid.',
     ['Open beacon_run.v. Inspect the tile coordinates and the rover, beacon and home signals.',
      'Place rover, beacon and home in that priority order before the corner and border colors. Check the emerald pad and cyan rover values in the solution if needed.',
      'Open VGA Playground and locate the three amber tiles around the rover.'], BOARD),
    ('movement', 'Move once per frame',
     'Use input bits 0–3 as left, right, up and down. Cancel opposing keys on each axis. Move by one tile per frame and clamp the rover to x=1–78 and y=1–58.',
     'Why update position on a frame tick?', ('It stays fixed during the scan.', 'RGB only works at a lower clock rate.', 'The buttons generate the VGA clock.'),
     'A one-clock frame-enable pulse gates the game state. Separate horizontal and vertical decisions allow diagonal motion while opposites cancel.',
     ['Open beacon_game.v. Keep next_x and next_y defaulted to the current position.',
      'Update each axis only for an exclusive button and a legal destination. Keep the actual register writes inside frame_tick.',
      'Use the preview input toggles. Turn the bits off to stop. Test opposing buttons and both borders.'], MOVE),
    ('collect', 'Collect each beacon once',
     'When the rover enters a beacon tile, set the corresponding bit and hide the beacon. Holding contact for multiple frames must leave the same score.',
     'Which state distinguishes one visit from several frames of overlap?', ('A sticky bit per beacon.', 'The current pixel color.', 'A counter that increments every overlapping frame.'),
     'The bit mask stores which beacons have been visited. OR is idempotent, so repeated contact leaves the same mask.',
     ['In beacon_game.v, examine touched. It compares the destination tile with each beacon coordinate.',
      'Update collected with the bitwise union of the existing state and touched. The renderer already hides collected beacons.',
      'Draw three score slots using score_slot and score_lit. Move onto a beacon, stop, and check that the beacon stays hidden and its score slot stays lit.'],
     "collected <= collected | touched;\n\n// In beacon_run.v, insert this after the home condition.\n"
     "else if (score_slot) rgb = score_lit ? 6'b11_11_00 : 6'b01_01_01;"),
    ('finish', 'Finish, crash and restart the game',
     'Move the red obstacle. On collision, return the rover home and clear its beacons. Collect all three and return home to win. Freeze the scene on win until bit 4 restarts the game.',
     'Which action takes priority over movement and collision?', ('Restart.', 'Movement.', 'Rendering the border.'),
     'A priority chain gives simultaneous events a definitive result. Restart wins first, then a won game freezes, then collision wins over ordinary movement and collection.',
     ['In beacon_game.v, make restart reset the game first. Freeze when won. Advance the obstacle on other frames.',
      'Check collision against both next positions before moving the rover or accepting a beacon. Win when all three beacons are stored and the rover reaches home.',
      'In beacon_run.v, give the win state and red obstacle higher drawing priority than the rover. Play a complete round and restart with bit 4.'], FINISH),
)


def config():
    from .getting_started import resource_root

    root = resource_root()/'examples'/'student-hub'/'beacon-run'
    return dict(version=1, top=STARTER, testbench='beacon_tb', include_dirs=['.'], defines={},
                waveform='wave.vcd', timeout=60, files=[dict(path=name, role='testbench' if name.endswith('.sv') else 'rtl',
                    text=(root/name).read_text(encoding='utf-8')) for name in FILE_NAMES])


def project():
    p = example('empty')
    p['name'] = 'Student · Beacon Run'
    p['cells'][0].update(name=STARTER,digital=config())
    return validate(p)


def lessons():
    prior = ['d-logic']
    result = []
    for key,title,target,question,options,concept,_,_ in STAGES:
        ident = 'vga-beacon-'+key
        result.append(dict(id=ident,title=title,path='digital',topic=TOPIC,starter=STARTER,workspace='beacon-run',
            vga_lesson=key,requires=prior, minutes=25, summary=target,
            skills=['VGA Playground','Verilog','simulation'],doc='STUDENT_BEACON_RUN.md',steps=[
                dict(id='predict',kind='quiz',title='Predict the behavior',instructions=question,
                     options=list(options),answer=0,explanation=concept),
                dict(id='verify',kind='check',title='Run the video and game regression',instructions=target,
                     rule=dict(type='digital',design=STARTER,checkpoint=key)),
                dict(id='reflect',kind='reflection',title='Record what you verified',instructions=
                     'Describe a preview or waveform observation and the test that backs it up. Include the input, expected outcome and observed result.')]))
        prior = [ident]
    return result


def stage(key):
    return next(item for item in STAGES if item[0]==key)


def teaching(key):
    _,_,target,_,_,concept,_,_ = stage(key)
    return dict(concept=concept,worked_example=target,
                try_next='Change one condition, predict the resulting frame or game state, and replay it.',
                interview='Which logic implements the decision, and which test proves it is made on the intended clock?',
                artifact='Save the project and keep a frame screenshot or waveform with the matching passing regression log.')


def hints(key):
    _,_,target,_,_,concept,edits,_ = stage(key)
    return {'predict':[('Which idea applies?',concept),('Where is the behavior defined?',edits[0]),
                       ('What should I see?',target),('How can I test this?', 'Replay a controlled case in the preview, then run the saved regression.')]}


def practice(key):
    _,_,target,_,_,concept,edits,solution = stage(key)
    controls = ['Choose Open RTL and complete the marked section.',*edits,
                'Apply sources, choose Run lesson, and inspect the saved run. Select Check this step.']
    return dict(tasks={'verify':[target,controls,concept]},questions={},code={'verify':solution})
