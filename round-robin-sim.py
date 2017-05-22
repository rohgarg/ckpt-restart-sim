#!/usr/bin/python2.7

import simpy
from collections import deque
import os, sys, math, random


"""
Simple round-robin batch queue simulator. Each process runs for a given
time quanta and is then preempted out for the next process in the queue.
"""
RANDOM_SEED = 42
PT_MEAN = 500.0        # Avg. processing time in minutes
PT_SIGMA = 100.0        # Sigma of processing time
MTBF = 300.0           # Mean time to failure in minutes
BREAK_MEAN = 1 / MTBF  # Param. for expovariate distribution
NUM_PROCESSES = 2      # Number of processes
MAX_PARALLEL_PROCESSES = 1
MAX_CIRC_Q_LEN = 3


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

    def addToBq(self, p):
        self.allJobs.append(p)
        p.submitToQueue();
        if len(self.circQ) < self.maxLength - 1:
            self.circQ.append(p)

    def runBq(self):
        self.process = self.env.process(self.runBqHelper())
        yield self.process
        #self.env.process(self.inject_failure())

    def inject_failure(self):
        """Break the machine every now and then."""
        while len(self.circQ):
            yield self.env.timeout(time_to_failure())
            if not len(self.circQ):
                # Only break the machine if it is currently computing.
                #print("Injecting a failure at %d" %(self.env.now))
                self.broken = True
                self.numFailures += 1
                self.process.interrupt(cause="failure")

    def runBqHelper(self):
        while len(self.circQ) > 0:
          with self.machine.request() as req:
            yield req
            try:
                # Run the head of the queue for a while
                p = self.circQ.popleft()
                if p.workLeft == 0:
                    print("BQ: Done with the queue at %d" %(self.env.now))
                    continue
                # Run, or Restart (if the process has at least one checkpoint)
                print("BQ: Starting %s at %d" %(p.name, self.env.now))
                if not p.haveCkpt:
                    start = self.env.now
                    p.process = self.env.process(p.runJob(p.haveCkpt))
                else:
                    print("BQ: Resuming %s at %d" % (p.name, self.env.now))
                    p.myTurn.succeed()
                    p.myTurn = self.env.event()
                    yield p.myTurn
                    start = self.env.now
                print("BQ: Will preempt %s after %d" %(p.name, time_to_preempt()))
                yield p.myTurn | self.env.timeout(time_to_preempt())
                if p.workLeft == 0:
                    print("BQ: Done with %s at %d. Len(Q): %d" %(p.name, self.env.now, len(self.circQ)))
                    if len(self.circQ) == 0:
                        self.env.exit()
                    continue
                # Then, preempt it after its quanta is over
                self.switchingJobs = True
                tempStart = self.env.now
                yield p.isCkpting
                tempEnd = self.env.now
                print("BQ: Preempt %s at %d" %(p.name, self.env.now))
                p.process.interrupt(cause="preempt")
                if tempEnd - tempStart == 0: # Avoid ckpting if the process just came out of a ckpt
                    yield self.env.process(p.do_ckpt())
                print("BQ: %s completed ckpting at %d, %d" %(p.name, self.env.now, len(self.circQ)))
                # Finally, add it back to the tail of the queue
                self.circQ.append(p)
                print("BQ: After adding %s completed ckpting at %d, %d" %(p.name, self.env.now, len(self.circQ)))
                self.switchingJobs = False
            except simpy.Interrupt as e:
                if e.cause == "failure":
                    p.process.interrupt(cause="failure")
                    self.circQ.append(p)
                else:
                    print("Unknown failure type. Exiting...")
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
        self.haveCkpt = False # True once you have taken the first ckpt
        self.isCkpting = myenv.event() # True during checkpointing
        self.myTurn = myenv.event()
        self.numOfPreempts = 0;
        self.lastComputeStartTime = 0;

    def submitToQueue(self):
        self.submissionTime = self.env.now

    def runJob(self, shouldRestart=False):
        """Simulate compute for the given amount of total work.
        """
        inTheMiddle = False
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
                   self.myTurn.succeed()
                   self.myTurn = self.env.event()
                # Start computing
                start = self.env.now
                self.lastComputeStartTime = start
                print("%s: Main Starting compute for %d at %d, workleft %d" % (self.name, computeTime, self.env.now, self.workLeft))
                yield self.env.timeout(computeTime)
                if self.workLeft < oci:
                   self.workLeft = 0
                   self.endTime = self.env.now
                   self.actualRunTime = self.endTime - self.startTime
                   self.myTurn.succeed()
                   self.myTurn = self.env.event()
                   self.env.exit()
                print("%s: Main Starting ckpting at %d, workleft %d" % (self.name, self.env.now, self.workLeft))
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
                self.haveCkpt = True
                self.numCkpts += 1
                inTheMiddle = False
                self.isCkpting.succeed()
                self.isCkpting = self.env.event()
                print("%s: Main Done ckpting at %d, work left %d, ckpts %d, lastCkpt %d" % (self.name, self.env.now, self.workLeft, self.numCkpts, self.lastCheckpointTime))
            except simpy.Interrupt as e:
                if e.cause == "failure":
                    # fallback to the last checkpoint
                    if inTheMiddle:
                        inTheMiddle = False
                        self.ckptFailures += 1
                        self.isCkpting.fail()
                        self.isCkpting = self.env.event()
                        #print ("%s: Failure in the middle of a checkpoint at %d, lastCkpt %d, workLeft %d" % (self.name, self.env.now, self.lastCheckpointTime, self.workLeft))
                    self.broken = True
                    #print("Incurred a failure at %d, work left %d" % (self.env.now, self.workLeft))
                    restarting = self.env.process(self.do_restart(self.env.now - start))
                    yield restarting
                    #print("Done restarting at %d, work left %d, lost work %d" % (self.env.now, self.workLeft, self.lostWork))
                    self.broken = False
                elif e.cause == "preempt":
                    print("%s preempted at %d, workLeft %d" %(self.name, self.env.now, self.workLeft))
                    self.numOfPreempts += 1
                    yield self.myTurn
                    print("%s resumed at %d" %(self.name, self.env.now))
                    shouldRestart = True
                else:
                    print("Unexpected interrupt in the middle of computing")
                    exit(-1)
        self.workLeft = 0
        self.endTime = self.env.now
        self.actualRunTime = self.endTime - self.startTime

    def do_ckpt(self):
        inTheMiddle = False
        try:
            delta = self.ckptTime
            print("%s: Starting ckpting at %d, workleft %d" % (self.name, self.env.now, self.workLeft))
            inTheMiddle = True
            self.isCkpting = self.env.event()
            ckptStartTime = self.env.now
            yield self.env.timeout(delta)
            timeSinceLastInterruption = ckptStartTime - self.lastComputeStartTime;
            # Done with ckpting, now
            #  first, save the progress made since the last interruption, and
            self.workLeft -= timeSinceLastInterruption
            #  second, update the latest ckpt time
            self.lastCheckpointTime += timeSinceLastInterruption
            # ... and increment the number of ckpts
            self.haveCkpt = True
            self.numCkpts += 1
            inTheMiddle = False
            self.isCkpting.succeed()
            self.isCkpting = self.env.event()
            print("%s: Done ckpting at %d, work left %d, ckpts %d, lastCkpt %d" % (self.name, self.env.now, self.workLeft, self.numCkpts, self.lastCheckpointTime))
        except simpy.Interrupt as e:
            if e.cause == "failure":
                self.ckptFailures += 1
                self.isCkpting.fail()
                self.isCkpting = self.env.event()
                #print ("%s: Failure in the middle of a checkpoint at %d, lastCkpt %d, workLeft %d" % (self.name, self.env.now, self.lastCheckpointTime, self.workLeft))

    def do_restart(self, timeSinceLastInterruption):
        """Restart the process after a failure."""
        delta = self.ckptTime
        assert self.broken == True
        try:
            #print("Attempting to restart from ckpt #%d, taken at %d" % (self.numCkpts, self.lastCheckpointTime))
            self.lostWork += timeSinceLastInterruption
            yield self.env.timeout(delta)
            # Done with restart without errors
            #print("Restart successful... going back to compute")
        except simpy.Interrupt as e:
            if (e.cause == "failure"):
                # TODO: Handle failures during a restart
                print("Failure in the middle of a restart... will attempt restart again")
                exit(-1)
                #self.do_restart()

    def __str__(self):
        return "%s, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d" %\
               (self.name, self.numCkpts, self.numFailures, self.ckptFailures, self.numOfPreempts,
                self.totalComputeTime, self.ckptTime, self.lostWork, self.submissionTime,
                self.startTime, self.endTime, self.actualRunTime)

def simulateArrivalOfJobs(env, processes, batchQ):
    """Simulate random arrival of jobs"""
    for p in processes:
        batchQ.addToBq(p)
#    # Submit four initial jobs
#    for p in processes[:4]:
#        env.process(p.submitToQueue())
#
#    # Create more cars while the simulation is running
#    for p in processes[4:]:
#        yield env.timeout(random.randint(5, 7))
#        env.process(p.submitToQueue())

def main(argc, argv):
    """Set up and start the simulation."""

    print('Process checkpoint-restart simulator')
    random.seed(RANDOM_SEED)  # constant seed for reproducibility

    # Create an environment and start the setup process
    env = simpy.Environment()

    # Create a batch queue
    mymachine = simpy.Resource(env, MAX_PARALLEL_PROCESSES)
    batchQ = BatchQueue(env, MAX_CIRC_Q_LEN, mymachine)

    testProcesses = [Process(env, 'Process %d' % i, time_to_checkpoint(), mymachine)
                     for i in range(NUM_PROCESSES)]

    simulateArrivalOfJobs(env, testProcesses, batchQ)
    env.process(batchQ.runBq())
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
