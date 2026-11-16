# NFS

Clean-room Android reimplementation research for the user's own Need for Speed: Underground 2 PS2 disc.

## Repository layout

- `docs/formats/` — format observations, evidence level, and parser contracts.
- `tools/` — small, defensive inspection utilities.
- `app/` — Android application (planned).
- `native/` — C++20 engine and platform-independent game code (planned).

## Source-disc workflow

The user's ISO is kept out of Git. The companion `Iso` repository downloads it temporarily in GitHub Actions and commits only reports. Never commit the ISO or extracted commercial game assets here.

## Current disc fingerprint

- PS2 volume label: `NFS_UNDERGROUND2`
- Executable: `SLUS_210.65`
- Main archive index: `NFSUNDER/ZDIR.BIN` (33,408 bytes)
- Data archives: `NFSUNDER/ZZDATA0.BIN` through `ZZDATA3.BIN`
- ISO SHA-256: `3ab6b231356bc81107342171ee8205b8c8e8cda6c44f4960d2caf5c83dfd08e2`

The current public evidence supports a 24-byte ZDIR record layout used by the NFS console archive family. The parser must still validate this exact NTSC disc's records and archive bounds before treating the layout as proven for this build.
