#!/usr/bin/python2.7

import simpy
from collections import deque
import os, sys, math, random


"""
Round-robin batch queue simulator.

A process runs until the first failure. The scheduler then switches
in the lightest process, which is then scheduled in a round-robin
fashion with the other heavy process.
"""
RANDOM_SEED = 42
PT_MEAN = 1000.0       # Avg. processing time in minutes
PT_SIGMA = 100.0       # Sigma of processing time
MTBF = 300.0           # Mean time to failure in minutes
BREAK_MEAN = 1 / MTBF  # Param. for expovariate distribution
NUM_PROCESSES = 2      # Number of processes
MAX_PARALLEL_PROCESSES = 1
MAX_CIRC_Q_LEN = NUM_PROCESSES + 1
CKPT_THRESH = 10

enableBqLogs = True
enableProcLogs = False

def time_per_process():
    """Return a randomly generated compute time."""
    return int(random.normalvariate(PT_MEAN, PT_SIGMA))


def time_to_failure():
    """Return time until next failure for a machine."""
    return int(random.expovariate(BREAK_MEAN))
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
        self.preemptMode = False

    def BqLog(self, msg):
        """Logging mechanism for the batchqueue"""
        if enableBqLogs:
            print("[%d]: BQ(%d): %s" %(self.env.now, len(self.circQ), msg))

    def addToBq(self, p):
        """Add the given process to the batchqueue
        for processing at a later time"""
        self.allJobs.append(p)
        p.submitToQueue()
        if len(self.circQ) < self.maxLength - 1:
            self.circQ.append(p)

    def runBq(self, with_preempt):
        self.process = self.env.process(self.runBqHelper(with_preempt))
        self.env.process(self.inject_failure())
        yield self.process

    def inject_failure(self):
        """Break the machine every now and then."""
        while len(self.circQ):
            yield self.env.timeout(time_to_failure())
            if len(self.circQ) > 0 and \
               not self.currentProc.broken and \
               self.currentProc.workLeft > 0:
                # Only break the machine if it is currently computing,
                #  and if current proc is not restarting
                #  TODO: Allow errors to be thrown while restarting
                self.BqLog("Injecting a failure in %s" % (self.currentProc.name))
                self.numFailures += 1
                self.process.interrupt(cause="failure")

    def runBqHelper(self, with_preempt=True):
        preemtionTime = time_to_preempt()
        while len(self.circQ) > 0:
          with self.machine.request() as req:
            yield req
            try:
                # Run the head of the queue for a while
                p = self.circQ.popleft()
                if p.workLeft == 0:
                    self.BqLog("Done with the queue")
                    continue
                # Run, or Restart (if the process has at least one checkpoint)
                self.currentProc = p
                if not p.startAfresh:
                    start = self.env.now
                    preemtionTime = time_to_preempt()
                    self.BqLog("Starting %s" %(p.name))
                    p.process = self.env.process(p.runJob(p.startAfresh))
                elif p.broken:
                    start = self.env.now
                    self.BqLog("%s recovering from failure... nothing to do" %(p.name))
                else:
                    self.BqLog("Resuming %s" % (p.name))
                    preemtionTime = time_to_preempt()
                    p.waitForBq.succeed()
                    p.waitForBq = self.env.event()
                    yield p.resumeCompleted
                    self.BqLog("Restarted %s" % (p.name))
                    start = self.env.now
                if not self.preemptMode:
                    # No round-robin scheduling until at least one failure
                    self.BqLog("No RR: wait for %s to complete" %(p.name))
                    yield p.waitForComputeToEnd
                    self.BqLog("No RR: %s completed" %(p.name))
                    self.allJobs.remove(p)
                    continue
                self.BqLog("Will preempt %s after %d" %(p.name, preemtionTime))
                yield p.waitForComputeToEnd | self.env.timeout(preemtionTime)
                if p.workLeft == 0:
                    self.BqLog("Done with %s." % (p.name))
                    if len(self.circQ) == 0:
                        self.env.exit()
                    continue
                # Then, preempt it after its quanta is over
                self.switchingJobs = True
                if p.inTheMiddle:
                    self.BqLog("%s currently ckpting." % (p.name))
                    yield p.isCkpting
                    self.BqLog("Non-regular Preempt %s" % (p.name))
                    p.process.interrupt(cause="preempt")
                else:
                    self.BqLog("Regular Preempt %s" % (p.name))
                    p.process.interrupt(cause="preempt")
                    if self.env.now - p.lastCkptInstant > CKPT_THRESH:
                        yield self.env.process(p.do_ckpt())
                    else:
                        self.BqLog("Skip ckpting for %s. Last Ckpt was at %d" % (p.name, p.lastCkptInstant))
                self.BqLog("%s completed ckpting" % (p.name))
                # Finally, add it back to the tail of the queue
                self.circQ.append(p)
                self.BqLog("Added %s back to queue" % (p.name))
                self.switchingJobs = False
            except simpy.Interrupt as e:
                if e.cause == "failure":
                    if not self.preemptMode:
                        self.BqLog("Starting Preemption now")
                        self.preemptMode = True
                        preemtionTime = time_to_preempt()
                        # First, add the current job for execution at a later time
                        self.BqLog("No RR: adding %s back for execution" % (p.name))
                        self.circQ.appendleft(p)
                        # Next, schedule the job with the min. ckpting overhead for execution
                        lightestProc = min(self.allJobs, key=lambda p:p.ckptTime)
                        if p.name == lightestProc.name:
                          self.BqLog("No RR: Lightest proc already running... nothing to do")
                          p.broken = True
                          p.process.interrupt(cause="failure")
                          continue
                        self.BqLog("No RR: scheduling %s for execution" % (lightestProc.name))
                        self.circQ.appendleft(lightestProc)
                        p.process.interrupt(cause="failureNoRestart")
                        continue
                    else:
                        preemtionTime -= self.env.now - start
                        p.broken = True
                        if preemtionTime < CKPT_THRESH:
                            # If near the end of execution, don't reschedule the job
                            self.circQ.append(p)
                            p.process.interrupt(cause="failureNoRestart")
                            self.BqLog("Not enough time %s to recover" % (p.name))
                        else:
                            # If there's still some time before preemption,
                            #   reschedule the job for execution again
                            self.BqLog("Adding %s back for execution" % (p.name))
                            self.circQ.appendleft(p)
                            p.process.interrupt(cause="failure")
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
        self.broken = False
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
        self.startAfresh = False # True once you have taken the first ckpt
        self.isCkpting = myenv.event() # True during checkpointing
        self.waitForBq = myenv.event()
        self.waitForComputeToEnd = myenv.event()
        self.resumeCompleted = myenv.event()
        self.numOfPreempts = 0
        self.lastComputeStartTime = 0
        self.lastCkptInstant = 0
        self.inTheMiddle = False

    def submitToQueue(self):
        self.submissionTime = self.env.now

    def ProcLog(self, msg):
        if enableProcLogs:
            print("[%d]: %s: %s" % (self.env.now, self.name, msg))


    def runJob(self, shouldRestart=False):
        """Simulate compute for the given amount of total work.
        """
        self.inTheMiddle = False
        self.startTime = self.env.now
        while self.workLeft:
            try:
                delta = self.ckptTime
                oci = int(math.sqrt(2*MTBF*delta))
                computeTime = min(oci, self.workLeft)
                if computeTime <= 0:
                    self.endTime = self.env.now
                    self.actualRunTime = self.endTime - self.startTime
                    self.env.exit()
                if shouldRestart:
                   yield self.env.timeout(delta) # simulate restart when requested by the bq
                   self.resumeCompleted.succeed()
                   self.resumeCompleted = self.env.event()
                # Start computing
                start = self.env.now
                self.lastComputeStartTime = start
                self.ProcLog("Computing for %d, workleft %d" % (computeTime, self.workLeft))
                yield self.env.timeout(computeTime)
                if self.workLeft < oci:
                   self.workLeft = 0
                   self.endTime = self.env.now
                   self.actualRunTime = self.endTime - self.startTime
                   self.waitForComputeToEnd.succeed()
                   self.waitForComputeToEnd = self.env.event()
                   self.env.exit()
                self.ProcLog("Ckpting, workleft %d" % (self.workLeft))
                ckptStartTime = self.env.now
                self.inTheMiddle = True
                yield self.env.timeout(delta)
                self.lastCkptInstant = self.env.now
                # Done with ckpting, now
                #  first, save the progress made since the last interruption, and
                timeSinceLastInterruption = ckptStartTime - start
                self.workLeft -= timeSinceLastInterruption
                #  second, update the latest ckpt time
                self.lastCheckpointTime += timeSinceLastInterruption
                # ... and increment the number of ckpts
                self.startAfresh = True
                self.numCkpts += 1
                self.inTheMiddle = False
                self.ProcLog("Done ckpting, work left %d, ckpts %d, lastCkpt %d" % (self.workLeft, self.numCkpts, self.lastCheckpointTime))
            except simpy.Interrupt as e:
                if e.cause == "failure":
                    # fallback to the last checkpoint
                    if self.inTheMiddle:
                        self.inTheMiddle = False
                        self.ckptFailures += 1
                        #self.ProcLog("Checkpointing failure, lastCkpt %d, workLeft %d" % (self.lastCheckpointTime, self.workLeft))
                    self.broken = True
                    #self.ProcLog("Incurred a failure, work left %d" % (self.workLeft))
                    self.numFailures += 1
                    restarting = self.env.process(self.do_restart(self.env.now - start))
                    yield restarting
                    #self.ProcLog("Resumed after failure, work left %d, lost work %d" % (self.workLeft, self.lostWork))
                    self.broken = False
                elif e.cause == "failureNoRestart":
                    if self.inTheMiddle:
                        self.inTheMiddle = False
                        self.ckptFailures += 1
                        #self.ProcLog("Checkpointing failure, lastCkpt %d, workLeft %d" % (self.lastCheckpointTime, self.workLeft))
                    self.broken = False
                    self.numFailures += 1
                    restarting = self.env.process(self.do_restart(self.env.now - start, True))
                    yield restarting
                    yield self.waitForBq
                    self.ProcLog("Resumed after failureNoRestart")
                    # Need to restart the job from its latest ckpt
                    shouldRestart = True
                elif e.cause == "preempt":
                    self.ProcLog("Preempted, workLeft %d" %(self.workLeft))
                    self.numOfPreempts += 1
                    yield self.waitForBq
                    self.ProcLog("Resumed after preemption")
                    # Need to restart the job
                    shouldRestart = True
                else:
                    print("Unexpected interrupt in the middle of computing")
                    exit(-1)
        self.workLeft = 0
        self.endTime = self.env.now
        self.actualRunTime = self.endTime - self.startTime

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
            self.startAfresh = True
            self.numCkpts += 1
            self.isCkpting.succeed()
            self.isCkpting = self.env.event()
            self.inTheMiddle = False
            self.ProcLog("Done forced ckpting, work left %d, ckpts %d, lastCkpt %d" % (self.workLeft, self.numCkpts, self.lastCheckpointTime))
        except simpy.Interrupt as e:
            if e.cause == "failure":
                self.ckptFailures += 1
                self.isCkpting.fail()
                self.isCkpting = self.env.event()
                #self.ProcLog ("Checkpointing failure, lastCkpt %d, workLeft %d" % (self.lastCheckpointTime, self.workLeft))

    def do_restart(self, timeSinceLastInterruption, noRestart=False):
        """Restart the process after a failure."""
        delta = self.ckptTime
        try:
            self.ProcLog("Attempting to restart from ckpt #%d, taken at %d" % (self.numCkpts, self.lastCheckpointTime))
            self.lostWork += timeSinceLastInterruption
            if not noRestart:
                assert self.broken == True
                yield self.env.timeout(delta)
            # Done with restart without errors
            self.ProcLog("Restart successful... going back to compute")
        except simpy.Interrupt as e:
            if (e.cause == "failure"):
                # TODO: Handle failures during a restart
                print("Failure in the middle of a restart... will attempt restart again")
                exit(-1)
                #self.do_restart()

    def __str__(self):
        # FIXME: Fix actual runtime
        return "%s, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d" %\
               (self.name, self.numCkpts, self.numFailures, self.ckptFailures, self.numOfPreempts,
                self.totalComputeTime, self.ckptTime, self.lostWork, self.submissionTime,
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

    # Create a batch queue
    mymachine = simpy.Resource(env, MAX_PARALLEL_PROCESSES)
    batchQ = BatchQueue(env, MAX_CIRC_Q_LEN, mymachine)

    testProcesses = [Process(env, 'Process %d' % i, time_to_checkpoint() + i*10, mymachine)
                     for i in range(NUM_PROCESSES)]

    simulateArrivalOfJobs(env, testProcesses, batchQ)
    env.process(batchQ.runBq(False))
    # Execute
    env.run()

    # Analyis/results
    print("******************************************************")
    print("******************FINAL DATA**************************")
    print("******************************************************")
    print("Process #, # Ckpts, # Total Failures, # Failure During Ckpt, # Preempts,"\
          " Compute Time, Ckpt Time, Lost Work, Submission Time, Start Time,"\
          " End Time, Actual Run Time")
    for p in testProcesses:
        if int((p.numCkpts + p.numFailures) * p.ckptTime +\
           p.lostWork + p.totalComputeTime) != int(p.actualRunTime):
            print("Warning")
        print(p)

if __name__ == "__main__":
    main(len(sys.argv), sys.argv)
