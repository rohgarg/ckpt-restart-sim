#!/bin/bash
COUNTER=0
while [  $COUNTER -lt $1 ]; do
   c=$COUNTER
   let c1=COUNTER+1
   ./parallel-run-ckpt-aware.py $3 $c $c1 $2
   let COUNTER=COUNTER+1
done
