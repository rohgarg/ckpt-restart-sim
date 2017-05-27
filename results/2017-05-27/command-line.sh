#!/bin/bash

# Weibull
./rr-proposed-ckpt-sim.py -w -n 5 -f run4 &
./rr-proposed-ckpt-sim.py -w -n 5 --sort -f run4 &

# Exponential
./rr-proposed-ckpt-sim.py -n 5 -f run4 &
./rr-proposed-ckpt-sim.py -n 5 --sort -f  run4
