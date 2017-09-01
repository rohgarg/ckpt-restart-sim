#!/bin/bash
for i in `seq 1 15`;
do
  echo "Switch point: " $i
  ./rr_proposed_ckpt_aware_sim_mod.py -w -n 2 --run-time 1000 --mtbf 10 --sorted --ckpts-before-yield1 0 --ckpts-before-yield2 $i --oci-scale-factor 1.0
  echo "-----------------------------------------------------------------------------------------------"
done
