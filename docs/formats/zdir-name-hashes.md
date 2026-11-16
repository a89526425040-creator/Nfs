# ZDIR filename hash resolution

## Observed algorithm

The public Ekey `NFS.BIN.Tool` implementation resolves `dwNameHash` through a text dictionary named `FileNames.list`. Its `BinHash.iGetHash` routine starts with `0xFFFFFFFF` and updates the 32-bit value for each uppercase UTF-16 character:

```text
hash = (33 * hash + character_code) mod 2^32
```

The catalogue tool implements this arithmetic and matches each 32-bit ZDIR name hash against candidate dictionary paths.

## Resolution policy

- Exactly one matching path: `resolved`.
- No matching path: preserve the hexadecimal hash as `__Unknown/HASH`.
- More than one matching path: mark `collision` and do not choose arbitrarily.
- The dictionary is downloaded temporarily by the ISO workflow; it is not committed.
- The catalogue contains index metadata only: name hash, candidate path, archive number, byte offset, size, and opaque ZDIR fields.
- No ZZDATA payload is extracted or committed.

## Evidence and limitations

The hash routine is taken from the public NFS.BIN.Tool source. The dictionary is a candidate-name corpus assembled for NFS console archives, not proof that every path belongs to this exact NTSC `SLUS_210.65` disc. A resolved hash is therefore a dictionary match, not a guarantee of semantic correctness. Unresolved hashes and collisions remain visible for later investigation.
