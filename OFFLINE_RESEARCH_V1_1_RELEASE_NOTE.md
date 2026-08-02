# Offline Research v1.1 Release Note

v1.1 finalizes the offline CLI/export workflow. A user can explicitly provide source kind, local input path, output path, and overwrite policy. Successful export is deterministic and carries export metadata plus SHA-256 export hash. Failures use stable blocked JSON and a non-zero exit code.

Frozen v1.0 research semantics remain unchanged. No remote transport, live provider, broker, account, order, position, or trading capability was added.
