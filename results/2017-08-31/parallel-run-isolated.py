#!/usr/bin/python

import subprocess, shlex
import numpy as np
from tqdm import tqdm
from multiprocessing import Pool
import sys
import re
#import rr_proposed_ckpt_sim_mod as sim
import rr_proposed_isolated_sim_mod as sim

RANGE=512

def f(cmd):
    return sim.main(len(sys.argv), sys.argv, shlex.split(cmd))

par = int(sys.argv[1])
par = 2 if par < 2 else par
max_par_runs = int(par/2)
p = re.compile('^Process\s[0-9]+,')
filter_fn = lambda x: filter(lambda l: p.match(l), x.split('\n'))

def prefix_details_fn(run, policy, lst):
    return map(lambda s: '%d, %s, %s\n' % (run, policy, s), lst)

pool = Pool(processes=par)
for oci in range(int(sys.argv[2]), int(sys.argv[3])):
   run_num = 1
   #lightAppCkpts = int(sys.argv[3])
   lightAppCkpts = 0
   #oci_factor = 1.0 + oci * 0.1
   oci_factor = float(sys.argv[4])
   aux_filename = "aux-results-mtbf-10-oci-%.1f-ckpts-%d.csv" % (oci_factor, lightAppCkpts)
   #results_filename = "results-oci-%.1f-ckpts-%d.csv" % (oci_factor, lightAppCkpts)
   aux = open(aux_filename, "w")
   aux.write("Run, Policy, Process #, Delta, Total Time, Useful Time, Ckpt Time, Lost Time, Job Failures, Total Failures\n")
   with tqdm(total=RANGE*1) as pbar:
       for i in range(int(RANGE/(max_par_runs))):
           computeTime = 1000
           cmdSort = "-w -n 2 --run-time %d --mtbf 10 --ckpts-before-yield1 0 --ckpts-before-yield2 0 --oci-scale-factor %.1f" % (computeTime, oci_factor)
           #cmdNoSort = "-w -n 2 --run-time %d --mtbf 10 --ckpts-before-yield1 0 --ckpts-before-yield2 0" % (computeTime)
           #a = [cmdSort, cmdNoSort]
           a = [cmdSort]
           arr = []
           for j in range(max_par_runs):
               arr.extend(a)
           res = pool.map(f, arr)
           for j in range(max_par_runs):
              #print res
              aux.writelines(prefix_details_fn(run_num, "isolated", filter_fn(res[0])))
              run_num += 1
              aux.writelines(prefix_details_fn(run_num, "isolated", filter_fn(res[1])))
              run_num += 1
           pbar.update(max_par_runs)
   
   aux.close()
   
pool.close()
pool.join()
