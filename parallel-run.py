#!/usr/bin/python2.7

import subprocess, shlex
import numpy as np
from tqdm import tqdm
from multiprocessing import Pool
import sys

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

aux = open("aux-results.txt", "w")

par = int(sys.argv[1])
par = 2 if par < 2 else par
max_par_runs = par/2

with tqdm(total=RANGE*2) as pbar:
    for i in range(RANGE/(max_par_runs)):
        computeTime = 500
        cmdSort = "./rr-proposed-ckpt-sim.py -w -n 2 --run-time %d --sort" % (computeTime)
        cmdNoSort = "./rr-proposed-ckpt-sim.py -w -n 2 --run-time %d" % (computeTime)
        a = [cmdSort, cmdNoSort]
        arr = []
        for j in range(max_par_runs):
            arr.extend(a)
        pool = Pool(processes=par)
        res = pool.map(f, arr)
        pool.close()
        pool.join()
        for j in range(max_par_runs):
           aux.write("Aware:\n %s" % (res[j*2+0]))
           aux.write("Unaware:\n %s" % (res[j*2+1]))
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
