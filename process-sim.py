#!/sw/bin/python2.7

import simpy
import os, sys, math, random


"""
Single process checkpoint-restart simulator

"""
RANDOM_SEED = 42
PT_MEAN = 500.0        # Avg. processing time in minutes
PT_SIGMA = 100.0        # Sigma of processing time
MTBF = 300.0           # Mean time to failure in minutes
BREAK_MEAN = 1 / MTBF  # Param. for expovariate distribution
NUM_PROCESSES = 10      # Number of processes


def time_per_process():
    """Return a randomly generated compute time."""
    return int(random.normalvariate(PT_MEAN, PT_SIGMA))


def time_to_failure():
    """Return time until next failure for a machine."""
    return int(random.expovariate(BREAK_MEAN))
    #return MTBF

def time_to_checkpoint():
    return 10

class Process(object):
    """A process computes, checkpoints, and occasionaly incurs a failure.

    If it fails, it restarts from the latest checkpoint. 

    """
    def __init__(self, env, name, ckptTime):
        self.env = env
        self.name = name
        self.broken = False
        self.totalComputeTime = time_per_process()
        self.lastCheckpointTime = 0
        self.numCkpts = 0
        self.numFailures = 0
        self.startTime = env.now
        self.workLeft = self.totalComputeTime
        self.endTime = 0
        self.lostWork = 0
        self.ckptTime = ckptTime

        # Start "compute" and "break_machine" processes for this machine.
        self.process = env.process(self.compute())
        env.process(self.inject_failure())

    def compute(self):
        """Simulate compute for the given amount of total work.
        """
        inTheMiddle = False
        while self.workLeft:
            try:
                # Start computing
                start = self.env.now
                #yield self.env.timeout(self.workLeft)
                delta = self.ckptTime
                oci = int(math.sqrt(2*MTBF*delta))
                computeTime = min(oci, self.workLeft)
                if computeTime <= 0:
                    self.endTime = self.env.now
                    self.env.exit()
                yield self.env.timeout(computeTime)
                #print("%s: Starting ckpting at %d, workleft %d" % (self.name, self.env.now, self.workLeft))
                ckptStartTime = self.env.now
                inTheMiddle = True
                yield self.env.timeout(delta)
                # Done with ckpting, now
                #  first, save the progress made since the last interruption, and
                timeSinceLastInterruption = ckptStartTime - start
                self.workLeft -= timeSinceLastInterruption
                #  second, update the latest ckpt time
                self.lastCheckpointTime += timeSinceLastInterruption
                # ... and increment the number of ckpts
                self.numCkpts += 1
                inTheMiddle = False
                #print("%s: Done ckpting at %d, work left %d, ckpts %d, lastCkpt %d" % (self.name, self.env.now, self.workLeft, self.numCkpts, self.lastCheckpointTime))

            except simpy.Interrupt as e:
                if (e.cause == "failure"):
                    # fallback to the last checkpoint
                    if inTheMiddle:
                        inTheMiddle = False
                        print ("%s: Failure in the middle of a checkpoint at %d, lastCkpt %d, workLeft %d" % (self.name, self.env.now, self.lastCheckpointTime, self.workLeft))
                    self.broken = True
                    #print("Incurred a failure at %d, work left %d" % (self.env.now, self.workLeft))
                    restarting = self.env.process(self.do_restart(self.env.now - start))
                    yield restarting
                    #print("Done restarting at %d, work left %d, lost work %d" % (self.env.now, self.workLeft, self.lostWork))
                    self.broken = False
                else:
                    print("Unexpected interrupt in the middle of computing")
                    exit(-1)
        self.workLeft = 0
        self.endTime = self.env.now


    def inject_failure(self):
        """Break the machine every now and then."""
        while self.workLeft:
            yield self.env.timeout(time_to_failure())
            if not self.broken and self.workLeft > 0:
                # Only break the machine if it is currently computing.
                #print("Injecting a failure at %d" %(self.env.now))
                self.broken = True
                self.numFailures += 1
                self.process.interrupt(cause="failure")

    def do_restart(self, timeSinceLastInterruption):
        """Restart the process after a failure."""
        delta = self.ckptTime
        assert(self.broken == True)
        try:
            #print("Attempting to restart from ckpt #%d, taken at %d" % (self.numCkpts, self.lastCheckpointTime))
            self.lostWork += timeSinceLastInterruption
            yield self.env.timeout(delta)
            # Done with restart without errors
            #print("Restart successful... going back to compute")
        except simpy.Interrupt as e:
            if (e.cause == "failure"):
                print("Failure in the middle of a restart... will attempt restart again")
                self.broken = True
                self.do_restart()


# Setup and start the simulation
print('Process checkpoint-restart simulator')
random.seed(RANDOM_SEED)  # constant seed for reproducibility

# Create an environment and start the setup process
env = simpy.Environment()
processes = [Process(env, 'Process %d' % i, time_to_checkpoint())
             for i in range(NUM_PROCESSES)]

# Execute
env.run()

# Analyis/results
for p in processes:
    if (int((p.numCkpts + p.numFailures) * p.ckptTime +\
        p.lostWork + p.totalComputeTime) != int(p.endTime)):
      print "Warning"
    print('%s:: '\
          '# ckpts: %d, # failures: %d, '\
          'compute time: %d, '\
          'lost work: %d, '\
          'actual run time: %d' %
          (p.name, p.numCkpts, p.numFailures, p.totalComputeTime, p.lostWork, p.endTime))
