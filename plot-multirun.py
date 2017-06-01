#!/usr/bin/python2.7

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import numpy as np
import sys

res = np.loadtxt(sys.argv[1],
           delimiter=',',
           skiprows=1,
           dtype=np.dtype([('computeTime', np.float),
                           ('aware-rt', np.float),
                           ('unaware-rt', np.float),
                           ('aware-ckpt', np.float),
                           ('unaware-ckpt', np.float),
                           ('aware-lw', np.float),
                           ('unaware-lw', np.float),
                           ]))
fig, ax = plt.subplots(3,1, sharex=True)
fig.suptitle("Round-robin Ckpt ovhd-aware vs. Ckpt ovhd-unaware (2 jobs, 500 hrs each, ckpt duration: 1 min and 30 mins, MTBF: 4 hrs)")
width=50.0

ind = [x*2*width for x in range(len(res['computeTime']))]
ticklocs = [x - (width/4) for x in ind]
ticklabels = [str(x) for x in range(len(res['computeTime']))]

aware = res['aware-rt']
unaware = res['unaware-rt']
improvement = (unaware - aware) * 100.0 / unaware
rects1 = ax[0].bar(ind, improvement, width)
ax[0].axhline(y=np.mean(improvement), linestyle='--')
ax[0].grid()
ax[0].set_xticks(ticklocs)
ax[0].set_ylabel("Improvement in total run time (%)")

aware = res['aware-ckpt']
unaware = res['unaware-ckpt']
improvement = (unaware - aware) * 100.0 / unaware
rects2 = ax[1].bar(ind, improvement, width)
ax[1].grid()
ax[1].set_ylabel("Improvement in total ckpt time (%)")
ax[1].set_xticks(ticklocs)

aware = res['aware-lw']
unaware = res['unaware-lw']
improvement = (unaware - aware) * 100.0 / unaware
rects3 = ax[2].bar(ind, improvement, width)
ax[2].axhline(y=np.mean(improvement), linestyle='--')
ax[2].grid()
ax[2].set_xticks(ticklocs)
ax[2].set_xticklabels(ticklabels, rotation="90")
ax[2].set_ylabel("Improvement in total lost work (%)")
ax[2].set_xlabel("Run number")

plt.show()
