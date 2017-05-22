#!/usr/bin/python

"""Testing Weibull distribution"""

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

# k values are drawn from Tiwari et al., DSN 2014

k = 0.64
y = np.random.weibull(k, size=100000)
v = abs(np.diff(y)) # Difference between two consecutive elements
print("k=%.2f" % (k))
print("max: %.2f" % (max(v)))
print("min: %.2f" % (min(v)))
print("avg: %.2f" % (np.mean(v)))
n, bins, patches = plt.hist(v, histtype='step', fill=False, label=r"$\kappa=%.2f$" %(k))
plt.xlim([min(v), max(v)])
plt.plot(bins)

k = 0.82
y = np.random.weibull(k, size=100000)
v = abs(np.diff(y)) # Difference between two consecutive elements
print("k=%.2f" % (k))
print("max: %.2f" % (max(v)))
print("min: %.2f" % (min(v)))
print("avg: %.2f" % (np.mean(v)))
n, bins, patches = plt.hist(v, histtype='step', fill=False, label=r"$\kappa=%.2f$" %(k))
#plt.xlim([min(v), max(v)])
plt.plot(bins)

k = 0.96
y = np.random.weibull(k, size=100000)
v = abs(np.diff(y)) # Difference between two consecutive elements
print("k=%.2f" % (k))
print("max: %.2f" % (max(v)))
print("min: %.2f" % (min(v)))
print("avg: %.2f" % (np.mean(v)))
n, bins, patches = plt.hist(v, histtype='step', fill=False, label=r"$\kappa=%.2f$" %(k))
#plt.xlim([min(v), max(v)])
plt.plot(bins)

plt.xlabel("Inter-arrival time")
plt.ylabel("Frequency")

plt.legend()

plt.show()
