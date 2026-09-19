# MESFlow HA Failback

Status: NOT YET TESTED.

Future failback is a controlled Patroni switchover HP -> TEST only after TEST has safely rejoined as a replica and replication is healthy. Old TEST must never reclaim leadership automatically.
