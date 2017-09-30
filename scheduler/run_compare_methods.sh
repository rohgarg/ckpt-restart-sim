python compare_methods.py -d ../../dmtcp -l "mpirun -np 1 ./bin/CoMD-mpi1 -e -i 1 -j 1 -k 1 -x 20 -y 20 -z 20" -g "mpirun -np 1 ./bin/CoMD-mpi2 -e -i 1 -j 1 -k 1 -x 75 -y 75 -z 75" -t 100 -m 2 -c 5 -i 0.1563 -n 0.4944 -w 0.6 -s 20 -o " --no-gzip"

