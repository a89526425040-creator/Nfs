# PS2 vehicle geometry prefix: first bounded observations

## Scope

This note describes the NTSC PS2 image identified by `SLUS_210.65`. It is based on the first 256 bytes of eight catalogue-selected vehicle geometry resources and does not assume that PC layouts are identical.

The automated ISO workflow sampled 16 resources overall (vehicle geometry and track resources). The observations below are consistent across the vehicle geometry prefixes.

## Repeated vehicle prefix

All inspected vehicle files begin with these little-endian 32-bit values:

| File offset | Observed value | Evidence |
|---:|---:|---|
| `0x00` | `0x80134000` | Same in all inspected vehicle geometry files |
| `0x04` | Varies by file | A 32-bit value; its precise size semantics remain to be checked against the complete file |
| `0x08` | `0x00000000` | Eight zero bytes occupy `0x08..0x0F` |
| `0x10` | `0x80134001` | Same in all inspected vehicle geometry files |
| `0x14` | Varies by file | A 32-bit value; precise semantics not yet assigned |
| `0x18` | `0x00134002` | Same in all inspected vehicle geometry files |
| `0x1C` | `0x00000090` | Declared following block size is 144 bytes |
| `0x28` | `0x0000001D` | Observed constant; meaning unknown |
| `0x2C` | Varies by file | Observed per-file value; meaning unknown |
| `0x30` | ASCII path | Begins with `..\\PSX2\\CDUG2\\CARS\\...` |
| `0x68` | ASCII `DEFAULT` | Repeated metadata string |

The byte sequence at offsets `0x00`, `0x10`, and `0x18` is consistent with an 8-byte chunk framing convention (32-bit identifier followed by 32-bit payload length). This is an observed structural hypothesis supported by repeated PS2 samples; the complete chunk tree and parent boundaries are the next validation step.

## What is not yet proven

- The meaning of the values at `0x04`, `0x14`, `0x28`, and `0x2C`.
- Whether the first root chunk spans the entire resource. In sampled files, the value at `0x04` is smaller than the complete ZDIR resource size.
- The meaning and layout of mesh, vertex, index, material, and texture records.
- Whether any PC-only geometry details (vertex stride, filler, winding, or transforms) match this PS2 build.

## Safety rules for the reader

- Read all integers explicitly as little-endian.
- Validate each declared chunk length against its immediate parent boundary before descending or skipping.
- Recurse into a chunk only after its identifier has been observed to represent a container.
- Keep unknown fields opaque; do not infer vertex or material layouts from nearby values.
- Tests use synthetic byte arrays and never require copyrighted game payloads.

## Evidence source

The generated report is in the companion `Iso` repository at `iso/resource-structure-report.md`. It records decoded prefix words, printable strings, source archive offsets, and sample hashes, but not raw payload bytes.
