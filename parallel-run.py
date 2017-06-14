#!/usr/bin/python2.7

import subprocess, shlex
import numpy as np
from tqdm import tqdm
from multiprocessing import Pool
import sys
import re

results = {'computeTime': [],
           'aware-rt': [],
           'unaware-rt': [],
           'aware-ckpt': [],
           'unaware-ckpt': [],
           'aware-lcw': [],
           'unaware-lcw': [],
           'aware-lrw': [],
           'unaware-lrw': [],
           'aware-lw': [],
           'unaware-lw': []}
RANGE=512

def f(cmd):
    return subprocess.check_output(shlex.split(cmd), stderr=subprocess.STDOUT)

aux = open("aux-results.csv", "w")
aux.write("Run, Policy, Process #, # Ckpts, # Total Failures, # Restarts, # Failed Restarts, # Failed Ckpts, # Preempts, Compute Time, Ckpt Time, Lost Work, Lost Restart Time, Lost Ckpt Time, Submission Time, Start Time, End Time, Actual Run Time\n")

par = int(sys.argv[1])
par = 2 if par < 2 else par
max_par_runs = par/2
run_num = 1
p = re.compile('^Process\s[0-9]+,')
filter_fn = lambda x: filter(lambda l: p.match(l), x.split('\n'))

def prefix_details_fn(run, policy, lst):
    return map(lambda s: '%d, %s, %s\n' % (run, policy, s), lst)

with tqdm(total=RANGE*2) as pbar:
    for i in range(RANGE/(max_par_runs)):
        computeTime = 500
        cmdSort = "./rr-proposed-ckpt-sim.py -w -n 2 --run-time %d --sort --mtbf 4 --oci-scale-factor 2" % (computeTime)
        cmdNoSort = "./rr-proposed-ckpt-sim.py -w -n 2 --run-time %d --mtbf 4" % (computeTime)
        a = [cmdSort, cmdNoSort]
        arr = []
        for j in range(max_par_runs):
            arr.extend(a)
        pool = Pool(processes=par)
        res = pool.map(f, arr)
        pool.close()
        pool.join()
        for j in range(max_par_runs):
           aux.writelines(prefix_details_fn(run_num, "aware"  , filter_fn(res[j*2+0])))
           aux.writelines(prefix_details_fn(run_num, "unaware", filter_fn(res[j*2+1])))
           results['computeTime'].append(computeTime)
           results['aware-rt'].append(int(res[j*2+0].split('\n')[-4].split(':')[1]))
           results['unaware-rt'].append(int(res[j*2+1].split('\n')[-4].split(':')[1]))
           results['aware-ckpt'].append(int(res[j*2+0].split('\n')[-3].split(':')[1]))
           results['unaware-ckpt'].append(int(res[j*2+1].split('\n')[-3].split(':')[1]))
           results['aware-lw'].append(int(res[j*2+0].split('\n')[-2].split(':')[1]))
           results['unaware-lw'].append(int(res[j*2+1].split('\n')[-2].split(':')[1]))
           results['aware-lcw'].append(int(res[j*2+0].split('\n')[-6].split(':')[1]))
           results['unaware-lcw'].append(int(res[j*2+1].split('\n')[-6].split(':')[1]))
           results['aware-lrw'].append(int(res[j*2+0].split('\n')[-5].split(':')[1]))
           results['unaware-lrw'].append(int(res[j*2+1].split('\n')[-5].split(':')[1]))
           run_num += 1
        pbar.update(par)

aux.close()

x = np.column_stack((results['computeTime'],
                    results['aware-rt'],
                    results['unaware-rt'],
                    results['aware-ckpt'],
                    results['unaware-ckpt'],
                    results['aware-lcw'],
                    results['unaware-lcw'],
                    results['aware-lrw'],
                    results['unaware-lrw'],
                    results['aware-lw'],
                    results['unaware-lw']))
head = 'computeTime,'\
       'aware-rt,'\
       'unaware-rt,'\
       'aware-ckpt,'\
       'unaware-ckpt,'\
       'aware-lcw,'\
       'unaware-lcw,'\
       'aware-lrw,'\
       'unaware-lrw,'\
       'aware-lw,'\
       'unaware-lw'
np.savetxt("results.csv", x.astype(int), delimiter=',', header=head)
