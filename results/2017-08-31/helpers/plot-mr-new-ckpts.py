#!/shared/apps/python/Python-3.5.2/Python-3.5.2/INSTALL/bin/python3

import numpy as np
import sys


def extract_jobdata(oci_factor, oci):
   mydata = np.dtype([('run', np.int), ('policy', np.str, 12), ('process', np.str, 14),
                      ('ckpts', np.int), ('failures', np.int), ('restarts', np.int),
                      ('failedRs', np.int), ('failedCs', np.int), ('preempts', np.int),
                      ('computeT', np.int), ('ckptT', np.int), ('lostW', np.int),
                      ('lostRW', np.int), ('lostCW', np.int), ('submitT', np.int),
                      ('startT', np.int), ('endT', np.int), ('runT', np.int)])
   aux_filename = "aux-results-oci-%.1f-ckpts-%d.csv" % (oci_factor, oci)
   res = np.loadtxt(aux_filename, delimiter=',', skiprows=1, dtype=mydata)
   
   aware_runs = np.extract(res['policy'] == "b' aware'", res)
   unaware_runs = np.extract(res['policy'] == "b' unaware'", res)
   
   aware_p0 = np.extract(aware_runs['process'] == "b' Process 0'", aware_runs)
   aware_p1 = np.extract(aware_runs['process'] == "b' Process 1'", aware_runs)
   
   unaware_p0 = np.extract(unaware_runs['process'] == "b' Process 0'", unaware_runs)
   unaware_p1 = np.extract(unaware_runs['process'] == "b' Process 1'", unaware_runs)
   
   def get_diffs(a, b, ct):
     return 100.0*(b[ct] - a[ct]) / b[ct]
   
   diff_p0 = get_diffs(aware_p0, unaware_p0, 'runT')
   diff_p1 = get_diffs(aware_p1, unaware_p1, 'runT')
   
   #msg = "%d, %.1f, %.1f" % (oci, np.mean(diff_p0), np.mean(diff_p1))
   msg = "%.1f, %.1f" % (np.mean(diff_p0), np.mean(diff_p1))
   return msg

def extract_aggdata(oci_factor, oci):

   aux_filename = "results-oci-%.1f-ckpts-%d.csv" % (oci_factor, oci+1)
   res = np.loadtxt(aux_filename,
              delimiter=',',
              skiprows=1,
              dtype=np.dtype([('computeTime', np.float),
                              ('aware-rt', np.float),
                              ('unaware-rt', np.float),
                              ('aware-ckpt', np.float),
                              ('unaware-ckpt', np.float),
                              ('aware-lcw', np.float),
                              ('unaware-lcw', np.float),
                              ('aware-lrw', np.float),
                              ('unaware-lrw', np.float),
                              ('aware-lw', np.float),
                              ('unaware-lw', np.float),
                              ]))
   main_result = "%.1f, %d, " % (oci_factor, oci+1)
   
   aware = res['aware-rt']
   unaware = res['unaware-rt']
   improvement = (unaware - aware) * 100.0 / unaware
   rtx = improvement[:]
   main_result += str(np.mean(improvement))
   #main_result += ", " + str(np.std(improvement))
   
   aware = res['aware-ckpt']
   unaware = res['unaware-ckpt']
   improvement = (unaware - aware) * 100.0 / unaware
   ckx = improvement[:]
   main_result += ", " + str(np.mean(improvement))
   #main_result += ", " + str(np.std(improvement))
   
   aware = res['aware-lw']
   unaware = res['unaware-lw']
   improvement = (unaware - aware) * 100.0 / unaware
   lwx = improvement[:]
   main_result += ", " + str(np.mean(improvement))
   #main_result += ", " + str(np.std(improvement))
   
   aware = res['aware-lcw']
   unaware = res['unaware-lcw']
   improvement = (unaware - aware) * 100.0 / unaware
   lcwx = improvement[:]
   main_result += ", " + str(np.mean(improvement))
   #main_result += ", " + str(np.std(improvement))
   
   aware = res['aware-lrw']
   unaware = res['unaware-lrw']
   improvement = (unaware - aware) * 100.0 / unaware
   lrwx = improvement[:]
   main_result += ", " + str(np.mean(improvement))
   #main_result += ", " + str(np.std(improvement))
   
   totallw_aware = res['aware-lw'] + res['aware-lcw'] + res['aware-lrw']
   totallw_unaware = res['unaware-lw'] + res['unaware-lcw'] + res['unaware-lrw']
   improvement = (totallw_unaware - totallw_aware) * 100.0 / totallw_unaware
   totallw_imp = improvement[:]
   main_result += ", " + str(np.mean(improvement))
   #main_result += ", " + str(np.std(improvement))

   main_result += ", " + extract_jobdata(oci_factor, oci + 1)
   print(main_result)

def main(argc, argv):
    for oci in range(int(argv[1])):
       oci_factor = float(argv[2])
       extract_aggdata(oci_factor, oci)


if __name__ == "__main__":
    main(len(sys.argv), sys.argv)
