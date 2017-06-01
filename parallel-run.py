#!/usr/bin/python2.7

import subprocess, shlex
import numpy as np
from tqdm import tqdm
from multiprocessing import Pool

results = {'computeTime': [],
           'aware-rt': [],
           'unaware-rt': [],
           'aware-ckpt': [],
           'unaware-ckpt': [],
           'aware-lw': [],
           'unaware-lw': []}
RANGE=100

def f(cmd):
    return subprocess.check_output(shlex.split(cmd), stderr=subprocess.STDOUT)

aux = open("aux-results.txt", "w")

with tqdm(total=RANGE*2) as pbar:
    for i in range(RANGE):
        computeTime = 500
        results['computeTime'].append(computeTime)
        cmdSort = "./rr-proposed-ckpt-sim.py -w -n 2 --run-time %d --sort" % (computeTime)
        cmdNoSort = "./rr-proposed-ckpt-sim.py -w -n 2 --run-time %d" % (computeTime)
        arr = [cmdSort, cmdNoSort]
        pool = Pool(processes=2)
        res = pool.map(f, arr)
        pool.close()
        pool.join()
        aux.write("Aware:\n %s" % (res[0]))
        aux.write("Unaware:\n %s" % (res[1]))
        results['aware-rt'].append(int(res[0].split('\n')[-4].split(':')[1]))
        results['unaware-rt'].append(int(res[1].split('\n')[-4].split(':')[1]))
        results['aware-ckpt'].append(int(res[0].split('\n')[-3].split(':')[1]))
        results['unaware-ckpt'].append(int(res[1].split('\n')[-3].split(':')[1]))
        results['aware-lw'].append(int(res[0].split('\n')[-2].split(':')[1]))
        results['unaware-lw'].append(int(res[1].split('\n')[-2].split(':')[1]))
        pbar.update(2)

aux.close()

x = np.column_stack((results['computeTime'],
                    results['aware-rt'],
                    results['unaware-rt'],
                    results['aware-ckpt'],
                    results['unaware-ckpt'],
                    results['aware-lw'],
                    results['unaware-lw']))
head = 'computeTime,'\
       'aware-rt,'\
       'unaware-rt,'\
       'aware-ckpt,'\
       'unaware-ckpt,'\
       'aware-lw,'\
       'unaware-lw'
np.savetxt("results.csv", x.astype(int), delimiter=',', header=head)
