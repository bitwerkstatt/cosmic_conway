import micropython
import random
import time
from cosmic import CosmicUnicorn
from picographics import PicoGraphics, DISPLAY_COSMIC_UNICORN

# --- Konstanten ---
WIDTH  = CosmicUnicorn.WIDTH   # 32
HEIGHT = CosmicUnicorn.HEIGHT  # 32
TICK_MS     = 100             # Millisekunden pro Generation (Schrittweite)
TICK_MIN_MS = 100
TICK_MAX_MS = 2000

CYCLE_MAX_PERIOD  = 20                              # maximale Periode, die erkannt wird
CYCLE_MIN_REPEATS = 3                               # mehr als zwei Wiederholungen nötig
HISTORY_SIZE      = CYCLE_MAX_PERIOD * CYCLE_MIN_REPEATS

# --- Hardware initialisieren ---
cu = CosmicUnicorn()
graphics = PicoGraphics(display=DISPLAY_COSMIC_UNICORN)

cu.set_brightness(0.5)

# --- Farben als Pen-Werte ---
BLACK = graphics.create_pen(0, 0, 0)

# Paletten: (BORN-Farbe, ALIVE-Farbe)
PALETTES = [
    (graphics.create_pen(0, 255, 180),   graphics.create_pen(0, 200, 80)),    # Cyan / Grün
    (graphics.create_pen(255, 255, 0),   graphics.create_pen(255, 140, 0)),   # Gelb / Orange
    (graphics.create_pen(255, 150, 200), graphics.create_pen(220, 20, 60)),   # Rosa / Rot
    (graphics.create_pen(200, 0, 255),   graphics.create_pen(0, 100, 255)),   # Violett / Blau
    (graphics.create_pen(255, 220, 80),  graphics.create_pen(200, 0, 0)),     # Feuer
    (graphics.create_pen(220, 240, 255), graphics.create_pen(60, 140, 255)),  # Eis
    (graphics.create_pen(180, 255, 180), graphics.create_pen(0, 140, 0)),     # Matrix
    (graphics.create_pen(255, 255, 150), graphics.create_pen(200, 100, 0)),   # Gold
    (graphics.create_pen(100, 220, 255), graphics.create_pen(0, 40, 180)),    # Ozean
    (graphics.create_pen(255, 150, 255), graphics.create_pen(180, 0, 200)),   # Magenta
]

BORN, ALIVE = PALETTES[0]


# --- Hilfsfunktionen ---

@micropython.native
def make_grid() -> list[list[int]]:
    """Gibt ein leeres WIDTH×HEIGHT-Raster zurück."""
    return [[0] * WIDTH for _ in range(HEIGHT)]


def randomize(grid: list[list[int]], density: float = 0.35) -> None:
    """Befüllt das Raster zufällig mit lebenden Zellen und wählt eine zufällige Palette."""
    global BORN, ALIVE
    BORN, ALIVE = PALETTES[random.randint(0, len(PALETTES) - 1)]
    for y in range(HEIGHT):
        for x in range(WIDTH):
            grid[y][x] = 1 if random.random() < density else 0


@micropython.native
def count_neighbours(grid, x: int, y: int) -> int:
    """Zählt lebende Nachbarn (toroidal, d.h. die Ränder wickeln sich um)."""
    total = int(0)
    W = int(WIDTH)
    H = int(HEIGHT)
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            if dx == 0 and dy == 0:
                continue
            nx = (x + dx + W) % W
            ny = (y + dy + H) % H
            total += int(grid[ny][nx]) & 1
    return total


@micropython.native
def step(current, nxt) -> None:
    """Berechnet eine Generation von Conway's Game of Life."""
    H = int(HEIGHT)
    W = int(WIDTH)
    for y in range(H):
        for x in range(W):
            alive = int(current[y][x]) & 1
            n = count_neighbours(current, x, y)
            if alive:
                nxt[y][x] = 1 if n == 2 or n == 3 else 0
            else:
                nxt[y][x] = 1 if n == 3 else 0


@micropython.native
def draw(grid: list[list[int]], prev: list[list[int]]) -> None:
    """Zeichnet das aktuelle Raster auf das Display."""
    graphics.set_pen(BLACK)
    graphics.clear()
    

    for y in range(HEIGHT):
        for x in range(WIDTH):
            cur  = grid[y][x]
            was  = prev[y][x]
            if cur and not was:
                pen = BORN
            elif cur:
                pen = ALIVE
            else:
                continue
            graphics.set_pen(pen)
            graphics.pixel(x, y)

    cu.update(graphics)


@micropython.native
def population(grid) -> int:
    """Gibt die Anzahl lebender Zellen zurück."""
    total = int(0)
    H = int(HEIGHT)
    W = int(WIDTH)
    for y in range(H):
        row = grid[y]
        for x in range(W):
            total += int(row[x])
    return total


@micropython.native
def is_cyclic(history) -> bool:
    """True, wenn die Population einen sich wiederholenden Zyklus bildet."""
    n = int(len(history))
    max_period = int(CYCLE_MAX_PERIOD)
    min_repeats = int(CYCLE_MIN_REPEATS)
    for period in range(1, max_period + 1):
        needed = period * min_repeats
        if n < needed:
            continue
        offset = n - needed
        cyclic = int(1)
        for i in range(period, needed):
            if int(history[offset + i]) != int(history[offset + i % period]):
                cyclic = int(0)
                break
        if cyclic:
            return True
    return False


def handle_buttons(paused: bool, tick_ms: int) -> tuple[bool, int]:
    """Verarbeitet Knopfeingaben, gibt neuen paused-Zustand und Tick-Zeit zurück."""
    if cu.is_pressed(CosmicUnicorn.SWITCH_BRIGHTNESS_UP):
        cu.adjust_brightness(+0.05)
    if cu.is_pressed(CosmicUnicorn.SWITCH_BRIGHTNESS_DOWN):
        cu.adjust_brightness(-0.05)
    if cu.is_pressed(CosmicUnicorn.SWITCH_A):
        paused = not paused
        time.sleep_ms(200)
    if cu.is_pressed(CosmicUnicorn.SWITCH_C):
        tick_ms = max(TICK_MIN_MS, tick_ms - TICK_MS)
        time.sleep_ms(200)
    if cu.is_pressed(CosmicUnicorn.SWITCH_D):
        tick_ms = min(TICK_MAX_MS, tick_ms + TICK_MS)
        time.sleep_ms(200)
    return paused, tick_ms


# --- Zustand ---
grid  = make_grid()
nxt   = make_grid()
prev  = make_grid()
randomize(grid)

paused     = False
tick_ms    = TICK_MS
pop_history: list[int] = []

# --- Hauptschleife ---
while True:
    # Knöpfe: A pausiert, B startet neu, C schneller, D langsamer
    if cu.is_pressed(CosmicUnicorn.SWITCH_B):
        randomize(grid)
        pop_history.clear()
        time.sleep_ms(300)

    paused, tick_ms = handle_buttons(paused, tick_ms)

    if not paused:
        step(grid, nxt)
        draw(nxt, grid)
        # Puffer rotieren (kein Speicher allokieren)
        grid, nxt, prev = nxt, prev, grid

        pop_history.append(population(grid))
        if len(pop_history) > HISTORY_SIZE:
            pop_history.pop(0)
        if is_cyclic(pop_history):
            randomize(grid)
            pop_history.clear()

    time.sleep_ms(tick_ms)
