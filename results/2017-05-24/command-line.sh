#!/bin/bash

./fifo-proposed-sim.py -n 10 -f run1 &
./fifo-proposed-sim.py -x -n 10 -f run1 &
./fifo-proposed-sim.py -w -n 10 -f run1 &
./fifo-proposed-sim.py -w -x -n 10 -f run1
