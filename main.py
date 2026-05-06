import micropython
import random
import time
from cosmic import CosmicUnicorn
from picographics import PicoGraphics, DISPLAY_COSMIC_UNICORN

# --- Constants ---
WIDTH  = CosmicUnicorn.WIDTH   # 32
HEIGHT = CosmicUnicorn.HEIGHT  # 32

# Padded grid: 1-cell halo on every side gives toroidal wrap-around
# without modulo arithmetic in the inner loop (the RP2040 has no HW divider).
PAD_W    = WIDTH + 2   # 34
PAD_H    = HEIGHT + 2  # 34
PAD_SIZE = PAD_W * PAD_H

TICK_MS     = 100   # milliseconds per generation
TICK_MIN_MS = 100
TICK_MAX_MS = 2000

CYCLE_MAX_PERIOD  = 20
CYCLE_MIN_REPEATS = 3
HISTORY_SIZE      = CYCLE_MAX_PERIOD * CYCLE_MIN_REPEATS

# Button input timing.
BTN_DEBOUNCE_MS    = 180   # rising-edge debounce window
BRIGHTNESS_RATE_MS = 80    # repeat rate while a brightness button is held

# --- Hardware ---
cu = CosmicUnicorn()
graphics = PicoGraphics(display=DISPLAY_COSMIC_UNICORN)
cu.set_brightness(0.5)

# --- Colours ---
BLACK = graphics.create_pen(0, 0, 0)

# Palettes: (BORN pen, ALIVE pen)
PALETTES = [
    (graphics.create_pen(0, 255, 180),   graphics.create_pen(0, 200, 80)),    # Cyan / Green
    (graphics.create_pen(255, 255, 0),   graphics.create_pen(255, 140, 0)),   # Yellow / Orange
    (graphics.create_pen(255, 150, 200), graphics.create_pen(220, 20, 60)),   # Pink / Red
    (graphics.create_pen(200, 0, 255),   graphics.create_pen(0, 100, 255)),   # Violet / Blue
    (graphics.create_pen(255, 220, 80),  graphics.create_pen(200, 0, 0)),     # Fire
    (graphics.create_pen(220, 240, 255), graphics.create_pen(60, 140, 255)),  # Ice
    (graphics.create_pen(180, 255, 180), graphics.create_pen(0, 140, 0)),     # Matrix
    (graphics.create_pen(255, 255, 150), graphics.create_pen(200, 100, 0)),   # Gold
    (graphics.create_pen(100, 220, 255), graphics.create_pen(0, 40, 180)),    # Ocean
    (graphics.create_pen(255, 150, 255), graphics.create_pen(180, 0, 200)),   # Magenta
]

born_pen, alive_pen = PALETTES[0]


# --- Helpers ---

def randomize(buf, density: float = 0.35) -> None:
    """Reset the padded buffer and seed it with random live cells. Picks a random palette."""
    global born_pen, alive_pen
    born_pen, alive_pen = PALETTES[random.randint(0, len(PALETTES) - 1)]
    for i in range(PAD_SIZE):
        buf[i] = 0
    for y in range(1, HEIGHT + 1):
        row = y * PAD_W
        for x in range(1, WIDTH + 1):
            buf[row + x] = 1 if random.random() < density else 0


@micropython.native
def update_halo(buf) -> None:
    """Mirror real edges into the halo so the inner step loop can wrap without modulo."""
    PW = PAD_W
    H  = HEIGHT
    W  = WIDTH
    # Left/right halo columns for the real rows.
    for y in range(1, H + 1):
        row = y * PW
        buf[row]         = buf[row + W]      # left halo  <- rightmost real cell
        buf[row + W + 1] = buf[row + 1]      # right halo <- leftmost real cell
    # Top/bottom halo rows (full width — picks up the corners just written).
    top_halo = 0
    top_real = PW
    bot_real = H * PW
    bot_halo = (H + 1) * PW
    for x in range(PW):
        buf[top_halo + x] = buf[bot_real + x]
        buf[bot_halo + x] = buf[top_real + x]


@micropython.native
def step(curr, nxt) -> int:
    """Compute one generation of Conway's Game of Life.

    Reads bit 0 of `curr` (the live state), writes into `nxt` with:
      bit 0 = cell alive after this step
      bit 1 = cell was alive before this step (used for the BORN highlight)
    Returns a 32-bit hash of the new live grid for cycle detection.
    """
    PW = PAD_W
    H  = HEIGHT
    W  = WIDTH
    h  = 0
    for y in range(1, H + 1):
        row_top = (y - 1) * PW
        row_mid = y * PW
        row_bot = (y + 1) * PW
        for x in range(1, W + 1):
            n = (curr[row_top + x - 1] & 1) + (curr[row_top + x] & 1) + (curr[row_top + x + 1] & 1) \
              + (curr[row_mid + x - 1] & 1)                           + (curr[row_mid + x + 1] & 1) \
              + (curr[row_bot + x - 1] & 1) + (curr[row_bot + x] & 1) + (curr[row_bot + x + 1] & 1)
            old = curr[row_mid + x] & 1
            if old:
                new = 1 if (n == 2 or n == 3) else 0
            else:
                new = 1 if n == 3 else 0
            nxt[row_mid + x] = new | (old << 1)
            h = ((h * 31) + new) & 0xFFFFFFFF
    return h


@micropython.native
def draw(buf) -> None:
    """Render the grid in two pen passes (alive, born). Minimises pen switches."""
    PW  = PAD_W
    H   = HEIGHT
    W   = WIDTH
    g   = graphics
    bp  = born_pen
    ap  = alive_pen
    blk = BLACK

    g.set_pen(blk)
    g.clear()

    # Pass 1: cells that survived (alive both before and after).
    g.set_pen(ap)
    for y in range(H):
        row = (y + 1) * PW + 1
        for x in range(W):
            if (buf[row + x] & 0b11) == 0b11:
                g.pixel(x, y)

    # Pass 2: cells that were born this step (alive now, dead before).
    g.set_pen(bp)
    for y in range(H):
        row = (y + 1) * PW + 1
        for x in range(W):
            if (buf[row + x] & 0b11) == 0b01:
                g.pixel(x, y)

    cu.update(g)


@micropython.native
def is_cyclic(history) -> bool:
    """Return True when the trailing values in `history` repeat with some period <= CYCLE_MAX_PERIOD."""
    n           = len(history)
    max_period  = CYCLE_MAX_PERIOD
    min_repeats = CYCLE_MIN_REPEATS
    for period in range(1, max_period + 1):
        needed = period * min_repeats
        if n < needed:
            continue
        offset = n - needed
        match  = True
        for i in range(period, needed):
            if history[offset + i] != history[offset + i % period]:
                match = False
                break
        if match:
            return True
    return False


# --- Buttons (non-blocking, edge-debounced) ---

_btn_state      = {}
_btn_last_press = {}


def button_pressed(btn, debounce_ms: int = BTN_DEBOUNCE_MS) -> bool:
    """True only on the rising edge of `btn`, after the debounce window has passed."""
    pressed = cu.is_pressed(btn)
    was = _btn_state.get(btn, False)
    _btn_state[btn] = pressed
    if pressed and not was:
        now = time.ticks_ms()
        last = _btn_last_press.get(btn, 0)
        if time.ticks_diff(now, last) > debounce_ms:
            _btn_last_press[btn] = now
            return True
    return False


# --- State ---
grid = bytearray(PAD_SIZE)
nxt  = bytearray(PAD_SIZE)
randomize(grid)

paused       = False
tick_ms      = TICK_MS
hash_history = []

last_step_t       = time.ticks_ms()
last_brightness_t = 0

# --- Main loop ---
# Buttons: A pauses, B reseeds, C speeds up, D slows down, +/- adjust brightness.
while True:
    now = time.ticks_ms()

    if button_pressed(CosmicUnicorn.SWITCH_A):
        paused = not paused
    if button_pressed(CosmicUnicorn.SWITCH_B):
        randomize(grid)
        hash_history.clear()
    if button_pressed(CosmicUnicorn.SWITCH_C):
        tick_ms = max(TICK_MIN_MS, tick_ms - TICK_MS)
    if button_pressed(CosmicUnicorn.SWITCH_D):
        tick_ms = min(TICK_MAX_MS, tick_ms + TICK_MS)

    if time.ticks_diff(now, last_brightness_t) > BRIGHTNESS_RATE_MS:
        if cu.is_pressed(CosmicUnicorn.SWITCH_BRIGHTNESS_UP):
            cu.adjust_brightness(+0.05)
            last_brightness_t = now
        elif cu.is_pressed(CosmicUnicorn.SWITCH_BRIGHTNESS_DOWN):
            cu.adjust_brightness(-0.05)
            last_brightness_t = now

    if not paused and time.ticks_diff(now, last_step_t) >= tick_ms:
        update_halo(grid)
        h = step(grid, nxt)
        grid, nxt = nxt, grid
        draw(grid)

        hash_history.append(h)
        if len(hash_history) > HISTORY_SIZE:
            hash_history.pop(0)

        if is_cyclic(hash_history):
            randomize(grid)
            hash_history.clear()

        last_step_t = now

    time.sleep_ms(5)
