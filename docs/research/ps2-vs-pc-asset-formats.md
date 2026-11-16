# Vehicle and track format research: PS2 build boundary

## Current evidence from this disc

The NTSC PS2 image is identified by executable `SLUS_210.65`. Its ZDIR index resolves resource paths including:

- `CARS/<vehicle>/GEOMETRY.BIN` for multiple vehicles;
- `CARS/WHEELS/GEOMETRY_*.BIN` for wheel models;
- `CARS/<vehicle>/TEXTURES.BIN` and `VINYLS.BIN`;
- `TRACKS/ROUTES*/ROUTES*.BIN` and `TRACKS/TRACKMAP*.BIN`.

These paths and archive offsets are directly observed in the supplied PS2 image's ZDIR catalogue. They do not by themselves prove the internal payload layout.

## Public PC-format references (reference only)

The OpenUG2 project documents PC retail Underground 2 formats and describes EA chunk containers with 8-byte little-endian chunk headers. Its documentation explicitly scopes its format work to PC retail data.

The NFSU2 World Editor documents reading PC `CARS/*/GEOMETRY.BIN` files and route/collision resources. It reports lossless round-tripping for supported PC world assets.

Sources:
- https://github.com/whoismept/OpenUG2/blob/main/docs/FORMATS.md
- https://github.com/mininxd/NFSU2-World-Editor

## Platform boundary

The PC specifications are useful hypotheses, not PS2 specifications. Do not assume the PS2 `GEOMETRY.BIN`, route, texture, or compression layouts are byte-identical to PC. The PS2 executable, archive payload samples, endianness, chunk boundaries, and any platform-specific compression must be independently checked before implementing a parser.

## Next validation

1. Read only the first 64 bytes of representative PS2 vehicle geometry and track resources.
2. Compare candidate chunk IDs and declared sizes against file lengths and nested boundaries.
3. Validate repeated structures across several vehicles, not one sample.
4. For track resources, distinguish road graph route chunks from `TRACKMAP` and world-stream chunks.
5. Record each field as observed or proven; do not label a guess as a format fact.

The probe tool writes only header signatures and hashes of the 64-byte samples. No game payloads are committed.
