# Research checkpoint — PS2 archive reader

Date: 2026-11-16

## Confirmed from our disc report

- Volume label: `NFS_UNDERGROUND2`
- Boot executable: `SLUS_210.65` (NTSC-region serial)
- Index: `NFSUNDER/ZDIR.BIN`, 33,408 bytes
- Four payload archives: `NFSUNDER/ZZDATA0.BIN` through `ZZDATA3.BIN`
- ZDIR length / 24 = 1,392 candidate records

## Public format references inspected

1. [Ekey/NFS.BIN.Tool](https://github.com/Ekey/NFS.BIN.Tool) explicitly lists Need for Speed: Underground 2 on PS2 among tested games. Its unpacker reads the newer ZDIR format as 24-byte little-endian records and converts the local offset from 2048-byte sectors to byte offsets.
2. The same reader resolves a 32-bit name hash through a supplied `FileNames.list`. Its hash routine is a rolling `hash = 33 * hash + uppercase_character`, starting at `0xFFFFFFFF`. Unknown hashes remain unknown; collisions are possible.
3. [nfsu2-native](https://github.com/mad0xStrixhadorami/nfsu2-native) is a separate native reconstruction based on the PAL v2.00 executable `SLES_527.25`. It is valuable technical research, but it is not our exact NTSC executable and targets Linux x86, not Android.
4. [OpenUG2 format notes](https://github.com/whoismept/OpenUG2/blob/main/docs/FORMATS.md) describe PC retail data formats. Those notes are useful for later resource decoding but must not be assumed to describe PS2 ZZDATA internals.

## Implementation added to this repository

- `tools/zdir_inspect.py`: defensive parser for the candidate 24-byte record.
- `tools/test_zdir_inspect.py`: synthetic tests for field decoding, sector offsets, malformed lengths, negative sizes, invalid archive IDs, and archive-boundary checks.
- `docs/formats/zdir-zzdata.md`: field table and explicit evidence status.

The parser intentionally does not extract or commit any game payload. The updated `Iso` workflow temporarily extracts the ZDIR index and four ZZDATA files on the GitHub runner, validates every indexed byte range against the actual archive sizes, then commits only a compact report.

## Next gate

Do not begin decoding the large payload formats until the updated ISO workflow produces a report with zero out-of-bounds references. Then implement a bounded, read-only entry extractor that can extract selected entries by index/hash to the runner's temporary directory. Keep extracted commercial assets out of both Git repositories.
