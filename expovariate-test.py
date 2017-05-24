#!/usr/bin/python

"""Testing Weibull distribution"""

import numpy as np
import random
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

# Exponential
MEAN=10.0
LAMBDA=1.0/MEAN
y = [random.expovariate(LAMBDA) for x in range(100000)]
v = abs(np.diff(y)) # Difference between two consecutive elements
print("max: %.2f" % (max(v)))
print("min: %.2f" % (min(v)))
print("avg: %.2f" % (np.mean(v)))
n, bins, patches = plt.hist(v, histtype='step', fill=False, label=r"Expo. Distr. $(\mu=%.2f)$" %(MEAN))
plt.xlim([min(v), max(v)])
plt.plot(bins)

MEAN=1.0/0.9
LAMBDA=0.9
y = [random.expovariate(LAMBDA) for x in range(100000)]
v = abs(np.diff(y)) # Difference between two consecutive elements
print("max: %.2f" % (max(v)))
print("min: %.2f" % (min(v)))
print("avg: %.2f" % (np.mean(v)))
n, bins, patches = plt.hist(v, histtype='step', fill=False, label=r"Expo. Distr. $(\mu=%.2f)$" %(MEAN))
#plt.xlim([min(v), max(v)])
plt.plot(bins)

# Weibull
k = 0.64
y = np.random.weibull(k, size=100000)
v = abs(np.diff(y)) # Difference between two consecutive elements
print("k=%.2f" % (k))
print("max: %.2f" % (max(v)))
print("min: %.2f" % (min(v)))
print("avg: %.2f" % (np.mean(v)))
n, bins, patches = plt.hist(v, histtype='step', fill=False, label=r"Weibull Distr. $(\kappa=%.2f)$" %(k))
#plt.xlim([min(v), max(v)])
plt.plot(bins)

k = 0.96
y = np.random.weibull(k, size=100000)
v = abs(np.diff(y)) # Difference between two consecutive elements
print("k=%.2f" % (k))
print("max: %.2f" % (max(v)))
print("min: %.2f" % (min(v)))
print("avg: %.2f" % (np.mean(v)))
n, bins, patches = plt.hist(v, histtype='step', fill=False, label=r"Weibull Distr. $(\kappa=%.2f)$" %(k))
#plt.xlim([min(v), max(v)])
plt.plot(bins)

plt.xlabel("Inter-arrival time")
plt.ylabel("Frequency")

plt.legend()

plt.show()
