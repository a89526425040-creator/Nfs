# NTSC PS2 vehicle geometry chunks

## Evidence scope

This document describes resources from the supplied NTSC PS2 build identified by `SLUS_210.65`. It is based on complete-file scans of eight ZDIR-resolved `CARS/*/GEOMETRY.BIN` resources. It is not a PC format specification.

The scanner reads the complete resource, validates every chunk against its immediate parent boundary, and recursively examines chunks whose ID has high nibble `0x8`. It records chunk IDs, sizes, offsets, padding, and counts only; it does not export payload bytes.

## Chunk framing

Observed framing is:

| Offset | Type | Meaning |
|---:|---|---|
| +0 | `u32 LE` | Chunk identifier |
| +4 | `u32 LE` | Payload byte count |
| +8 | bytes | Payload |

The next sibling begins at `header_offset + 8 + payload_size`. The scanner accepts zero-ID padding records and runs of `0x11` filler. It stops on a malformed size rather than searching outside the immediate parent.

The root identifier observed at offset zero is `0x80134000`. Its declared payload length is smaller than the complete ZDIR resource size in the inspected files; the remaining bytes are scanned as a separate top-level stream rather than silently included in the root.

## Repeated PS2 vehicle hierarchy

The following hierarchy was observed in the complete-file scans:

```text
0x80134000  root container
  0x80134001  header container
    0x00134002  leaf, 144 bytes
    0x00134003  leaf, variable size
    0x00134004  leaf, variable size
    0x80134008  empty container
  0x80134010  repeated object container
    0x00134011  leaf, 192 bytes
    0x00134012  leaf, variable size
    0x00134013  leaf, variable size
    0x00134017  optional leaf
    0x00134018  optional leaf
    0x00134019  optional leaf
    0x0013401A  optional leaf
    0x80134100  geometry subcontainer
      0x00134A00  leaf, 20 bytes
      0x00134A01  leaf, variable size
      0x00134A02  leaf, variable size
```

The tree above is an observed structural summary, not a semantic naming of the leaves. In particular, the roles of `0x00134A00`, `0x00134A01`, and `0x00134A02` (descriptor, vertex stream, index stream, or another arrangement) remain unassigned until their payloads are checked.

## Cross-file validation

The generated ISO report contains eight complete geometry scans. All eight have zero chunk-boundary errors. Representative counts:

| Resource | Total chunks | Containers | Leaves | Repeated object containers |
|---|---:|---:|---:|---:|
| RX7 | 6,901 | 1,272 | 5,629 | 634 |
| Celica | 6,641 | 1,222 | 5,419 | 609 |
| IS300 | 6,198 | 1,140 | 5,058 | 568 |
| Peugeot | 6,609 | 1,214 | 5,395 | 605 |
| 3000GT | 6,303 | 1,162 | 5,141 | 579 |
| Escalade | 3,715 | 708 | 3,007 | 352 |
| Mirrors body | 2,646 | 483 | 2,163 | 240 |
| Lancer Evolution VIII | 6,263 | 1,148 | 5,115 | 572 |

For RX7, the number of `0x80134010` object containers and `0x80134100` geometry subcontainers is 634 each. The three `0x134A00/01/02` leaf IDs also occur 634 times each. This repeated parent/child relationship is strong evidence that the hierarchy is structural rather than an accidental scan of payload bytes.

The scan also found one `0x80034020` container and five each of `0x00039200`, `0x00039201`, and `0x00039202` in several vehicles. Their semantic relationship is not yet decoded.

## Unknowns and next measurements

- The exact payload fields in `0x134A00`, `0x134A01`, and `0x134A02`.
- Whether vertex records are 24, 32, 36, or another byte stride.
- Whether index values are 16-bit or 32-bit, and whether they are local to a mesh.
- The role of per-object leaves `0x134012`, `0x134013`, and `0x13417..`.
- Texture/material references and how they bind to texture archives.
- Coordinate handedness, axis order, scale, and triangle winding.

The next probe reads a small bounded prefix from representative geometry leaves and reports decoded numeric candidates and payload-size divisibility. No leaf payload is copied into the repository.
