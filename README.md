# Cosmic Conway

Conway's Game of Life running on a [Pimoroni Cosmic Unicorn](https://shop.pimoroni.com/products/cosmic-unicorn) — a 32×32 RGB LED matrix driven by an RP2040 microcontroller. Written in MicroPython.

The simulation runs autonomously, detects when the population reaches a static or cyclic state, and automatically reseeds with a new random configuration and colour palette.

---

## Hardware

| Component | Detail |
|-----------|--------|
| Board | Pimoroni Cosmic Unicorn |
| MCU | RP2040 (dual-core Cortex-M0+, 264 KB SRAM) |
| Display | 32 × 32 RGB LED matrix (1 024 cells) |
| Firmware | MicroPython with Pimoroni's `cosmic` / `picographics` libraries |

---

## Controls

| Button | Action |
|--------|--------|
| **A** | Pause / resume the simulation |
| **B** | Reseed — randomise the grid and pick a new colour palette |
| **C** | Speed up — decrease the generation interval (minimum 100 ms) |
| **D** | Slow down — increase the generation interval (maximum 2 000 ms) |
| **Brightness +** | Increase display brightness (hold to ramp) |
| **Brightness −** | Decrease display brightness (hold to ramp) |

All buttons are edge-triggered with a 180 ms debounce window, so a single press always registers exactly once regardless of how long the button is held. Brightness adjustment repeats at ~12 Hz while held.

---

## Colour Palettes

Ten palettes are built in. Each palette defines two colours:

- **Born** — a cell that was dead last generation and is alive now
- **Alive** — a cell that was alive last generation and remains alive

A palette is chosen at random whenever the grid is reseeded (button B or automatic reseed after cycle detection).

| # | Name | Born colour | Alive colour |
|---|------|-------------|--------------|
| 1 | Cyan / Green | `#00FFB4` | `#00C850` |
| 2 | Yellow / Orange | `#FFFF00` | `#FF8C00` |
| 3 | Pink / Red | `#FF96C8` | `#DC143C` |
| 4 | Violet / Blue | `#C800FF` | `#0064FF` |
| 5 | Fire | `#FFDC50` | `#C80000` |
| 6 | Ice | `#DCF0FF` | `#3C8CFF` |
| 7 | Matrix | `#B4FFB4` | `#008C00` |
| 8 | Gold | `#FFFF96` | `#C86400` |
| 9 | Ocean | `#64DCFF` | `#0028B4` |
| 10 | Magenta | `#FF96FF` | `#B400C8` |

---

## Technical Architecture

### Grid representation

The live grid is stored as two flat `bytearray` buffers — `grid` (current generation) and `nxt` (next generation) — each of size `PAD_W × PAD_H` (34 × 34 = 1 156 bytes).

The extra ring of cells around the 32 × 32 live area is a **halo** used to implement toroidal (wrap-around) boundary conditions without modulo arithmetic. The RP2040 has no hardware divider, so avoiding `%` in the innermost loop gives a measurable speedup.

```
┌─────────────────────────────────────────┐
│  halo (mirrored border)  34 × 34        │
│  ┌───────────────────────────────────┐  │
│  │  live cells  32 × 32             │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

### Cell encoding (2-bit packing)

Each byte in `nxt` encodes two generations of state for the same cell:

| Bit 1 | Bit 0 | Meaning |
|-------|-------|---------|
| 0 | 0 | Dead — was dead last step |
| 0 | 1 | **Born** — alive now, was dead |
| 1 | 0 | Died — was alive, dead now |
| 1 | 1 | **Alive** — alive now, was alive |

This eliminates the need for a separate `prev` buffer. `draw()` reads both bits to select the correct pen colour without any extra memory.

### Simulation pipeline per tick

```
update_halo(grid)          # copy real edges into the 1-cell halo (64 + 68 writes)
h = step(grid, nxt)        # compute next generation; returns a 32-bit grid hash
grid, nxt = nxt, grid      # swap buffers — no allocation
draw(grid)                 # render to display
```

**`update_halo`** runs first and copies the four real edges — including corners — into the surrounding halo ring, so the inner step loop can look up all eight neighbours with plain array indexing.

**`step`** iterates every real cell, reads the eight neighbours from pre-computed row offsets (no per-neighbour index arithmetic), applies the standard Game of Life rules, and writes the 2-bit result into `nxt`. As a by-product of the same loop it accumulates a 32-bit rolling hash of the new generation's live pattern — used by the cycle detector at zero extra cost.

**`draw`** uses two pen passes over the 32 × 32 grid:
1. Set `alive_pen`, draw all `0b11` cells.
2. Set `born_pen`, draw all `0b01` cells.

This keeps the total number of `set_pen()` calls to 2 per frame instead of up to 1 024.

### Main loop timing

The loop runs continuously with a 5 ms idle sleep. Step timing is driven by `time.ticks_ms()` / `time.ticks_diff()`, so buttons are polled every ~5 ms regardless of the configured generation interval. This keeps the controls responsive even at the slowest speed (2 000 ms/generation).

```
while True:
    poll buttons              # always, every ~5 ms
    poll brightness buttons   # rate-limited to ~12 Hz
    if elapsed >= tick_ms:
        step + draw + cycle check
    sleep 5 ms
```

### Cycle detection

After every generation the 32-bit hash is appended to a history list (capped at 60 entries). The `is_cyclic()` function scans for any repeating period from 1 to 20 generations, requiring at least 3 consecutive full repetitions before triggering a reseed. Using a hash of the entire live grid (rather than just a population count) prevents false positives for patterns such as gliders, which have a constant population but a changing spatial layout.

---

## Installation

1. Flash your Cosmic Unicorn with Pimoroni's MicroPython firmware (includes `cosmic` and `picographics`).
2. Copy `main.py` to the root of the device (e.g. with [MicroPico](https://marketplace.visualstudio.com/items?itemName=paulober.pico-w-go) or `mpremote`).
3. The simulation starts automatically on power-up.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
