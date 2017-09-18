#!/usr/bin/python

# Import libraries #

import sys, argparse
import shlex, glob
import os, subprocess, threading, shutil
import time, math, random
from scipy.special import gamma

# Global functions #

def HOURS_TO_SECS(x):
	return x*3600

def SECS_TO_HOURS(x):
	return x/3600

'''
VARIABLE FORMAT
Contstants          :- All captial letters
Global Variables    :- Start with "gv"
Local Variables     :- Small letters except first letter of a word 
                       starting with the second word 
'''

# Global constants #

DESCRIPTION = "The program runs an application with DMTCP checkpointing and simulated failures.\n"

SCALE_FACTOR = 1800                                     # The factor which the times should be scaled down by
                                                        # Current value scales 100 hours to 200 seconds

TOTAL_TIME = HOURS_TO_SECS(100/SCALE_FACTOR)            # Total time that the program should run for

MTBF = HOURS_TO_SECS(10/SCALE_FACTOR)                   # Mean time between failures for the entire system
WEIBULL_SHAPE = 0.6                                     # Shape parameter for failure calculation
WEIBULL_SCALE = MTBF/gamma(1+(1/WEIBULL_SHAPE))         # Scale parameter for failure calculation

CKPT_INTERVAL = int(HOURS_TO_SECS(5/SCALE_FACTOR))      # Checkpointing interval (or compute time per interval)

APP_NAME = '../dmtcp/test/dmtcp1'                       # Name of the app

# Parameter for checkpoint and DMTCP paths and dirs
APP_CKPT_DIR = 'app'

GLOBAL_CKPT_DIR = "./ckpt-dir"
DMTCP_PATH = "../../dmtcp"
DMTCP_BIN = DMTCP_PATH + "/bin"
DMTCP_LAUNCH = DMTCP_BIN + "/dmtcp_launch"
DMTCP_RESTART = DMTCP_BIN + "/dmtcp_restart"
DMTCP_COMMAND = DMTCP_BIN + "/dmtcp_command"

# Global Variables #

gvTotalCO = 0                    # Total checkpointing overhead of the app 
gvTotalUW = 0                    # Total useful work done by the app 
gvTotalLW = 0                    # Total lost work of the app 
gvTotalRT = 0                    # Total run time of the app
gvTotalCP = 0                    # Total number of checkpoints during the app

gvTotalFL = 0                    # Total number of system failures

gvDone = False                   # Signals the end of the run

gvStartTime = time.time()        # The start time of the most recent run (after a failure)

gvStatsLock = threading.Lock()   # The lock is used when the runtime statistics are being calculated

# Functions #

# DESCRIPTION:
# > This function prints all the relevant values
# INPUTS:
# > None
# OUTPUTS:
# > None
def printStats():

	global gvTotalFL
	global gvTotalCO, gvTotalUW, gvTotalLW, gvTotalRT, gvTotalCP

	# Scale back the values in seconds to hours
	TotalCO = SECS_TO_HOURS(gvTotalCO)*SCALE_FACTOR
	TotalUW = SECS_TO_HOURS(gvTotalUW)*SCALE_FACTOR
	TotalLW = SECS_TO_HOURS(gvTotalLW)*SCALE_FACTOR
	TotalRT = SECS_TO_HOURS(gvTotalRT)*SCALE_FACTOR

	string  = "\n"
	string += "Process Name         = " + APP_NAME + "\n"
	string += "Checkpoint Time      = " + str("%.2f" % TotalCO) + "h\n"
	string += "Useful Work          = " + str("%.2f" % TotalUW) + "h\n"
	string += "Lost Work            = " + str("%.2f" % TotalLW) + "h\n"
	string += "Run Time             = " + str("%.2f" % TotalRT) + "h\n"
	string += "Num Checkpoints      = " + str(gvTotalCP) + "\n"
	string += "Num Failures         = " + str(gvTotalFL) + "\n"

	print(string)

# DESCRIPTION:
# > This function calculates the relevant data
# > It is called every time a failure or a switch takes place
# INPUTS:
# > timeDiff: the amount of time elapsed between last failure/switch and the current failure/switch
# OUTPUTS:
# > None
def calculateStats(timeDiff):

	global gvTotalCO, gvTotalUW, gvTotalLW, gvTotalRT, gvTotalCP

	locCP = 0   # Number of checkpoints during this interval
	locCO = 0   # Checkpoint overhead during this interval

	# Read the checkpoint timings log
	if os.path.exists('jtimings.csv'):
		with open('jtimings.csv') as f:
    			content = f.readlines()
		content = [x.strip() for x in content]

		# For each checkpoint, add the checkpoint time to the overhead
		# And add 1 to the number of checkpoints
		for line in content:
			if "checkpoint" in line:
				splits = line.split(',')
				locCO += float(splits[3])
				locCP += 1
	
		# Remove the checkpoint timings log
		subprocess.call('rm jtimings.csv', shell=True)

	# Useful Work is [checkpoint interval * number of checkpoints]
	# Lost Work is [runtime - (checkpoint overhead + useful work)]
	gvTotalCO += locCO
	gvTotalUW += float(CKPT_INTERVAL)*locCP
	gvTotalLW += timeDiff-(locCO+(CKPT_INTERVAL*locCP))
	gvTotalRT += timeDiff
	gvTotalCP += locCP

# DESCRIPTION:
# > This function starts/restarts DMTCP with the desired app
# INPUTS:
# > None
# OUTPUTS:
# > proc: the ID of the launched DMTCP process (needed to know when the process dies)
def runApplication():

	global gvStartTime

	# List of app's checkpoint files
	ckptFiles = glob.glob(APP_CKPT_DIR + '/' + 'ckpt_*.dmtcp')
	
	# Launch the application
	string = ''

	# If there are no checkpoint files, then start afresh
	if (len(ckptFiles) == 0):
		string = DMTCP_LAUNCH + " "
		# Set the ckeckpointing interval
		string += '-i ' + str(CKPT_INTERVAL) + ' '
		string += '--ckptdir ' + APP_CKPT_DIR + ' '
		string += APP_NAME
	else:
		ckptFile = ckptFiles[0]
		# If there are multiple checkpoint files, get the newest one
		if (len(ckptFiles) != 1):
			ckptTimes = []
			for fle in ckptFiles:
				ckptTimes.append(os.path.getmtime(fle))
			ckptTimes.sort(reverse=True)
			for fle in ckptFiles:
				if (os.path.getmtime(fle) == ckptTimes[0]):
					ckptFile = fle
					break

		string = DMTCP_RESTART + " "
		# Set the ckeckpointing interval
		string += '-i ' + str(CKPT_INTERVAL) + ' '
		string += '--ckptdir ' + APP_CKPT_DIR + ' '
		string += ckptFile

	# Set the new start time of the run
	gvStartTime = time.time()

	# Start the run
	proc = subprocess.Popen(shlex.split(string), stdout=subprocess.PIPE)

	return proc

# DESCRIPTION:
# > This function waits until there is a failure or until the LW app switches, to calculate data
# INPUTS:
# > proc: the ID of the launched DMTCP process (needed to know when the process dies)
# OUTPUTS:
# > None
def waitTillFailure(proc):

	global gvStartTime, gvDone, gvStatsLock, gvTotalFL

	# Calculate when the next failure should take place
	nextFailure = int(random.weibullvariate(WEIBULL_SCALE, WEIBULL_SHAPE))

	time.sleep(nextFailure)

	# Caluclate the time which the app ran for during this instance
	timeDiff = time.time() - gvStartTime

	proc.send_signal(9);

	# Acquire the lock on calculate stats
	gvStatsLock.acquire()

	# No need to calculate if the entire run has already ended
	if (gvDone is False):
		calculateStats(timeDiff)
		gvTotalFL += 1

	# Release the lock on calculate stats
	gvStatsLock.release()

# DESCRIPTION:
# > This function (thread) keeps running the application and injects failures
# > It keeps doing this until the runtime has ended
# INPUTS:
# > None
# OUTPUTS:
# > None
def scheduleApps():

	global gvDone

	while(gvDone is False):
		proc = runApplication()
		if (gvDone):
			break
		waitTillFailure(proc)

# DESCRIPTION:
# > This function (thread) sleeps until its time to end the run
# > After that it calculates the statistics and exits
# INPUTS:
# > None
# OUTPUTS:
# > None
def waitTillEOE():
	
	global gvStartTime, gvDone, gvStatsLock

	# Sleep for the duration of the run
	time.sleep(TOTAL_TIME)	
	
	# Set the gvDone signal to alert the scheduleApps() function to quit
	gvDone = True
	
	# Acquire the lock on calculate stats
	gvStatsLock.acquire()

	timeDiff = time.time() - gvStartTime
	subprocess.call(DMTCP_COMMAND + ' --kill', shell=True)
	calculateStats(timeDiff)

	# Release the lock on calculate stats
	gvStatsLock.release()

# DESCRIPTION:
# > This function verifies that the path specified for the
# > DMTCP root directory is a valid path, and that the binaries
# > are present.
# INPUTS:
# > None
# OUTPUTS:
# > None
def verifyDmtcpPaths():

	if not (os.path.isdir(DMTCP_PATH) and os.path.isdir(DMTCP_BIN) and \
		os.path.isfile(DMTCP_LAUNCH) and os.path.isfile(DMTCP_RESTART) and \
		os.path.isfile(DMTCP_COMMAND)):
			print("Please specify a valid path to the DMTCP root directory.\n" \
			"Also, make sure to run configure and build within the DMTCP directory.\n")
			exit(-1)


# DESCRIPTION:
# > This function verifies removes any old ckeckpoint dir
# > and creates a new one.
# INPUTS:
# > None
# OUTPUTS:
# > None
def prepareCkptDirs():
  
	try:
		if os.path.exists(GLOBAL_CKPT_DIR):
			shutil.rmtree(GLOBAL_CKPT_DIR, ignore_errors=True)
		os.makedirs(GLOBAL_CKPT_DIR)
		APP_CKPT_DIR = GLOBAL_CKPT_DIR + "/" + os.path.basename(APP_NAME)
		os.makedirs(APP_CKPT_DIR)
	except OSError as e:
		if e.errno != errno.EEXIST:
			raise

# DESCRIPTION:
# > Main function parses arguments and starts the threads
# INPUTS:
# > None
# OUTPUTS:
# > None
def main():

	global TOTAL_TIME
	global MTBF, WEIBULL_SHAPE, WEIBULL_SCALE
	global CKPT_INTERVAL, APP_NAME
	global DMTCP_PATH, DMTCP_BIN, DMTCP_LAUNCH, DMTCP_RESTART, DMTCP_COMMAND
	global SCALE_FACTOR

	# Parse the arguments and set the global constants
	parser = argparse.ArgumentParser(prog="isolated_run", description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter)

	parser.add_argument("-d", "--dmtcp-path", type=str, help="The path to the DMTCP root directory. Default = ../../dmtcp")
	parser.add_argument("-n", "--app-name", type=str, help="The name of the low weight application.")
	parser.add_argument("-t", "--run-time", type=float, help="The total run time of the program in hours. Default = 100 hours.")
	parser.add_argument("-m", "--mtbf", type=float, help="The MTBF of the system. Default = 10 hours.")
	parser.add_argument("-i", "--ckpt-int", type=float, help="The checkpointing interval of the low weight application. Default = 1 hour.")
	parser.add_argument("-w", "--weibull-shape", type=float, help="The shape parameter of the Weibull failure curve. Default = 0.6.")
	parser.add_argument("-s", "--scale-factor", type=float, help="The parameter to scale hous to seconds. Default = 1800.")	

	args = parser.parse_args()

	if args.app_name:
		APP_NAME = args.app_name
	if args.run_time:
		TOTAL_TIME = HOURS_TO_SECS(args.run_time/SCALE_FACTOR)
	if args.mtbf:
		MTBF = HOURS_TO_SECS(args.mtbf/SCALE_FACTOR)
	if args.ckpt_int:
		CKPT_INTERVAL = int(HOURS_TO_SECS(args.ckpt_int/SCALE_FACTOR))
	if args.weibull_shape:
		WEIBULL_SHAPE = args.weibull_shape
		WEIBULL_SCALE = MTBF/gamma(1+(1/WEIBULL_SHAPE))
	if args.dmtcp_path:
		DMTCP_PATH = args.dmtcp_path
                DMTCP_BIN = DMTCP_PATH + "/bin"
                DMTCP_LAUNCH = DMTCP_BIN + "/dmtcp_launch"
                DMTCP_RESTART = DMTCP_BIN + "/dmtcp_restart"
                DMTCP_COMMAND = DMTCP_BIN + "/dmtcp_command"
                verifyDmtcpPaths()
	if args.scale_factor:
		SCALE_FACTOR = args.scale_factor

	# Remove any existing checkpoint data files
	prepareCkptDirs()
	
	# Kill any exisiting dmtcp processes
	subprocess.call(DMTCP_COMMAND + ' --kill', shell=True)

	# Start the SAThread which runs the scheduleApps() function
	SAThread = threading.Thread(target=scheduleApps, args=())
	SAThread.setDaemon(True)
	SAThread.start()

	# Start the EOEThread which runs the waitTillEOE() function
	EOEThread = threading.Thread(target=waitTillEOE, args=())
	EOEThread.start()
	EOEThread.join()

	# Print the final statistics
	printStats()

	# Remove any generated checkpoint restart files
	if (len(glob.glob('dmtcp_restart_script*.sh')) != 0):
		subprocess.call('rm dmtcp_restart_script*.sh', shell=True)

	exit()

# Program beginning #
if __name__ == "__main__":
	main()
