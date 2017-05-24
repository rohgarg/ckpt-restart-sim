#!/usr/bin/python2.7

import sys
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import itertools

def showResults(myres, axs, preempt):
    axs[0,0].plot(myres[0], label=preempt)
    axs[1,0].plot(myres[1], label="Work Done/Current Time")
    axs[2,0].plot(myres[2], label=preempt)

    axs[0,1].plot(myres[3], label=preempt)
    axs[1,1].plot(myres[4], label="Lost work/Current Time")
    axs[2,1].plot(myres[5], label=preempt)

f, axs = plt.subplots(3, 2, sharex=True)

origFileName = sys.argv[1]
failureDistr = "Weibull" if sys.argv[2][:3].lower() in ["wei"] else "Exponential"

preemptFileSubstr = "woPreempt" if sys else "wPreempt"

f.suptitle("Failure injection using %s distr." % (failureDistr))
axs[0,0].set_title("Work done (Throughput)")
axs[0,0].set_ylabel("Work done over last 5 time units")
axs[1,0].set_ylabel("Work done/Current Time")
axs[2,0].set_ylabel("Work done")
axs[2,0].set_xlabel("Time")

axs[0,1].set_title("Lost Work due to failures")
axs[0,1].set_ylabel("Lost work over last 5 time units")
axs[1,1].set_ylabel("Lost work/Current Time")
axs[2,1].set_ylabel("Lost Work")
axs[2,1].set_xlabel("Time")

res = []
for (x, y, z) in itertools.product(["Wd", "Lw"], ["woPreempt", "wPreempt"], ["instantenous", "OverTime", ""]):
    # Need this ugly switch because of the way files are named by the program
    if z == "OverTime":
      zc = x
      xc = z
    else:
      zc = z 
      xc = x
    fileName = "%s-%s-%s-%s%s.csv" % (origFileName, y, failureDistr[:3], zc, xc)
    print("Processing file: %s" % (fileName))
    with open(fileName, "r") as wdfile:
        for l in wdfile.readlines():
            res.append(l)
t = []
for r in res:
    t.append([float(x) for x in r.split(',')])

preemptLabel = "W/o Preemption"
wdResults = t[:3]
lwResults = t[6:9]
wdResults.extend(lwResults)
showResults(wdResults, axs, preemptLabel)

preemptLabel = "W/ Preemption"
wdResults1 = t[3:6]
lwResults1 = t[9:]
wdResults1.extend(lwResults1)
showResults(wdResults1, axs, preemptLabel)

plt.show()
