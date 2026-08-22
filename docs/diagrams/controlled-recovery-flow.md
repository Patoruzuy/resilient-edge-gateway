# Controlled-recovery control flow

This is following upstream reconnection, the gateway requires a configurable link-stability time and an acknowledged QoS 1 health publication before backlog recovery starts. Eligible pending and `retry_wait` records are then released in limited batches. Failed or doubtful publications return to `retry_wait` and force the recovery back through the stability check, while successful batches continue after a pause and health verification.
