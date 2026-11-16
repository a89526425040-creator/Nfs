# PS2 VIF geometry stream findings

## Scope

These findings are from the supplied NTSC PS2 build (`SLUS_210.65`) and three complete vehicle geometry resources: RX7, Celica, and IS300. The ISO workflow parsed nine `0x00134A02` leaves and independently cross-checked the enclosing chunk trees with the C++ reader.

## Descriptor-to-stream correlation

Each sampled geometry container has a 20-byte `0x00134A00` leaf followed by a `0x00134A02` VIF stream. Across all nine sampled submeshes:

- The second little-endian word in `0x00134A00` equals the number of `MSCAL` commands in the corresponding VIF stream.
- The third little-endian word equals the VIF stream byte count after removing the eight leading `0x11` resource-fill bytes.
- Every parsed VIF stream ends exactly at its declared payload boundary; no trailing fill bytes remain.

| Vehicle | Submesh | Descriptor count | VIF MSCAL count | Declared VIF bytes | Leaf payload bytes | Payload minus 8 |
|---|---:|---:|---:|---:|---:|---:|
| RX7 | 0 | 37 | 37 | 13,408 | 13,416 | 13,408 |
| RX7 | 1 | 28 | 28 | 7,568 | 7,576 | 7,568 |
| RX7 | 2 | 17 | 17 | 4,448 | 4,456 | 4,448 |
| Celica | 0 | 64 | 64 | 22,816 | 22,824 | 22,816 |
| Celica | 1 | 24 | 24 | 6,352 | 6,360 | 6,352 |
| Celica | 2 | 4 | 4 | 944 | 952 | 944 |
| IS300 | 0 | 54 | 54 | 18,048 | 18,056 | 18,048 |
| IS300 | 1 | 41 | 41 | 12,448 | 12,456 | 12,448 |
| IS300 | 2 | 8 | 8 | 2,208 | 2,216 | 2,208 |

This is strong evidence that `0x00134A00` is a descriptor for the adjacent VIF stream, and that its second and third words encode an execution count and stream length respectively. The first word (for example `0xC1800020` or `0x41800020`) remains uninterpreted.

## VIF input groups observed

The VIF streams repeatedly write to the same VU memory addresses:

| VU address | Observed input | What is established |
|---:|---|---|
| `0x000` | V4-8 | Four 8-bit components |
| `0x001` | V4-32 | Four 32-bit components; first records contain mixed integer/float-looking values |
| `0x002` | V3-32 | Three 32-bit components; float interpretations are finite and often in plausible geometric ranges |
| `0x004` | V4-32 | Four 32-bit components; many samples look normalized, but meaning is unknown |
| `0x005` | V4-16 | Four 16-bit components |
| `0x00B` and nearby addresses | V2/V3-16 | Packed 16-bit component groups |
| `0x01D` and nearby addresses | V4-16 | Packed 16-bit component groups |
| `0x02D` | V4-8 | Often unsigned values from 0 to 255 |
| `0x04D` | V4-8 | Signed values commonly in the -127 to 127 range |

The numeric probe records signedness from the VIF UNPACK USN bit, component widths, vector counts, VU destination addresses, bounded samples, and min/max values. For 32-bit fields it reports both integer and IEEE-754 interpretations. These are candidate interpretations only: no attribute has yet been definitively named as position, normal, UV, color, or index.

## VU microprogram question

The sampled streams contain many `MSCAL` calls (all with immediate zero) but no `MPG` commands. Therefore the microprogram is not loaded by these particular VIF streams. It must be preloaded elsewhere, shared/preconfigured by the game, or supplied by another resource/path. A renderer cannot correctly reproduce the game output until this program or an equivalent transformation is understood.

## Next steps

1. Locate the VU microprogram source or its upload path in the other PS2 resources and executable.
2. Decode the VU memory layout at addresses `0x001`, `0x002`, `0x004`, `0x005`, `0x02D`, and `0x04D`.
3. Establish which values are positions and which are attributes by tracing the VU program's reads and output writes.
4. Identify the index/primitive assembly path and triangle winding.
5. Export a first GLB/OBJ test model only after positions and topology are supported by evidence; until then a point-cloud preview may be labelled experimental.

## Reports

- [VIF command stream report](https://github.com/a89526425040-creator/Iso/blob/main/iso/vif-stream-probe-report.md)
- [VIF UNPACK numeric sample report](https://github.com/a89526425040-creator/Iso/blob/main/iso/vif-unpack-samples-report.md)
- [Mesh leaf probe report](https://github.com/a89526425040-creator/Iso/blob/main/iso/mesh-leaf-probe-report.md)
- [C++/Python chunk reader cross-check](https://github.com/a89526425040-creator/Iso/blob/main/iso/cpp-chunk-reader-report.md)
