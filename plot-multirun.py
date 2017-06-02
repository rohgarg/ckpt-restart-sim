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
                           ('aware-lcw', np.float),
                           ('unaware-lcw', np.float),
                           ('aware-lrw', np.float),
                           ('unaware-lrw', np.float),
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
rtx = improvement[:]
print np.mean(improvement)
ax[0].axhline(y=np.mean(improvement), linestyle='--')
ax[0].grid()
ax[0].set_xticks(ticklocs)
ax[0].set_ylabel("Improvement in total run time (%)")

aware = res['aware-ckpt']
unaware = res['unaware-ckpt']
improvement = (unaware - aware) * 100.0 / unaware
rects2 = ax[1].bar(ind, improvement, width)
ckx = improvement[:]
print np.mean(improvement)
ax[1].axhline(y=np.mean(improvement), linestyle='--')
ax[1].grid()
ax[1].set_ylabel("Improvement in total ckpt time (%)")
ax[1].set_xticks(ticklocs)

aware = res['aware-lw']
unaware = res['unaware-lw']
improvement = (unaware - aware) * 100.0 / unaware
rects3 = ax[2].bar(ind, improvement, width)
lwx = improvement[:]
print np.mean(improvement)
ax[2].axhline(y=np.mean(improvement), linestyle='--')
ax[2].grid()
ax[2].set_xticks(ticklocs)
ax[2].set_xticklabels(ticklabels, rotation="90")
ax[2].set_ylabel("Improvement in total lost work (%)")
ax[2].set_xlabel("Run number")

aware = res['aware-lcw']
unaware = res['unaware-lcw']
improvement = (unaware - aware) * 100.0 / unaware
lcwx = improvement[:]
print np.mean(lcwx)

aware = res['aware-lrw']
unaware = res['unaware-lrw']
improvement = (unaware - aware) * 100.0 / unaware
lrwx = improvement[:]
print np.mean(lrwx)

totallw_aware = res['aware-lw'] + res['aware-lcw'] + res['aware-lrw']
totallw_unaware = res['unaware-lw'] + res['unaware-lcw'] + res['unaware-lrw']
improvement = (totallw_unaware - totallw_aware) * 100.0 / totallw_unaware
totallw_imp = improvement[:]
print np.mean(totallw_imp)

# Enable this for debuggin
# for i in range(len(lwx)):
#   if rtx[i] > 0 and lwx[i] < 0:
#     print (i, rtx[i], lcwx[i], lrwx[i], lwx[i], totallw_imp[i])


plt.show()
