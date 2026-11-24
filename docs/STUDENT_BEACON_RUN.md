# Beacon Run in the VGA Playground

Open **Student Hub → Digital → Beacon Run · VGA Playground**. Five lessons
share the same Verilog sources and project. A working raster scaffold starts
with a timing error and unfinished game logic. No external hardware is required.
**Step by step** walks through each edit. **Show solution** gives the matching
Verilog. **Do it yourself** gives the behavior to implement and verify.

| Lesson | Build | Verify |
| --- | --- | --- |
| Draw a VGA test card | 640 × 480 active display, border, and four color markers | Check HSync, VSync, blanking and frame wrap over all 420,000 pixels in the raster. |
| Draw the board and rover | 8 × 8 pixel tiles for the rover, beacons and home | Inspect colors at the coordinates that the game logic uses. The rover takes drawing priority over home. |
| Move once per frame | Input decoding and position registers with border guards | Check held input, opposing directions, diagonal movement and the four limits. |
| Collect each beacon once | Three sticky collection bits, hidden collected beacons, and a three-slot score display | Hold the rover on one beacon and confirm the scoreboard counts it once. |
| Finish, crash and restart the game | Moving obstacle, collision reset, frozen win state, and restart | Replay the collection loop, return home, collide with the obstacle and restart. |

Use **Open VGA Playground** in the guide to see the active RTL. The game uses
input bits 0, 1, 2, and 3 for left, right, up, and down. Bit 4 restarts. Turn
off an input bit to stop moving. Use **Apply sources**, then **Run lesson** to
run the Icarus regression and **Check this step** to save the checkpoint. The
reference bench includes a complete frame and a game state replay with controlled
frame ticks. It records a separate pass marker for each completed milestone.

For the final evidence, save your project, capture the preview on the win
screen, and keep the passing run with your explanation of rule priority.
The same sources can then be used in Digital Flow to explore synthesis.
