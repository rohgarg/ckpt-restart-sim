#!/usr/bin/python2.7

import simpy
from simpy.util import start_delayed
from collections import deque
import os, sys, math, random
import numpy as np
from inspect import currentframe, getframeinfo

"""
FIFO batch queue simulator.

A process runs until the first failure. The scheduler then switches
in the lightest process, which is then runs until completion.
"""
RANDOM_SEED = 42
PT_MEAN = 1000.0       # Avg. processing time in minutes
PT_SIGMA = 100.0       # Sigma of processing time
MTBF = 100.0           # Mean time to failure in minutes
BREAK_MEAN = 1 / MTBF  # Param. for expovariate distribution
NUM_PROCESSES = 7      # Number of processes
MAX_PARALLEL_PROCESSES = 1
MAX_CIRC_Q_LEN = NUM_PROCESSES + 1
CKPT_THRESH = 10

# Shape parameter for Weibull distr.
WEIBULL_K = 0.96

# Failures are injected after a delay of 100
INITIAL_FAILURE_DELAY = 200

enableBqLogs = False
enableProcLogs = False

def time_per_process():
    """Return a randomly generated compute time."""
    return int(random.normalvariate(PT_MEAN, PT_SIGMA))

def time_to_failure():
    """Return time until next failure for a machine."""
    nextFailure = int(random.expovariate(BREAK_MEAN))
    #nextFailure = int(np.random.weibull(WEIBULL_K)*10.0)
    return nextFailure
    #return MTBF

def time_to_checkpoint():
    return 10

def time_to_preempt():
    return 250

class BatchQueue(object):
    """Represents and simulates a batch queue"""

    def __init__(self, myenv, max_circ_length, nodes):
        self.env = myenv
        self.maxLength = max_circ_length
        self.circQ = deque([], self.maxLength)
        self.allJobs = []
        self.numPreempts = 0
        self.process = None
        self.switchingJobs = False
        self.numFailures = 0
        self.machine = nodes
        self.currentProc = None

    def BqLog(self, msg):
        """Logging mechanism for the batchqueue"""
        if enableBqLogs:
            print("[%d][%4d]: BQ(%d): %s" %(self.env.now, currentframe().f_back.f_lineno, len(self.circQ), msg))

    def addToBq(self, p):
        """Add the given process to the batchqueue
        for processing at a later time"""
        self.allJobs.append(p)
        p.submitToQueue()
        if len(self.circQ) < self.maxLength - 1:
            self.circQ.append(p)

    def runBq(self, with_preempt):
        self.process = self.env.process(self.runBqHelper(with_preempt))
        start_delayed(self.env, self.inject_failure(), INITIAL_FAILURE_DELAY)
        while True:
            try:
                yield self.process
                self.env.exit()
            except simpy.Interrupt as e:
                self.process.interrupt(e.cause)

    def inject_failure(self):
        """Break the machine every now and then."""
        # Inject a failure only if there's a process running
        self.BqLog("Starting failure injection")
        while len(self.circQ) > 0 or (self.currentProc and self.currentProc.workLeft > 0):
            t = time_to_failure()
            self.BqLog("Inject the next failure after %d seconds" % (t))
            if t == 0:
              continue
            yield self.env.timeout(t)
            if len(self.circQ) >= 0 and \
               self.currentProc.workLeft > 0:
                # Only break the machine if it is currently computing,
                #  and if current proc is not restarting
                self.BqLog("Injecting a failure in %s" % (self.currentProc.name))
                self.numFailures += 1
                self.process.interrupt(cause="failure")

    def runBqHelper(self, with_preempt=True):
        while len(self.circQ) > 0:
          with self.machine.request() as req:
            yield req
            try:
                # Run the head of the queue for a while
                p = self.circQ.popleft()
                self.BqLog("Will try to exe %s next" % (p.name))
                if p.workLeft == 0:
                    self.BqLog("Done with %s" % (p.name))
                    continue
                # Run, or Restart (if the process has at least one checkpoint)
                self.currentProc = p
                if p.startAfresh:
                    start = self.env.now
                    queueTime = self.env.now
                    self.BqLog("Starting %s" %(p.name))
                    p.process = self.env.process(p.runJob())
                elif p.isRestarting and not p.isPreempted:
                    start = self.env.now
                    self.BqLog("%s recovering from failure... nothing to do" %(p.name))
                elif p.isPreempted:
                    self.BqLog("Resuming %s" % (p.name))
                    queueTime = self.env.now
                    p.waitForBq.succeed()
                    p.waitForBq = self.env.event()
                    yield p.resumeCompleted
                    self.BqLog("Restarted %s" % (p.name))
                    start = self.env.now
                else:
                    assert False
                # Simple FIFO scheduling after a fault
                self.BqLog("Wait for %s to complete" %(p.name))
                yield p.waitForComputeToEnd
                p.actualRunTime += self.env.now - queueTime
                self.BqLog("%s completed, AT: %d, QT: %d" %(p.name, p.actualRunTime, queueTime))
                self.allJobs.remove(p)
                self.BqLog("Done with %s at end" % (p.name))
                continue
            except simpy.Interrupt as e:
                if e.cause == "failure":
                    # First, add the current job for execution at a later time
                    self.BqLog("Adding %s back for execution" % (p.name))
                    self.circQ.appendleft(p)
                    # Next, schedule the job with the min. ckpting overhead for execution
                    lightestProc = min(self.allJobs, key=lambda p:p.ckptTime)
                    if p.name == lightestProc.name:
                        if p.isPreempted: # failure in the middle of resuming from preemption
                            p.actualRunTime += self.env.now - queueTime
                        self.BqLog("Lightest proc already running... nothing to do.")
                        p.isRestarting = True
                        p.process.interrupt(cause="failure")
                        continue
                    p.actualRunTime += self.env.now - queueTime
                    self.BqLog("Scheduling %s for execution, AT: %d, QT: %d" % (lightestProc.name, p.actualRunTime, queueTime))
                    self.circQ.remove(lightestProc)
                    self.circQ.appendleft(lightestProc)
                    p.isPreempted = True
                    p.process.interrupt(cause="preemptImmediate")
                else:
                    self.BqLog("Unknown failure type. Exiting...")
                    exit(-1)


class Process(object):
    """A process computes, checkpoints, and occasionaly incurs a failure.

    If it fails, it restarts from the latest checkpoint.

    """
    def __init__(self, myenv, name, ckptTime, nodes):
        self.env = myenv
        self.name = name
        self.isRestarting = False
        self.isPreempted = False
        self.totalComputeTime = time_per_process()
        self.lastCheckpointTime = 0
        self.numCkpts = 0
        self.numFailures = 0
        self.workLeft = self.totalComputeTime
        self.endTime = 0
        self.actualRunTime = 0
        self.lostWork = 0
        self.ckptTime = ckptTime
        self.ckptFailures = 0
        self.bq = nodes
        self.startTime = 0
        self.submissionTime = 0
        self.process = None
        self.isCkpting = myenv.event() # True during checkpointing
        self.waitForBq = myenv.event()
        self.waitForComputeToEnd = myenv.event()
        self.resumeCompleted = myenv.event()
        self.numOfPreempts = 0
        self.lastComputeStartTime = 0
        self.lastCkptInstant = 0
        self.inTheMiddle = False
        self.restartFailures = 0
        self.numRestarts = 0
        self.lostRestartTime = 0
        self.lostCkptTime = 0
        self.startAfresh = True

    def submitToQueue(self):
        self.submissionTime = self.env.now

    def ProcLog(self, msg):
        if enableProcLogs:
            print("[%d][%4d]: %s: %s" % (self.env.now, currentframe().f_back.f_lineno, self.name, msg))

    def runJob(self):
        """Simulate compute for the given amount of total work.
        """
        self.inTheMiddle = False
        self.startTime = self.env.now
        self.startAfresh = False
        while self.workLeft:
            try:
                delta = self.ckptTime
                oci = int(math.sqrt(2*MTBF*delta))
                computeTime = min(oci, self.workLeft)
                if computeTime <= 0:
                    self.endTime = self.env.now
                    self.env.exit()

                # Simulate restart when requested by the bq, only if we have at least 1 ckpt
                if self.isPreempted and self.numCkpts > 0:
                   restarting = self.env.process(self.do_restart(0))
                   while True:
                       try:
                           self.isRestarting = True
                           yield restarting
                           self.isRestarting = False
                           self.isPreempted = False
                           break
                       except simpy.Interrupt as e:
                           self.ProcLog("Resume Restart received: %s" %(e.cause))
                           restarting.interrupt(cause=e.cause)
                   # Inform the Bq about completion of resume
                   self.resumeCompleted.succeed()
                   self.resumeCompleted = self.env.event()

                # Start computing
                start = self.env.now
                self.lastComputeStartTime = start
                self.ProcLog("Computing for %d, workleft %d" % (computeTime, self.workLeft))
                yield self.env.timeout(computeTime)

                # If the work left was less than oci, and we reach here w/o any interrupt,
                #    it means we are done
                if self.workLeft <= oci:
                   self.workLeft = 0
                   self.endTime = self.env.now
                   self.waitForComputeToEnd.succeed()
                   self.waitForComputeToEnd = self.env.event()
                   self.env.exit()

                self.ProcLog("Ckpting, workleft %d" % (self.workLeft))
                ckptStartTime = self.env.now
                self.inTheMiddle = True
                yield self.env.timeout(delta)

                # Done with ckpting, now
                #  first, save the progress made since the last interruption, and
                self.lastCkptInstant = self.env.now
                timeSinceLastInterruption = ckptStartTime - start
                self.workLeft -= timeSinceLastInterruption
                #  second, update the latest ckpt time
                self.lastCheckpointTime += timeSinceLastInterruption
                # ... and increment the number of ckpts
                self.numCkpts += 1
                self.inTheMiddle = False
                self.ProcLog("Done ckpting, work left %d, ckpts %d, lastCkpt %d" % (self.workLeft, self.numCkpts, self.lastCheckpointTime))
            except simpy.Interrupt as e:
                if e.cause == "failure":
                    # fallback to the last checkpoint
                    if self.inTheMiddle:
                        self.inTheMiddle = False
                        self.ckptFailures += 1
                        self.lostCkptTime += self.env.now - ckptStartTime
                        self.ProcLog("Checkpointing failure, lastCkpt %d, workLeft %d" % (self.lastCheckpointTime, self.workLeft))
                    self.isRestarting = True
                    self.ProcLog("Incurred a failure, work left %d" % (self.workLeft))
                    self.numFailures += 1
                    restarting = self.env.process(self.do_restart(self.env.now - start))
                    while True:
                        try:
                            yield restarting
                            break
                        except simpy.Interrupt as e:
                            self.ProcLog("Restart received: %s" %(e.cause))
                            restarting.interrupt(cause=e.cause)
                    self.ProcLog("Resumed after failure, work left %d, lost work %d" % (self.workLeft, self.lostWork))
                    self.isRestarting = False
                elif e.cause == "preemptImmediate":
                    if self.inTheMiddle:
                        self.inTheMiddle = False
                        self.ckptFailures += 1
                        #self.ProcLog("Checkpointing failure, lastCkpt %d, workLeft %d" % (self.lastCheckpointTime, self.workLeft))
                    self.isRestarting = False
                    self.numFailures += 1
                    restarting = self.env.process(self.do_restart(self.env.now - start, True))
                    yield restarting
                    self.ProcLog("preemptImmediate: Waiting for bq")
                    yield self.waitForBq
                    self.ProcLog("Resumed after preemptImmediate")
                    # Need to restart the job from its latest ckpt
                    self.isPreempted = True
                elif e.cause == "preempt":
                    self.ProcLog("Preempted, workLeft %d" %(self.workLeft))
                    self.numOfPreempts += 1
                    yield self.waitForBq
                    self.ProcLog("Resumed after preemption")
                    # Need to restart the job
                    self.isPreempted = True
                else:
                    print("Unexpected interrupt in the middle of computing")
                    exit(-1)
        self.workLeft = 0
        self.endTime = self.env.now

    def do_ckpt(self):
        self.inTheMiddle = False
        try:
            delta = self.ckptTime
            self.ProcLog("Forced ckpting, workleft %d" % (self.workLeft))
            self.inTheMiddle = True
            ckptStartTime = self.env.now
            yield self.env.timeout(delta)
            timeSinceLastInterruption = ckptStartTime - self.lastComputeStartTime;
            # Done with ckpting, now
            #  first, save the progress made since the last interruption, and
            self.workLeft -= timeSinceLastInterruption
            #  second, update the latest ckpt time
            self.lastCheckpointTime += timeSinceLastInterruption
            # ... and increment the number of ckpts
            self.numCkpts += 1
            self.isCkpting.succeed()
            self.isCkpting = self.env.event()
            self.inTheMiddle = False
            self.ProcLog("Done forced ckpting, work left %d, ckpts %d, lastCkpt %d" % (self.workLeft, self.numCkpts, self.lastCheckpointTime))
        except simpy.Interrupt as e:
            if e.cause in ["failure", "preemptImmediate"]:
                self.ckptFailures += 1
                self.lostCkptTime += self.env.now - ckptStartTime
                self.isCkpting.fail()
                self.isCkpting = self.env.event()
                self.ProcLog("Checkpointing failure, lastCkpt %d, workLeft %d" % (self.lastCheckpointTime, self.workLeft))

    def do_restart(self, timeSinceLastInterruption, noRestart=False):
        """Restart the process after a failure."""
        failureInTheMiddle = False
        # Try to restart until your time ends (e.g., preemption, fatal error)
        while True:
            delta = self.ckptTime
            try:
                # Don't count restart failures as lost work
                if not failureInTheMiddle:
                    self.ProcLog("Adding to lost work %d" %(timeSinceLastInterruption))
                    self.lostWork += timeSinceLastInterruption
                if not noRestart and self.numCkpts > 0:
                    assert self.isRestarting == True
                    self.ProcLog("Restart from ckpt #%d, taken at %d" % (self.numCkpts, self.lastCheckpointTime))
                    restartStartTime = self.env.now
                    yield self.env.timeout(delta)
                    # Done with restart without errors
                    self.numRestarts += 1
                    self.ProcLog("Restart successful... going back to compute")
                    self.env.exit()
                else:
                    self.ProcLog("Nothing to do for restart")
                    self.env.exit()
            except simpy.Interrupt as e:
                failureInTheMiddle = True
                self.restartFailures += 1
                self.lostRestartTime += self.env.now - restartStartTime
                if e.cause == "failure":
                    self.ProcLog("Restart failure... will attempt restart again")
                elif e.cause == "preemptImmediate":
                    self.ProcLog("preemptImmediate: restart mode: will wait for Bq to resume us")
                    yield self.waitForBq
                    self.ProcLog("preemptImmediate: restart mode: resumed")
                    self.env.exit()

    def __str__(self):
        return "%s, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d" %\
               (self.name, self.numCkpts, self.numFailures, self.numRestarts, self.restartFailures,
                self.ckptFailures, self.numOfPreempts, self.totalComputeTime, self.ckptTime,
                self.lostWork, self.lostRestartTime, self.lostCkptTime, self.submissionTime,
                self.startTime, self.endTime, self.actualRunTime)

def simulateArrivalOfJobs(env, processes, batchQ):
    """Simulate random arrival of jobs"""
    for p in processes:
        batchQ.addToBq(p)

def main(argc, argv):
    """Set up and start the simulation."""

    print('Process checkpoint-restart simulator')
    random.seed(RANDOM_SEED)  # constant seed for reproducibility

    # Create an environment and start the setup process
    env = simpy.Environment()
    if argc > 1:
      NUM_PROCESSES = int(sys.argv[1])
      MAX_CIRC_Q_LEN = NUM_PROCESSES + 1

    # Create a batch queue
    mymachine = simpy.Resource(env, MAX_PARALLEL_PROCESSES)
    batchQ = BatchQueue(env, MAX_CIRC_Q_LEN, mymachine)

    testProcesses = [Process(env, 'Process %d' % i, time_to_checkpoint() + random.randint(0, 5) * 10, mymachine)
                     for i in range(NUM_PROCESSES)]

    simulateArrivalOfJobs(env, testProcesses, batchQ)
    env.process(batchQ.runBq(False))
    # Execute
    env.run()

    # Analyis/results
    print("******************************************************")
    print("******************FINAL DATA**************************")
    print("******************************************************")
    print("Process #, # Ckpts, # Total Failures, # Restarts, # Failed Restarts, # Failure During Ckpt, # Preempts,"\
          " Compute Time, Ckpt Time, Lost Work, Lost Restart Time, Lost Ckpt Time, Submission Time, Start Time,"\
          " End Time, Actual Run Time")
    for p in testProcesses:
        t1 =  int((p.numCkpts + p.numRestarts) * p.ckptTime + p.lostWork + p.totalComputeTime + p.lostRestartTime)
        t2 = int(p.actualRunTime)
        if not p.restartFailures * p.ckptTime >= p.lostRestartTime:
          print "Warning"
        if t1 != t2:
            print("Warning: %d != %d" % (t1, t2))
        print(p)

if __name__ == "__main__":
    main(len(sys.argv), sys.argv)
