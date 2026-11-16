# PS2 NFS Underground 2 — ZDIR / ZZDATA

## Disc observed

The inspected ISO identifies itself as `NFS_UNDERGROUND2`, contains `SLUS_210.65`, and stores the main index at `NFSUNDER/ZDIR.BIN`. The index is 33,408 bytes, which is exactly 1,392 records at 24 bytes each.

## Candidate 24-byte record layout

The public NFS.BIN.Tool reader documents and consumes this little-endian record layout for the newer ZDIR format:

| Offset | Width | Field | Current interpretation |
|---:|---:|---|---|
| 0x00 | 4 | `name_hash` | 32-bit path/name hash |
| 0x04 | 4 | `archive_id` | ZZDATA archive number |
| 0x08 | 4 | `local_offset_sectors` | Local offset in 2048-byte sectors |
| 0x0C | 4 | `total_offset` | Meaning not established here |
| 0x10 | 4 | `size` | Entry byte length |
| 0x14 | 4 | `checksum` | Meaning/algorithm not established here |

The reference reader multiplies `local_offset_sectors` by 2048 before seeking into `ZZDATA{archive_id}.BIN`.

**Evidence status:** OBSERVED in a public reader for the NFS console ZZDATA family; NOT YET VALIDATED against every entry and archive boundary of this user's NTSC `SLUS_210.65` disc. Do not treat `total_offset` or `checksum` semantics as known.

## Parser safety requirements

1. Require the index length to be divisible by 24.
2. Decode explicitly as little-endian; do not rely on host endianness.
3. Reject negative sizes and invalid archive IDs.
4. Compute byte offsets as `local_offset_sectors * 2048`.
5. Check `offset + size` without integer overflow and against the actual corresponding archive length.
6. Preserve unknown fields verbatim in diagnostic output.
7. Do not extract file payloads during metadata inspection.
8. Keep original game files out of Git; store only structural summaries and hashes.

## Next validation

Run `tools/zdir_inspect.py` on the extracted ZDIR index and provide all four ZZDATA archive lengths. The resulting report will establish whether all 1,392 records map inside the four archives and how entries are distributed. Only after that should a bounded extractor be implemented.
