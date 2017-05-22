# Checkpoint-restart simulator

## How to navigate the source

### process-sim.py

Simple process checkpoint-restart sim, where all
the jobs are submitted in the beginning.

### queue-sim.py

Simple FIFO queue sim, where jobs are generated
and submitted to the queue at random times
with some distribution.

### round-robin-sim.py

Simple RR queue sim, all jobs are submitted in the
beginning and are scheduled in a RR fashion with a
fixed time quantum per job.

### fifo-proposed-sim.py

Proposed fault-aware FIFO queue sim, where all the
jobs are submitted in the beginning, and the lightest
job is switched in after a fault. The lightest application
continues to execute until completion or the next fault.

### rr-proposed-sim.py

Proposed fault-aware RR queue sim, where all the jobs
are submitted in the beginning, and the lightest job is
switched in after a fault. The applications are then
scheduled in a RR fashion with a fixed time quantum.

## Dependencies

The programs depend on SimPy, a Python-based discrete-event simulator
package. You can use `pip` to install it locally.

    $ sudo pip install simpy
