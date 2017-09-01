#!/usr/bin/python

#import matplotlib
#matplotlib.use("TkAgg")
#import matplotlib.pyplot as plt
import numpy as np
import sys


#Run, Policy, Process #, Delta, Total Time, Useful Time, Ckpt Time, Lost Time

mydata = np.dtype([('run', np.int), ('policy', np.str, 12), ('process', np.str, 14),
                   ('delta', np.int), ('totalTime', np.float), ('useful', np.float),
                   ('ckptTime', np.float), ('lostTime', np.float), ('jobFails', np.int), ('totalFails', np.int)])
for oci in range(int(sys.argv[1])):
   #oci_factor = 1.0 + oci * 0.1
   oci_factor = float(sys.argv[2])
   aux_filename = "aux-results-mtbf-10-oci-%.1f-ckpts-%d.csv" % (oci_factor, oci+1)
   res = np.loadtxt(aux_filename, delimiter=',', skiprows=1, dtype=mydata)
   
   p0 = np.extract(res['process'] == " Process 0", res)
   p1 = np.extract(res['process'] == " Process 1", res)

   print("------------------Switching Results: Switch Point  %d ---------------------" % (oci+1))
   print("Light Weight App: Total Time:  %.2f  Useful:  %.2f  Checkpoint:  %.2f  Lost:  %.2f  Failures: %.2f" %
         (np.mean(p1['totalTime']), np.mean(p1['useful']), np.mean(p1['ckptTime']), np.mean(p1['lostTime']), np.mean(p1['jobFails'])))
   print("Heavy Weight App: Total Time:  %.2f  Useful:  %.2f  Checkpoint:  %.2f  Lost:  %.2f  Failures: %.2f" %
         (np.mean(p0['totalTime']), np.mean(p0['useful']), np.mean(p0['ckptTime']), np.mean(p0['lostTime']), np.mean(p0['jobFails'])))
   print("Total combined: Total Time:  %.2f  Useful:  %.2f  Checkpoint:  %.2f  Lost:  %.2f  Failures: %.2f" %
         (np.mean(p1['totalTime']) + np.mean(p0['totalTime']), np.mean(p0['useful']) + np.mean(p1['useful']),
          np.mean(p0['ckptTime']) + np.mean(p1['ckptTime']), np.mean(p1['lostTime']) + np.mean(p0['lostTime']), np.mean(p1['totalFails'])))
   print("")
   
   #plt.show()
