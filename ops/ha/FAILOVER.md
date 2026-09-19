# MESFlow HA Failover

Status: NOT YET ENABLED.

Do not fail over automatically or manually until the Patroni lab, live two-node Patroni cluster, pg_rewind rejoin, role-aware app control, and required safety gates pass.

Future manual switchover must use Patroni switchover with explicit candidate mesflow-hp, never forced promotion while TEST is healthy.
