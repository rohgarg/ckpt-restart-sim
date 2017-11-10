#!/sw/bin/python2.7

import simpy
from simpy.util import start_delayed
from collections import deque
import os, sys, math, random
import numpy as np
import argparse as ap
from inspect import currentframe, getframeinfo
import scipy
import scipy.stats
import itertools
from scipy.stats import exponweib
from scipy.special import gamma
from tqdm import tqdm

"""
Round-robin batch queue simulator.

A process runs until it completes N=1 checkpoints. After the
N'th checkpoint, the next process in the queue is scheduled
for execution. In case of a failure, the executions starts
from the latest checkpoint of the first process in the queue.
"""

def HOURS_TO_SECS(x):
    return x*3600.0

def SECS_TO_HOURS(x):
    return x/3600.0

RANDOM_SEED = 42
INFINITE = HOURS_TO_SECS(10000.0)    # Avg. processing time in hours
PT_MEAN = HOURS_TO_SECS(1000.0)    # Avg. processing time in hours
PT_SIGMA = HOURS_TO_SECS(100.0)   # Sigma of processing time
MTBF = HOURS_TO_SECS(10.0)        # Mean time to failure in hours
BREAK_MEAN = 1 / MTBF             # Param. for expovariate distribution
NUM_PROCESSES = 7                 # Number of processes
MAX_PARALLEL_PROCESSES = 1
MAX_CIRC_Q_LEN = NUM_PROCESSES + 1
CKPT_THRESH = 10
MONITOR_GAP = 10.0      # We note the various params every MONITOR_GAP seconds
ckptOvhdAware = False

HELP="This simulator implements the following policy.\n\n"\
     "  - All jobs are submitted at the beginning.\n\n"\
     "  - A job runs until it completes N=1 checkpoints.\n\n"\
     "  - After the N'th checkpoint, the next job in queue is scheduled for \n"\
     "    execution.\n\n"\
     "  - In case of a failure, the execution starts from the latest checkpoint \n"\
     "    of the first job in the queue.\n\n"

# Shape parameter for Weibull distr.
WEIBULL_SHAPE = 0.60
WEIBULL_SCALE = MTBF/gamma(1.0+1.0/WEIBULL_SHAPE)

# Failures are injected after a delay of 100
INITIAL_FAILURE_DELAY = 200

enableBqLogs = False
enableProcLogs = False
useWeibull = False

def time_per_process():
    """Return a randomly generated compute time."""
    #return int(random.normalvariate(PT_MEAN, PT_SIGMA))
    return PT_MEAN

def time_to_failure():
    """Return time until next failure for a machine."""
    if not useWeibull:
        nextFailure = int(random.expovariate(BREAK_MEAN))
    else:
        # The Weibull distr. generates many errors.
        #nextFailure = int(np.random.weibull(WEIBULL_K)*98.0) # Gives MTBF to be 200
        #nextFailure = int(exponweib.rvs(1.0, WEIBULL_SHAPE, scale=WEIBULL_SCALE))
        nextFailure = int(exponweib.rvs(1.0, WEIBULL_SHAPE, scale=WEIBULL_SCALE))
    return nextFailure
    #return MTBF

def time_to_checkpoint():
    return 10

def time_to_preempt():
    return 250

class BatchQueue(object):
    """Represents and simulates a batch queue"""

    def __init__(self, myenv, max_circ_length, nodes, noPreemption=False):
        self.env = myenv
        self.maxLength = max_circ_length
        self.circQ = deque([], self.maxLength)
        self.allJobs = []
        self.numPreempts = 0
        self.process = None
        self.noPreemption = noPreemption
        self.numFailures = 0
        self.machine = nodes
        self.currentProc = None
        self.monitorDict = {'wd': [], 'lw': [], 'ckpts': [], 'rsts': [], 'failureTimes': []}
        self.savedJobs = []

    def BqLog(self, msg, showLogs=False):
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
        #self.env.process(self.monitorWorkDone())
        self.env.process(self.preempt())
        self.savedJobs = self.allJobs[:]
        while True:
            try:
                yield self.process
                self.env.exit()
            except simpy.Interrupt as e:
                self.process.interrupt(e.cause)

    def monitorWorkDone(self):
        tw = sum([p.totalComputeTime for p in self.savedJobs])
        oldtwd = sum([p.totalComputeTime - p.workLeft for p in self.savedJobs])
        #with tqdm(total=100, leave=False) as pbar:
        while len(self.circQ) > 0 or (self.currentProc and self.currentProc.workLeft > 0):
           yield self.env.timeout(MONITOR_GAP)
           if len(self.circQ) >= 0 and \
               self.currentProc and self.currentProc.workLeft > 0:
               lw = sum([p.lostWork for p in self.savedJobs])
               newtwd = sum([p.totalComputeTime - p.workLeft for p in self.savedJobs])
               ckpts = sum([p.numCkpts for p in self.savedJobs])
               rsts = sum([p.numRestarts for p in self.savedJobs])
               #self.monitorDict['wd'].append(twd)
               self.monitorDict['lw'].append(lw)
               self.monitorDict['ckpts'].append(ckpts)
               self.monitorDict['rsts'].append(rsts)
               #pbar.update(100*(newtwd-oldtwd)/tw)
               oldtwd = newtwd

    def preempt(self):
        self.BqLog("Starting preemption")
        while len(self.circQ) > 0 or (self.currentProc and self.currentProc.workLeft > 0):
            t = PT_MEAN
            self.BqLog("Interrupt after %d seconds" % (t))
            yield self.env.timeout(t)
            if len(self.circQ) >= 0 and self.currentProc.endTime == 0:
               self.BqLog("Interrupting %s" % (self.currentProc.name))
               self.numFailures += 1
               self.process.interrupt(cause="removeProcFromQ")

    def inject_failure(self):
        """Break the machine every now and then."""
        # Inject a failure only if there's a process running
        self.BqLog("Starting failure injection")
        while len(self.circQ) > 0 or (self.currentProc and self.currentProc.workLeft > 0):
            t = time_to_failure()
            self.BqLog("Inject the next failure after %d seconds" % (t))
            if t < 5:
              continue
            yield self.env.timeout(t)
            if len(self.circQ) >= 0 and \
               self.currentProc.endTime == 0:
                # Only break the machine if it is currently computing,
                #  and if current proc is not restarting
                self.BqLog("Injecting a failure in %s" % (self.currentProc.name))
                self.numFailures += 1
                self.process.interrupt(cause="failure")

    def runBqHelper(self, with_preempt=True):
        idx = 0
        while len(self.circQ) > 0:
          self.BqLog("Waiting for request")
          with self.machine.request() as req:
            yield req
            try:
                # Run the head of the queue for a while
                p = self.circQ[idx]
                self.BqLog("Will try to exec %s next" % (p.name))
                if p.workLeft == 0:
                    self.BqLog("Done with %s" % (p.name))
                    self.circQ.remove(p)
                    idx = idx if len(self.circQ) == 0 else idx % len(self.circQ)
                    continue
                # Run, or Restart (if the process has at least one checkpoint)
                self.currentProc = p
                if p.startAfresh:
                    start = self.env.now
                    queueTime = self.env.now
                    self.BqLog("Starting %s" %(p.name))
                    #print(p.numCkptsBeforeYield)
                    if p.preemptionTime == 0:
                       p.preemptionTime = PT_MEAN - self.env.now
                    p.process = self.env.process(p.runJob())
                elif p.isRestarting and not p.isPreempted:
                    start = self.env.now
                    self.BqLog("%s recovering from failure... nothing to do" %(p.name))
                elif p.isPreempted:
                    self.BqLog("Resuming %s" % (p.name))
                    queueTime = self.env.now
                    p.waitForBq.succeed()
                    self.BqLog("Waiting for resume for %s to complete" % (p.name))
                    yield p.resumeCompleted
                    self.BqLog("Restarted %s" % (p.name))
                    p.isPreempted = False
                    start = self.env.now
                else:
                    assert len(self.circQ) == 1
                    queueTime = self.env.now
                # Simple FIFO scheduling after a fault
                self.BqLog("Wait for %s to complete or ckpt" %(p.name))
                yield p.waitForComputeToEnd | p.waitForCkptToComplete
                p.actualRunTime += self.env.now - queueTime
                self.BqLog("%s completed, AT: %d, QT: %d" %(p.name, p.actualRunTime, queueTime))
                if p.workLeft == 0:
                    self.BqLog("Done with %s at end" % (p.name))
                    self.circQ.remove(p)
                    idx = idx if len(self.circQ) == 0 else idx % len(self.circQ)
                    continue
                if len(self.circQ) > 1:
                    # No need to preempt a single process
                    idx = (idx + 1) % len(self.circQ)
                    self.BqLog("Preempting %s from execution, AT: %d, QT: %d" % (p.name, p.actualRunTime, queueTime))
                    p.isPreempted = True
                    p.numPreempts += 1
                    p.process.interrupt(cause="preemptImmediate")
                continue
            except simpy.Interrupt as e:
                if e.cause == "failure":
                    # First, add the current job for execution at a later time
                    self.BqLog("Encountered a failure while executing %s" % (p.name))
                    p.numFailures += 1
                    if self.noPreemption:
                        # Force simple FIFO queue, with no preemption
                        p.isRestarting = True
                        p.process.interrupt(cause="failure")
                        continue
                    # Reset the counter to start from the head of the queue
                    #idx = 0
                    p.actualRunTime += self.env.now - queueTime
                    self.BqLog("Preempting %s from execution, AT: %d, QT: %d" % (p.name, p.actualRunTime, queueTime))
                    p.isPreempted = True
                    p.process.interrupt(cause="preemptImmediate")
                    save = idx
                    idx = (idx + (2 - (idx % 2))) # this gets us to the next pair (or factor of 2): 0 --> 2, 1 --> 2, 2 --> 4, 3 --> 4, 4 --> 6 ...
                    if idx >= len(self.circQ):
                      idx = 0
                    self.BqLog("Moved idx from %d to %d" % (save, idx))
                    twd = sum([x.totalComputeTime - x.workLeft for x in self.savedJobs])
                    self.monitorDict['wd'].append(twd)
                    self.monitorDict['failureTimes'].append(self.env.now)
                    #if not ckptOvhdAware:
                    #    random.shuffle(self.circQ)
                elif e.cause == "removeProcFromQ":
                    self.BqLog("Done with %s at end" % (p.name))
                    p.actualRunTime += self.env.now - queueTime
                    self.BqLog("Preempting %s from execution, AT: %d, QT: %d" % (p.name, p.actualRunTime, queueTime))
                    p.isPreempted = True
                    p.process.interrupt(cause="removeProcFromQ")
                    twd = sum([x.totalComputeTime - x.workLeft for x in self.savedJobs])
                    self.monitorDict['wd'].append(twd)
                    self.circQ.remove(p)
                    idx = 0
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
        self.totalComputeTime = INFINITE # time_per_process()
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
        self.waitForBq = myenv.event()
        self.waitForComputeToEnd = myenv.event()
        self.waitForCkptToComplete = myenv.event()
        self.resumeCompleted = myenv.event()
        self.numPreempts = 0
        self.usefulWork = 0
        self.lastComputeStartTime = 0
        self.lastCkptInstant = 0
        self.inTheMiddle = False
        self.restartFailures = 0
        self.numRestarts = 0
        self.lostRestartTime = 0
        self.lostCkptTime = 0
        self.numCkptsBeforeYield = 0
        self.startAfresh = True
        self.preemptionTime = 0
        self.oci = int(math.sqrt(2*MTBF*self.ckptTime) - self.ckptTime)

    def updateCkptTime(self, delta):
        self.ckptTime = delta
        self.oci = int(math.sqrt(2*MTBF*self.ckptTime) - self.ckptTime)

    def submitToQueue(self):
        self.submissionTime = self.env.now

    def ProcLog(self, msg):
        if enableProcLogs:
            print("[%d][%4d]: %s: %s" % (self.env.now, currentframe().f_back.f_lineno, self.name, msg))

    #def preempt(self):
    #    self.ProcLog("Starting preemption")
    #    while self.endTime == 0:
    #        t = self.preemptionTime
    #        if t == 0:
    #          self.ProcLog("Nothing to do")
    #          break
    #        self.ProcLog("Interrupt after %d seconds" % (t))
    #        yield self.env.timeout(t)
    #        if self.endTime == 0:
    #           self.ProcLog("Interrupting")
    #           self.process.interrupt(cause="removeProcFromQ")
    #        else:
    #           break

    def runJob(self):
        """Simulate compute for the given amount of total work.
        """
        self.inTheMiddle = False
        self.startTime = self.env.now
        self.startAfresh = False
        numCkptsInThisSchedule = 0
        #if self.preemptionTime > 0:
        #   self.env.process(self.preempt())
        while self.workLeft:
            try:
                computeTime = min(self.oci, self.workLeft)
                self.ProcLog("Will ckpt after %d time" % (self.oci))
                if computeTime <= 0:
                    self.endTime = self.env.now
                    self.env.exit()

                # Simulate restart when requested by the bq, only if we have at least 1 ckpt
                if self.isPreempted:
                   if self.numCkpts > 0:
                       restarting = self.env.process(self.do_restart(0))
                   else:
                       restarting = self.env.process(self.do_restart(0, True))
                   numCkptsInThisSchedule = 0
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
                if self.workLeft <= self.oci:
                   self.workLeft = 0
                   self.endTime = self.env.now
                   self.waitForComputeToEnd.succeed()
                   self.waitForComputeToEnd = self.env.event()
                   self.env.exit()

                self.ProcLog("Ckpting, workleft %d" % (self.workLeft))
                self.inTheMiddle = True
                ckptingProc = self.env.process(self.do_ckpt())

                yield ckptingProc
                numCkptsInThisSchedule += 1
                self.usefulWork += computeTime
                if self.numCkptsBeforeYield != 0 and numCkptsInThisSchedule == self.numCkptsBeforeYield:
                  #self.workLeft = 0
                  #self.endTime = self.env.now
                  #self.waitForComputeToEnd.succeed()
                  #self.waitForComputeToEnd = self.env.event()
                  #self.env.exit()
                  self.waitForCkptToComplete.succeed()
                  self.waitForCkptToComplete = self.env.event()
                self.inTheMiddle = False
            except simpy.Interrupt as e:
                if e.cause == "failure":
                    # fallback to the last checkpoint
                    if self.inTheMiddle:
                        self.inTheMiddle = False
                        ckptingProc.interrupt(e.cause)
                        self.ProcLog("Checkpointing failure, lastCkpt %d, workLeft %d" % (self.lastCheckpointTime, self.workLeft))
                    self.isRestarting = True
                    self.ProcLog("Incurred a failure, work left %d" % (self.workLeft))
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
                        ckptingProc.interrupt(e.cause)
                        self.ProcLog("Checkpointing failure, lastCkpt %d, workLeft %d" % (self.lastCheckpointTime, self.workLeft))
                    self.isRestarting = False
                    restarting = self.env.process(self.do_restart(self.env.now - start, True))
                    yield restarting
                    self.ProcLog("preemptImmediate: Waiting for bq")
                    yield self.waitForBq
                    self.waitForBq = self.env.event()
                    self.ProcLog("Resumed after preemptImmediate")
                    # Need to restart the job from its latest ckpt
                    self.isPreempted = True
                elif e.cause == "removeProcFromQ":
                    if self.inTheMiddle:
                        self.inTheMiddle = False
                        ckptingProc.interrupt(e.cause)
                        self.ProcLog("Checkpointing failure, lastCkpt %d, workLeft %d" % (self.lastCheckpointTime, self.workLeft))
                    self.isRestarting = False
                    self.ProcLog("removeProcFromQ: ending now")
                    self.workLeft = 0
                    self.endTime = self.env.now
                    #self.waitForComputeToEnd.succeed()
                    #self.waitForComputeToEnd = self.env.event()
                    self.env.exit()
                else:
                    print("Unexpected interrupt in the middle of computing")
                    exit(-1)
        self.workLeft = 0
        self.endTime = self.env.now

    def do_ckpt(self):
        self.inTheMiddle = False
        try:
            delta = self.ckptTime
            self.ProcLog("Ckpting, workleft %d" % (self.workLeft))
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
            self.inTheMiddle = False
            self.ProcLog("Done ckpting, work left %d, ckpts %d, lastCkpt %d" % (self.workLeft, self.numCkpts, self.lastCheckpointTime))
        except simpy.Interrupt as e:
            if e.cause in ["failure", "preemptImmediate", "removeProcFromQ"]:
                self.ckptFailures += 1
                self.inTheMiddle = False
                self.lostCkptTime += self.env.now - ckptStartTime
                self.ProcLog("Checkpointing failure, lastCkpt %d, workLeft %d" % (self.lastCheckpointTime, self.workLeft))
            else:
                print("Unexpected interrupt in the middle of ckpting")
                exit(-1)

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
                    #yield self.env.timeout(int(delta/2.0))
                    yield self.env.timeout(1)
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
                    self.waitForBq = self.env.event()
                    self.ProcLog("preemptImmediate: restart mode: resumed")
                    #self.env.exit()
                elif e.cause == "removeProcFromQ":
                    self.ProcLog("removeProcFromQ: restart mode: ending now")
                    self.env.exit()
                else:
                    print("Unexpected interrupt in the middle of ckpting")
                    exit(-1)

    def __str__(self):
        return "%s, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d" %\
               (self.name, self.numCkpts, self.numFailures, self.numRestarts, self.restartFailures,
                self.ckptFailures, self.numPreempts, self.totalComputeTime, self.ckptTime,
                SECS_TO_HOURS(self.lostWork), self.lostRestartTime, self.lostCkptTime, self.submissionTime,
                self.startTime, self.endTime, self.actualRunTime, SECS_TO_HOURS(self.usefulWork), self.numCkptsBeforeYield)

def simulateArrivalOfJobs(env, processes, batchQ):
    """Simulate random arrival of jobs"""
    for p in processes:
        batchQ.addToBq(p)

def showResults(args, batchQ):
    failureDistr = "Weibull" if useWeibull else "Exponential"
    sortList = "Ckpt Overhead-aware" if args.sorted else "Ckpt Overhead-unaware"
    xIdx, yIdx = 0, 0
    nRows, nCols = 3, 0
    if args.show_throughput_results:
       nCols += 1
    if args.show_lostwork_results:
       nCols += 1
    if args.show_ckpt_results:
       nCols += 1
    if args.show_restart_results:
       nCols += 1
    f, axs = plt.subplots(nRows, nCols if nCols > 1 else 2)
    f.suptitle("%s (Failure injection using %s distr.)" % (sortList, failureDistr))
    if args.show_throughput_results:
        axs[0,yIdx].set_title("Work done (Throughput)")
        axs[0,yIdx].plot(batchQ.monitorDict['instantenousWd'], label="Instant")
        axs[0,yIdx].set_ylabel("Work done since last failure")
        axs[1,yIdx].plot(batchQ.monitorDict['overTimeWd'], label="Work Done/Current Time")
        axs[1,yIdx].set_ylabel("Work done/Current Time")
        print(str(len(batchQ.monitorDict['wd'])))
        print(str(batchQ.numFailures))
        axs[2,yIdx].plot(batchQ.monitorDict['wd'], label="Work Done")
        axs[2,yIdx].set_ylabel("Work done")
        axs[2,yIdx].set_xlabel("Failure #")
        yIdx += 1
    if args.show_lostwork_results:
        axs[0,yIdx].set_title("Lost Work due to failures")
        axs[0,yIdx].plot(batchQ.monitorDict['instantenousLw'], label="Instantenous Lost Work")
        axs[0,yIdx].set_ylabel("Lost work over last 5 time units")
        axs[1,yIdx].plot(batchQ.monitorDict['overTimeLw'], label="Lost work/Current Time")
        axs[1,yIdx].set_ylabel("Lost work/Current Time")
        axs[2,yIdx].plot(batchQ.monitorDict['lw'], label="Lost work")
        axs[2,yIdx].set_ylabel("Lost Work")
        axs[2,yIdx].set_xlabel("Time")
        yIdx += 1
    if args.show_ckpt_results:
        axs[0,yIdx].set_title("# Checkpoints")
        axs[0,yIdx].plot(batchQ.monitorDict['instantenousCkpts'], label="Instantenous # Ckpts")
        axs[0,yIdx].set_ylabel("# Ckpts over last 5 time units")
        axs[1,yIdx].plot(batchQ.monitorDict['overTimeCkpts'], label="# Ckpts/Current Time")
        axs[1,yIdx].set_ylabel("# Ckpts/Current Time")
        axs[2,yIdx].plot(batchQ.monitorDict['ckpts'], label="# Ckpts")
        axs[2,yIdx].set_ylabel("# Ckpts")
        axs[2,yIdx].set_xlabel("Time")
        yIdx += 1
    if args.show_restart_results:
        axs[0,yIdx].set_title("# Restarts")
        axs[0,yIdx].plot(batchQ.monitorDict['instantenousRsts'], label="Instantenous # Restarts")
        axs[0,yIdx].set_ylabel("# Restarts over last 5 time units")
        axs[1,yIdx].plot(batchQ.monitorDict['overTimeRsts'], label="# Restarts/Current Time")
        axs[1,yIdx].set_ylabel("# Restarts/Current Time")
        axs[2,yIdx].plot(batchQ.monitorDict['rsts'], label="# Restarts")
        axs[2,yIdx].set_ylabel("# Restarts")
        axs[2,yIdx].set_xlabel("Time")
        yIdx += 1

def saveResults(args, batchQ):
    failureDistr = "Weibull" if useWeibull else "Exponential"
    sortList = "aware" if args.sorted else "unaware"
    if (args.file_name):
        origFileName = args.file_name
        fileName = "%s-%s-%s-%sWd.csv" % (origFileName, sortList, failureDistr[:3], "instantenous")
        batchQ.monitorDict['instantenousWd'].tofile(fileName, sep=',')
        fileName = "%s-%s-%s-%sWd.csv" % (origFileName, sortList, failureDistr[:3], "OverTime")
        batchQ.monitorDict['overTimeWd'].tofile(fileName, sep=',')
        fileName = "%s-%s-%s-Wd.csv" % (origFileName, sortList, failureDistr[:3])
        np.asarray(batchQ.monitorDict['wd']).tofile(fileName, sep=',')
        fileName = "%s-%s-%s-%sLw.csv" % (origFileName, sortList, failureDistr[:3], "instantenous")
        batchQ.monitorDict['instantenousLw'].tofile(fileName, sep=',')
        fileName = "%s-%s-%s-%sLw.csv" % (origFileName, sortList, failureDistr[:3], "OverTime")
        batchQ.monitorDict['overTimeWd'].tofile(fileName, sep=',')
        fileName = "%s-%s-%s-Lw.csv" % (origFileName, sortList, failureDistr[:3])
        np.asarray(batchQ.monitorDict['lw']).tofile(fileName, sep=',')

def computeResults(args, batchQ):
    tmp = batchQ.monitorDict['wd']
    tmp2 = batchQ.monitorDict['failureTimes']
    instantenousWd = np.asarray(np.diff(tmp))
    WdOverTime = np.asarray([x/float(y) for (x,y) in zip(tmp, tmp2)])

    tmp = batchQ.monitorDict['lw']
    instantenousLw = np.asarray(np.diff(tmp))
    LwOverTime = np.asarray([x/float(i*MONITOR_GAP) for (x,i) in zip(tmp, range(len(tmp))) if i > 0.0])

    tmp = batchQ.monitorDict['ckpts']
    instantenousCk = np.asarray(np.diff(tmp))
    CkOverTime = np.asarray([x/float(i*MONITOR_GAP) for (x,i) in zip(tmp, range(len(tmp))) if i > 0.0])

    tmp = batchQ.monitorDict['rsts']
    instantenousRsts = np.asarray(np.diff(tmp))
    RstsOverTime = np.asarray([x/float(i*MONITOR_GAP) for (x,i) in zip(tmp, range(len(tmp))) if i > 0.0])

    batchQ.monitorDict['instantenousWd'] = instantenousWd
    batchQ.monitorDict['overTimeWd'] = WdOverTime
    batchQ.monitorDict['instantenousLw'] = instantenousLw
    batchQ.monitorDict['overTimeLw'] = LwOverTime
    batchQ.monitorDict['instantenousCkpts'] = instantenousCk
    batchQ.monitorDict['overTimeCkpts'] = CkOverTime
    batchQ.monitorDict['instantenousRsts'] = instantenousRsts
    batchQ.monitorDict['overTimeRsts'] = RstsOverTime

# Return the switch point for the lw app
def getSwitchPoint(lwDelta, hwDelta):
# lw, hw, mtbf, sp
# (2,50,5,80)
# (2,150,5,80)
# (2,1800,5,70)
# (2,2700,5,90)
# (50,150,5,15)
# (50,1800,5,14)
# (50,2700,5,17)
# (150,1800,5,9)
# (150,2700,5,10)
# (1800,2700,5,2)

# (2,50,20,147)
# (2,150,20,150)
# (2,1800,20,130)
# (2,2700,20,155)
# (50,150,20,30)
# (50,1800,20,26)
# (50,2700,20,32)
# (150,1800,20,18)
# (150,2700,20,18)
# (1800,2700,20,4)

  # ckptOvhds = [2, 50, 150, 1800, 2700]
  if   lwDelta == 2 and hwDelta == 50:
    return 80
  elif lwDelta == 2 and hwDelta == 150:
    return 80
  elif lwDelta == 2 and hwDelta == 1800:
    return 70
  elif lwDelta == 2 and hwDelta == 2700:
    return 90
  elif lwDelta == 50 and hwDelta == 150:
    return 15
  elif lwDelta == 50 and hwDelta == 1800:
    return 14
  elif lwDelta == 50 and hwDelta == 2700:
    return 17
  elif lwDelta == 150 and hwDelta == 1800:
    return 9
  elif lwDelta == 150 and hwDelta == 2700:
    return 10
  elif lwDelta == 1800 and hwDelta == 2700:
    return 2
  elif lwDelta == hwDelta:  # Special case
    print("Special case: %d" % (lwDelta))
    return 0
  else:
    print("Unknown deltas: %d %d" % (lwDelta, hwDelta))
    assert False

#def makePairings(lst):
#  tmp = []
#  l = len(lst)
#  for i in range(l/2):
#    lst[i].numCkptsBeforeYield = getSwitchPoint(lst[i].ckptTime, lst[l-i-1].ckptTime)
#    tmp.append(lst[i])
#    lst[l-i-1].numCkptsBeforeYield = 0
#    tmp.append(lst[l-i-1])
#  return tmp

def makePairings(lst, ckptOvhds):
  tmp = []
  i = 0
  # ckptCombs = list(itertools.combinations(ckptOvhds, 2))
  # Pre-generated list
  ckptCombs = [(150, 2700), (1800, 2700), (150, 1800), (50, 2700), (1800, 2700), (150, 1800), (2, 150), (2, 2700), (50, 2700), (1800, 2700), (2, 50), (150, 1800), (1800, 2700), (150, 2700), (2, 2700), (2, 50), (2, 2700), (2, 150), (50, 1800), (50, 1800), (2, 50), (150, 2700), (50, 1800), (2, 1800), (2, 50), (1800, 2700), (50, 150), (2, 150), (50, 1800), (2, 150), (50, 150), (50, 2700), (50, 2700), (2, 1800), (150, 1800), (2, 2700), (150, 2700), (2, 1800), (2, 150), (1800, 2700), (50, 2700), (2, 150), (150, 2700), (50, 1800), (1800, 2700), (50, 1800), (50, 150), (50, 150), (50, 150), (2, 50)]

  def getRandomCombination(l):
    return random.randint(0, len(l) - 1)

  for i in xrange(0, len(lst), 2):
    # c = getRandomCombination(ckptCombs)
    c = i / 2
    lst[i].updateCkptTime(ckptCombs[c][0])
    lst[i].numCkptsBeforeYield = getSwitchPoint(ckptCombs[c][0], ckptCombs[c][1])
    lst[i + 1].updateCkptTime(ckptCombs[c][1])
    lst[i + 1].numCkptsBeforeYield = 0
    tmp.append(lst[i])
    tmp.append(lst[i + 1])
    
  return tmp

def main(argc, argv, argList=None):
    """Set up and start the simulation."""
    global NUM_PROCESSES, enableProcLogs, enableBqLogs, HELP, useWeibull,\
           PT_MEAN, MTBF, WEIBULL_SHAPE, WEIBULL_SCALE, ckptOvhdAware

    #final_out = 'Process checkpoint-restart simulator\n'
    final_out = ''
    #random.seed(RANDOM_SEED)  # constant seed for reproducibility

    # Create an environment and start the setup process
    env = simpy.Environment()
    parser = ap.ArgumentParser(prog="./rr_proposed_ckpt_sim_mod.py", description=HELP, formatter_class=ap.RawTextHelpFormatter)
    parser.add_argument("--run-time", type=int, help="Compute time (in hours) for each job. Default is 1000.")
    parser.add_argument("-p", "--proc_logs", action="store_true", help="Show run time logs from processes")
    parser.add_argument("-b", "--batchqueue_logs", action="store_true", help="Show run time logs from the batch-queue manager")
    parser.add_argument("-n", "--procs", type=int, default=NUM_PROCESSES, help="Max. number of processes to simulate (default: 7)")
    #parser.add_argument("-x", "--no_preempt", action="store_true", help="Disables preemption of currently executing "\
    #                                                                    "job on failure. This simulates the behavior "\
    #                                                                    "of a simple FIFO queue.")
    parser.add_argument("-w", "--use-weibull", action="store_true", help="Use Weibull distribution for failure injection. Default is to use exponential distribution")
    parser.add_argument("-f", "--file-name", type=str, help="Store lost work/throughput results in the given file.")
    parser.add_argument("-s", "--show-throughput-results", action="store_true", help="Show throughput results using matplotlib.")
    parser.add_argument("-l", "--show-lostwork-results", action="store_true", help="Show lost work results using matplotlib.")
    parser.add_argument("-c", "--show-ckpt-results", action="store_true", help="Show checkpoint results using matplotlib.")
    parser.add_argument("-r", "--show-restart-results", action="store_true", help="Show restart results using matplotlib.")
    parser.add_argument("--sorted", action="store_true", help="Submit jobs in increasing order of ckpt ovhd.")
    parser.add_argument("--ckpts-before-yield1", type=int, help="N1, as described above. Default is 1. 0 indicates no yield after a ckpt, i.e., FIFO policy.")
    parser.add_argument("--ckpts-before-yield2", type=int, help="N2, as described above. Default is 1. 0 indicates no yield after a ckpt, i.e., FIFO policy.")
    parser.add_argument("--mtbf", type=int, help="System MTBF in hours. Default is 10 hrs.")
    parser.add_argument("--weibull-shape", type=float, help="Weibull shape parameter. Default is 0.6.")
    parser.add_argument("--oci-scale-factor", type=float, help="Scaling factor for OCI of heavy application. Default is 1.0")
    if argList:
        args = parser.parse_args(argList)
    else:
        args = parser.parse_args()
    NUM_PROCESSES = args.procs
    MAX_CIRC_Q_LEN = NUM_PROCESSES + 1
    enableProcLogs = args.proc_logs
    enableBqLogs = args.batchqueue_logs
    useWeibull = args.use_weibull
    if args.run_time:
       PT_MEAN = HOURS_TO_SECS(args.run_time)
    if args.weibull_shape:
       WEIBULL_SHAPE = args.weibull_shape
       WEIBULL_SCALE = MTBF/gamma(1.0+1.0/WEIBULL_SHAPE)
    if args.mtbf:
       MTBF = HOURS_TO_SECS(args.mtbf)
       #print("MTBF: %d" %(MTBF))
       WEIBULL_SCALE = MTBF/gamma(1.0+1.0/WEIBULL_SHAPE)
       #print("SCALE: %f" %(WEIBULL_SCALE))

    # Create a batch queue
    mymachine = simpy.Resource(env, MAX_PARALLEL_PROCESSES)
    batchQ = BatchQueue(env, MAX_CIRC_Q_LEN, mymachine, False)
    showPlot = args.show_throughput_results | args.show_lostwork_results |\
               args.show_ckpt_results | args.show_restart_results

    ckptOvhds = [2, 50, 150, 1800, 2700]
    #ckptOvhds = [30*60, 1*60, 15*60, 4*60]
    testProcesses = [Process(env, 'Process %d' % i, ckptOvhds[random.randint(0, 4)], mymachine)
                     for i in range(NUM_PROCESSES)]
    # idx = 0
    # count = 1
    # for p in testProcesses:
    #   p.ckptTime = ckptOvhds[idx]
    #   p.oci = int(math.sqrt(2*MTBF*p.ckptTime) - p.ckptTime)
    #   count += 1
    #   if count > (len(testProcesses) / len(ckptOvhds)):
    #     count = 1
    #     idx += 1

    if args.oci_scale_factor:
        heavyProc = max(testProcesses, key=lambda p:p.ckptTime)
        heavyProc.oci *= args.oci_scale_factor

    myidx = 0
    #testProcesses[0].numCkptsBeforeYield = args.ckpts_before_yield1 if args.ckpts_before_yield1 != None else 1
    #testProcesses[1].numCkptsBeforeYield = args.ckpts_before_yield2 if args.ckpts_before_yield2 != None else 1
    #testProcesses[2].numCkptsBeforeYield = args.ckpts_before_yield1 if args.ckpts_before_yield1 != None else 1
    #testProcesses[3].numCkptsBeforeYield = args.ckpts_before_yield2 if args.ckpts_before_yield2 != None else 1
    if args.ckpts_before_yield1 == 0 and args.ckpts_before_yield2 == 0:
       testProcesses[0].preemptionTime = PT_MEAN / 2
       testProcesses[1].preemptionTime = PT_MEAN / 2
    # print(testProcesses[0].numCkptsBeforeYield)
    # print(testProcesses[1].numCkptsBeforeYield)
    #if args.ckpts_before_yield1 == None and args.ckpts_before_yield2 == None:
    #    for p in testProcesses:
    #        x = int((MTBF/2.0)/p.oci)
    #        p.numCkptsBeforeYield = 1 if x <= 0 else x
        #    x = args.ckpts_before_yield[myidx]
        #    p.numCkptsBeforeYield = 1 if x <= 0 else x
        #    myidx += 1

    if args.sorted:
      ckptOvhdAware = True
      # testProcesses.sort(key=lambda p:p.ckptTime)
      # testProcesses = makePairings(testProcesses)
      testProcesses = makePairings(testProcesses, ckptOvhds)
    else:
      random.shuffle(testProcesses)

    simulateArrivalOfJobs(env, testProcesses, batchQ)
    env.process(batchQ.runBq(False))
    # Execute
    env.run(until=(PT_MEAN+1))

    # Analyis/results
    #print("******************************************************")
    #print("******************FINAL DATA**************************")
    #print("******************************************************")

    #computeResults(args, batchQ)
    #saveResults(args, batchQ)
    #showResults(args, batchQ)

    #final_out += ("Process #, # Ckpts, # Total Failures, # Restarts, # Failed Restarts, # Failed Ckpts, # Preempts,"\
    #      " Compute Time, Ckpt Time, Lost Work, Lost Restart Time, Lost Ckpt Time, Submission Time, Start Time,"\
    #      " End Time, Actual Run Time, #CkptsBeforeYield\n")
    #for p in testProcesses:
    #    t1 = int(p.numCkpts * p.ckptTime + p.numRestarts * int(p.ckptTime/2.0) + p.lostWork + p.totalComputeTime + p.lostRestartTime)
    #    t2 = int(p.actualRunTime)
    #    if not p.restartFailures * p.ckptTime >= p.lostRestartTime:
    #      final_out += "Warning\n"
    #    if t1 != t2:
    #        final_out += "Warning: %d != %d\n" % (t1, t2)
    #    final_out += str(p)
    #    final_out += "\n"
    #final_out += ("Total Lost Ckpt Work: %d\n" % (sum([t.lostCkptTime for t in testProcesses])))
    #final_out += ("Total Lost Restart Work: %d\n" % (sum([t.lostRestartTime for t in testProcesses])))
    #final_out += ("End Time: %d\n" % (max(testProcesses, key=lambda p:p.endTime).endTime))
    #final_out += ("Total Ckpt Time: %d\n" % (sum([t.ckptTime * t.numCkpts for t in testProcesses])))
    #final_out += ("Total Lost Work: %d\n" % (sum([t.lostWork for t in testProcesses])))
    combined_total = 0
    combined_useful = 0
    combined_ckpt = 0
    combined_lost = 0
    #print("Total failures: %d" % (batchQ.numFailures))
    for p in testProcesses:
      useful_work = SECS_TO_HOURS(p.usefulWork)
      #print("%s %.2f %d" % (p.name, SECS_TO_HOURS(p.lostCkptTime), p.numCkpts))
      ckpt_time = SECS_TO_HOURS(p.ckptTime * p.numCkpts)
      lost_work = SECS_TO_HOURS(p.lostWork)
      #lost_work = SECS_TO_HOURS(p.lostWork + p.lostCkptTime) # + p.lostRestartTime)
      total =  useful_work + ckpt_time + lost_work
      #string = "%s (delta:%d secs): Total: %.2f, Useful: %.2f  Checkpoint: %.2f  Lost: %.2f\n" % \
      string = "%s, %d, %.2f, %.2f, %.2f, %.2f, %d, %d\n" % \
      (p.name, p.ckptTime, total, useful_work, ckpt_time, lost_work, p.numFailures, batchQ.numFailures)
      combined_total += total
      combined_useful += useful_work
      combined_ckpt += ckpt_time
      combined_lost += lost_work
      final_out += string
    #string = "Combined: Total: %.2f, Useful: %.2f  Checkpoint: %.2f  Lost: %.2f\n" % \
    #         (combined_total, combined_useful, combined_ckpt, combined_lost)
    #final_out += string
    if showPlot:
        plt.show()
    if argList:
        return final_out
    else:
        print(final_out)

if __name__ == "__main__":
    main(len(sys.argv), sys.argv)
