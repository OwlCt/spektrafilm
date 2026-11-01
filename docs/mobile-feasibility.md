# Android feasibility

This is a note only. There is no mobile build.

## What would have to move

The desktop GUI is Qt + napari. That stack does not have a supported Android port, so a phone app would be a new UI. The simulation itself is NumPy, SciPy, Numba, colour-science, and native imaging libraries (OpenImageIO, rawpy, pyfftw, exiv2, lensfunpy).

## Bundling options

Chaquopy and BeeWare/Briefcase can embed CPython and ship pure-Python plus some wheels. NumPy has Android builds in those ecosystems. Numba, OpenImageIO, pyfftw, rawpy, and lensfunpy do not: they are native extensions with no Android wheels, and Numba's LLVM JIT is the expensive part of the pipeline. Packaging the current environment would mean cross-compiling those extensions, not just wrapping the repo.

A practical split is a reduced pipeline (preview resolution, no RAW/OpenImageIO, no Numba or a small C/Rust replacement for the hot loops) inside Chaquopy, or leaving the full pipeline on a desktop/server and using the phone as a controller.

## Time and memory

On a laptop the full-resolution scan is already very slow. A recent phone CPU is several times slower on this kind of spectral array work, and RAM is the tighter limit: a few-megapixel float buffer plus spectral intermediates does not fit comfortably. A preview around 1000–1500 px on the long edge is the size that could plausibly finish on device, on the order of tens of seconds to a few minutes once the numeric core is ported. Full-resolution export on a phone is not a reasonable target.

## Recommended UI

Do not port napari. A small native screen (Kotlin or Flutter) that picks a film and paper, runs a preview-sized job, and shows the result is the right shape. Keep profile names and parameter values identical to the desktop app so projects still match. Ship that only after a reduced core exists; until then, process on the desktop build.
