#!/usr/bin/python2.7 -u

import sys
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import itertools
import progressbar

def showResults(myres, axs, preempt, results, pbar=None):
    global progress
    results.append(axs[0,0].plot(myres[0], label=preempt)[0])
    progress += 1
    pbar.update(progress)
    results.append(axs[1,0].plot(myres[1], label=preempt)[0])
    progress += 1
    pbar.update(progress)
    results.append(axs[2,0].plot(myres[2], label=preempt)[0])
    progress += 1
    pbar.update(progress)

    results.append(axs[0,1].plot(myres[3], label=preempt)[0])
    progress += 1
    pbar.update(progress)
    results.append(axs[1,1].plot(myres[4], label=preempt[0]))
    progress += 1
    pbar.update(progress)
    results.append(axs[2,1].plot(myres[5], label=preempt)[0])
    progress += 1
    pbar.update(progress)

f, axs = plt.subplots(3, 2)
bar = progressbar.ProgressBar(redirect_stdout=True, max_value=100)
bar.start()
progress = 0

origFileName = sys.argv[1]
failureDistr = "Weibull" if sys.argv[2][:3].lower() in ["wei"] else "Exponential"

f.suptitle("Failure injection using %s distr." % (failureDistr))
axs[0,0].set_title("Work done (Throughput)")
axs[0,0].set_ylabel("Work done since last failure")
axs[1,0].set_ylabel("Work done/Current Time")
axs[2,0].set_ylabel("Work done")
axs[2,0].set_xlabel("Failure #")
progress += 5
bar.update(progress)

axs[0,1].set_title("Lost Work due to failures")
axs[0,1].set_ylabel("Lost work over last 5 time units")
axs[1,1].set_ylabel("Lost work/Current Time")
axs[2,1].set_ylabel("Lost Work")
axs[2,1].set_xlabel("Time")
progress += 5
bar.update(progress)

res = []
for (x, y, z) in itertools.product(["Wd", "Lw"], ["aware", "unaware"], ["instantenous", "OverTime", ""]):
    fileName = "%s-%s-%s-%s%s.csv" % (origFileName, y, failureDistr[:3], z, x)
    #print("Processing file: %s" % (fileName))
    progress += 1
    bar.update(progress)
    with open(fileName, "r") as wdfile:
        for l in wdfile.readlines():
            progress+=3
            bar.update(progress)
            res.append(l)
            progress += 1
            bar.update(progress)

t = []
for r in res:
    t.append([float(x) for x in r.split(',')])
    progress += 1
    bar.update(progress)
#print "Done"


results = []
preemptLabel = "Ckpt ovhd-aware"
wdResults = t[:3]
lwResults = t[6:9]
wdResults.extend(lwResults)
showResults(wdResults, axs, preemptLabel, results, bar)

preemptLabel = "Ckpt ovhd-unaware"
wdResults1 = t[3:6]
lwResults1 = t[9:]
wdResults1.extend(lwResults1)
showResults(wdResults1, axs, preemptLabel, results, bar)

f.suptitle("Failure injection using %s distr." % (failureDistr))
f.legend([results[0], results[6]], ["Ckpt ovhd-aware", "Ckpt ovhd-unaware"], "upper right")
bar.finish()
#plt.savefig("test.jpg", format='jpg', bbox_inches='tight')
plt.show()
