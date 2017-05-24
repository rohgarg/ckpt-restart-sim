#!/sw/bin/python2.7

import simpy
import os, sys, math, random
from inspect import currentframe, getframeinfo


"""
Single process checkpoint-restart simulator

"""
RANDOM_SEED = 42
PT_MEAN = 500.0        # Avg. processing time in minutes
PT_SIGMA = 100.0        # Sigma of processing time
MTBF = 300.0           # Mean time to failure in minutes
BREAK_MEAN = 1 / MTBF  # Param. for expovariate distribution
NUM_PROCESSES = 1      # Number of processes

enableProcLogs = True

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
        self.isRestarting = False
        self.totalComputeTime = time_per_process()
        self.lastCheckpointTime = 0
        self.numCkpts = 0
        self.numFailures = 0
        self.startTime = env.now
        self.workLeft = self.totalComputeTime
        self.endTime = 0
        self.lostWork = 0
        self.ckptTime = ckptTime
        self.restartFailures = 0
        self.lostRestartTime = 0
        self.numRestarts = 0
        self.ckptFailures = 0
        self.numOfPreempts = 0
        self.lostCkptTime = 0
        self.lostRestartTime = 0
        self.submissionTime = 0
        self.actualRunTime = 0

        # Start "compute" process for this job
        self.process = env.process(self.compute())

    def ProcLog(self, msg):
        if enableProcLogs:
            print("[%d][%4d]: %s: %s" % (self.env.now, currentframe().f_back.f_lineno, self.name, msg))

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
                    self.actualRunTime = self.endTime - self.startTime
                    self.ProcLog("Done.")
                    self.env.exit()
                self.ProcLog("Computing for %d" % (computeTime))
                yield self.env.timeout(computeTime)

                if self.workLeft <= oci:
                     self.workLeft = 0
                     self.endTime = self.env.now
                     self.actualRunTime = self.endTime - self.startTime
                     self.ProcLog("Done with all compute.")
                     self.env.exit()
                self.ProcLog("Starting ckpting, workleft %d" % (self.workLeft))
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
                #self.ProcLog("Done ckpting, work left %d, ckpts %d, lastCkpt %d" % (self.workLeft, self.numCkpts, self.lastCheckpointTime))

            except simpy.Interrupt as e:
                if (e.cause == "failure"):
                    # fallback to the last checkpoint
                    self.numFailures += 1
                    if inTheMiddle:
                        inTheMiddle = False
                        self.ckptFailures += 1
                        self.lostCkptTime += self.env.now - ckptStartTime
                        self.ProcLog("Ckpt failure, lastCkpt %d, workLeft %d" % (self.lastCheckpointTime, self.workLeft))
                    self.isRestarting = True
                    #self.ProcLog("Incurred a failure, work left %d" % (self.workLeft))
                    restarting = self.env.process(self.do_restart(self.env.now - start))
                    while True:
                        try:
                            yield restarting
                            break
                        except simpy.Interrupt as e:
                            self.ProcLog("Restart received: %s" %(e.cause))
                            restarting.interrupt(cause=e.cause)
                    #self.ProcLog("Done restarting, work left %d, lost work %d" % (self.workLeft, self.lostWork))
                    self.isRestarting = False
                else:
                    print("Unexpected interrupt in the middle of computing")
                    exit(-1)
        self.workLeft = 0
        self.endTime = self.env.now
        self.actualRunTime = self.endTime - self.startTime


    def do_restart(self, timeSinceLastInterruption):
        """Restart the process after a failure."""
        delta = self.ckptTime
        failureInTheMiddle = False
        while True:
            try:
                if not failureInTheMiddle:
                    self.lostWork += timeSinceLastInterruption
                if self.numCkpts > 0:
                    assert self.isRestarting == True
                    self.ProcLog("Attempting to restart from ckpt #%d, taken at %d" % (self.numCkpts, self.lastCheckpointTime))
                    restartStartTime = self.env.now
                    yield self.env.timeout(delta)
                    self.numRestarts += 1
                    # Done with restart without errors
                    self.ProcLog("Restart successful... going back to compute")
                    self.env.exit()
                else:
                    self.ProcLog("Nothing to do for restart")
                    self.env.exit()
            except simpy.Interrupt as e:
                failureInTheMiddle = True
                self.restartFailures += 1
                self.numFailures += 1
                self.lostRestartTime += self.env.now - restartStartTime
                if e.cause == "failure":
                    self.ProcLog("Restart failure... will attempt restart again")

    def __str__(self):
        return "%s, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d" %\
               (self.name, self.numCkpts, self.numFailures, self.numRestarts, self.restartFailures,
                self.ckptFailures, self.numOfPreempts, self.totalComputeTime, self.ckptTime,
                self.lostWork, self.lostRestartTime, self.lostCkptTime, self.submissionTime,
                self.startTime, self.endTime, self.actualRunTime)

def inject_failure(env, procs, verbose):
    """Break the machine every now and then."""
    liveProcs = len(procs)
    while liveProcs > 0:
        yield env.timeout(time_to_failure())
        for p in procs:
            if p.workLeft > 0:
                # Only break the machine if it is currently computing.
                if verbose: print("[%d] Injecting a failure in %s" % (env.now, p.name))
                p.process.interrupt(cause="failure")
                continue
            liveProcs -= 1


# Setup and start the simulation
print('Process checkpoint-restart simulator')

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbosity", action="store_true", help="Show run time logs from processes")
parser.add_argument("-n", "--procs", type=int, default=NUM_PROCESSES, help="max. number of processes to run simultaneously")
args = parser.parse_args()
NUM_PROCESSES = args.procs
enableProcLogs = args.verbosity

random.seed(RANDOM_SEED)  # constant seed for reproducibility

# Create an environment and start the setup process
env = simpy.Environment()
processes = [Process(env, 'Process %d' % i, time_to_checkpoint())
             for i in range(NUM_PROCESSES)]

env.process(inject_failure(env, processes, args.verbosity))

# Execute
env.run()

# Analyis/results
print("******************************************************")
print("******************FINAL DATA**************************")
print("******************************************************")
print("Process #, # Ckpts, # Total Failures, # Restarts, # Failed Restarts, # Failed Ckpts, # Preempts,"\
      " Compute Time, Ckpt Time, Lost Work, Lost Restart Time, Lost Ckpt Time, Submission Time, Start Time,"\
      " End Time, Actual Run Time")
for p in processes:
    t1 = int((p.numCkpts + p.numRestarts) * p.ckptTime + p.lostWork + p.totalComputeTime + p.lostRestartTime)
    t2 = int(p.actualRunTime)
    assert p.restartFailures * p.ckptTime >= p.lostRestartTime
    if t1 != t2:
        print("Warning: %d != %d" % (t1, t2))
    print(p)
