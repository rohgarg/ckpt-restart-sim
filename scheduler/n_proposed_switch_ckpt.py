#!/usr/bin/python

# Import libraries #

import sys, argparse
import shlex, glob
import os, subprocess, threading, shutil
import time, math, random
import errno
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

DESCRIPTION = "The program runs two application using the switch checkpointing method.\n"

SCALE_FACTOR = 1800                                     # The factor which the times should be scaled down by
                                                        # Current value scales 100 hours to 200 seconds

TOTAL_TIME = HOURS_TO_SECS(100/SCALE_FACTOR)            # Total time that the program should run for

MTBF = HOURS_TO_SECS(10/SCALE_FACTOR)                   # Mean time between failures for the entire system
WEIBULL_SHAPE = 0.6                                     # Shape parameter for failure calculation
WEIBULL_SCALE = MTBF/gamma(1+(1/WEIBULL_SHAPE))         # Scale parameter for failure calculation

CKPT_INTERVAL = None                                    # Checkpoint interval of each pp
SWITCH_POINT = 2                                        # Number of checkpoints after which app 1 should switch

NUM_APPS = 2                                            # Number of applications to run
APP_NAME = None                                         # Name of each app

GLOBAL_CKPT_DIR = "./ckpt-dir"                          # Main checkpointing directory
APP_CKPT_DIR = None                                     # Individual checkpointing directories

DMTCP_PATH = "../../dmtcp"                              # Path to DMTCP
DMTCP_BIN = DMTCP_PATH + "/bin"
DMTCP_LAUNCH = DMTCP_BIN + "/dmtcp_launch"
DMTCP_RESTART = DMTCP_BIN + "/dmtcp_restart"
DMTCP_COMMAND = DMTCP_BIN + "/dmtcp_command"

# Global Variables #

gvTotalCO = None                 # Total checkpointing overhead of individual apps
gvTotalUW = None                 # Total useful work done by individual apps
gvTotalLW = None                 # Total lost work of individual apps
gvTotalRT = None                 # Total run time of individual apps
gvTotalCP = None                 # Total number of checkpoints during individual apps
gvTotalFL = None                 # Total number of failures for individual apps

gvCurrentApp = 0                 # The ID of the currently running app

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

	global gvTotalCO, gvTotalUW, gvTotalLW, gvTotalRT, gvTotalCP, gvTotalFL

	# Scale back the values in seconds to hours
	TotalCO = [(SECS_TO_HOURS(i)*SCALE_FACTOR) for i in gvTotalCO]
	TotalUW = [(SECS_TO_HOURS(i)*SCALE_FACTOR) for i in gvTotalUW]
	TotalLW = [(SECS_TO_HOURS(i)*SCALE_FACTOR) for i in gvTotalLW]
	TotalRT = [(SECS_TO_HOURS(i)*SCALE_FACTOR) for i in gvTotalRT]

	string = ""
	for i in range(0, NUM_APPS):
		string += "\n"
		string += "Process Name         = " + APP_NAME[i] + "\n"
		string += "Checkpoint Time      = " + str("%.2f" % TotalCO[i]) + "h\n"
		string += "Useful Work          = " + str("%.2f" % TotalUW[i]) + "h\n"
		string += "Lost Work            = " + str("%.2f" % TotalLW[i]) + "h\n"
		string += "Run Time             = " + str("%.2f" % TotalRT[i]) + "h\n"
		string += "Num Checkpoints      = " + str(gvTotalCP[i]) + "\n"
		string += "Num Failures         = " + str(gvTotalFL[i]) + "\n"

	string += "\n"
	string += "Total runtime statistics:\n"
	string += "Checkpoint Time      = " + str("%.2f" % sum(TotalCO)) + "h\n"
	string += "Useful Work          = " + str("%.2f" % sum(TotalUW)) + "h\n"
	string += "Lost Work            = " + str("%.2f" % sum(TotalLW)) + "h\n"
	string += "Run Time             = " + str("%.2f" % sum(TotalRT)) + "h\n"
	string += "Num Failures         = " + str(sum(gvTotalFL)) + "\n"

	print(string)

# DESCRIPTION:
# > This function calculates the relevant data
# > It is called every time a failure or a switch takes place
# INPUTS:
# > timeDiff: the amount of time elapsed between last failure/switch and the current failure/switch
# OUTPUTS:
# > None
def calculateStats(timeDiff):

	global gvCurrentApp
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
	gvTotalCO[gvCurrentApp] += locCO
	gvTotalUW[gvCurrentApp] += float(CKPT_INTERVAL[gvCurrentApp])*locCP
	gvTotalLW[gvCurrentApp] += timeDiff-(locCO+(CKPT_INTERVAL[gvCurrentApp]*locCP))
	gvTotalRT[gvCurrentApp] += timeDiff
	gvTotalCP[gvCurrentApp] += locCP

# DESCRIPTION:
# > This function starts/restarts DMTCP with the desired app
# INPUTS:
# > None
# OUTPUTS:
# > proc: the ID of the launched DMTCP process (needed to know when the process dies)
def runApplication():

	global gvCurrentApp, gvStartTime
	global APP_NAME, APP_CKPT_DIR

	# List of current app's checkpoint files
	ckptFiles = glob.glob(APP_CKPT_DIR[gvCurrentApp] + '/' + 'ckpt_*.dmtcp')
	
	# Launch the currently set application
	string = ''

	# If there are no checkpoint files, then start afresh
	if (len(ckptFiles) == 0):
		string = DMTCP_LAUNCH + " "
		# Set the ckeckpointing interval
		string += '-i ' + str(CKPT_INTERVAL[gvCurrentApp]) + ' '
		# If the LW app is being started, set the --exit-after-ckpt option
		if ((gvCurrentApp % 2) == 0):
			string += '--exit-after-ckpt ' + str(SWITCH_POINT) + ' '
		string += '--ckptdir ' + APP_CKPT_DIR[gvCurrentApp] + ' '
		string += APP_NAME[gvCurrentApp]
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
		string += '-i ' + str(CKPT_INTERVAL[gvCurrentApp]) + ' '
		# If the LW app is being started, set the --exit-after-ckpt option
		if (gvCurrentApp == 0):
			string += '--exit-after-ckpt ' + str(SWITCH_POINT) + ' '
		string += '--ckptdir ' + APP_CKPT_DIR[gvCurrentApp] + ' '
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
def waitTillFailure(proc, failureTime):

	global gvStartTime, gvDone, gvStatsLock, gvCurrentApp, gvTotalFL

	# Calculate when the next failure should take place
	nextFailure = failureTime
	if failureTime == 0:
		nextFailure = int(random.weibullvariate(WEIBULL_SCALE, WEIBULL_SHAPE))

	# Holds the reason for exisitng the while loop below
	switch = False

	# Loop until its time to inject a failure
	while ((time.time() - gvStartTime) <= nextFailure):
		# Every iteration, poll the currently running DMTCP process
		# to learn if it has died. If it has, that means it is time
		# to switch to the HW app.
		if (proc.poll() is not None):
			# Set the reason for quitting the loop as switch and break
			switch = True
			break

	# Caluclate the time which the app ran for during this instance
	timeDiff = time.time() - gvStartTime

	# Kill the process if failure is the reason for quitting the loop
	if switch is False:
		# --kill may block while the application is ckpting
		#subprocess.call(DMTCP_COMMAND + ' --kill', shell=True)
		proc.send_signal(9);
		nextFailure = 0;
	else:
		nextFailure = nextFailure - timeDiff
		
	# Acquire the lock on calculate stats
	gvStatsLock.acquire()

	# No need to calculate if the entire run has already ended
	if (gvDone is False):

		calculateStats(timeDiff)

		# If switching, move on to the HW app
		# Else had a failure, so run the LW app
		# And increment the number of failures
		if switch is False:
			gvTotalFL[gvCurrentApp] += 1	
		if (gvCurrentApp == (NUM_APPS - 1)):
			gvCurrentApp = 0
		else:
			gvCurrentApp += 1

		gvStartTime = time.time()

	# Release the lock on calculate stats
	gvStatsLock.release()

	return nextFailure

# DESCRIPTION:
# > This function (thread) keeps running the application and injects failures
# > It keeps doing this until the runtime has ended
# INPUTS:
# > None
# OUTPUTS:
# > None
def scheduleApps():

	global gvDone

	failureTime = 0
	while(gvDone is False):
		proc = runApplication()
		if (gvDone):
			break
		failureTime = waitTillFailure(proc, failureTime)

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
# > This function sorts the n apps and creates pairs of light
# > weight and heavy weight applications for scheduling.
# INPUTS:
# > None
# OUTPUTS:
# > None
def sortApps():
	
	global APP_NAME, CKPT_INTERVAL	
	global gvTotalCO, gvTotalUW, gvTotalLW, gvTotalRT, gvTotalCP, gvTotalFL


	# Sort the apps in pairs of LW and HW
	tmpAppName = list(APP_NAME)
	tmpCkptInt = list(CKPT_INTERVAL)
	
	for i in range(0, NUM_APPS):
		index = tmpCkptInt.index(min(tmpCkptInt))
		if ((i % 2) == 1):
			index = tmpCkptInt.index(max(tmpCkptInt))
		APP_NAME[i] = tmpAppName[index]
		CKPT_INTERVAL[i] = tmpCkptInt[index]
		del tmpAppName[index]
		del tmpCkptInt[index]
	
	# Initialize the calculation varaibles
	gvTotalCO = [0]*NUM_APPS
	gvTotalUW = [0]*NUM_APPS
	gvTotalLW = [0]*NUM_APPS
	gvTotalRT = [0]*NUM_APPS
	gvTotalCP = [0]*NUM_APPS
	gvTotalFL = [0]*NUM_APPS

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
		print ("ERROR: Please specify a valid path to the DMTCP root directory.\n" \
		"Also, make sure to run configure and build within the DMTCP directory.\n")
		exit(-1)


# DESCRIPTION:
# > This function removes the previous ckpt directory and creates  a new one.
# INPUTS:
# > None
# OUTPUTS:
# > None
def prepareCkptDirs():

	global APP_CKPT_DIR

	try:
		if os.path.exists(GLOBAL_CKPT_DIR):
			shutil.rmtree(GLOBAL_CKPT_DIR, ignore_errors=True)
		os.makedirs(GLOBAL_CKPT_DIR)
		APP_CKPT_DIR = [0]*NUM_APPS
		for i in range(len(APP_NAME)):
			APP_CKPT_DIR[i] = GLOBAL_CKPT_DIR + "/" + os.path.basename(APP_NAME[i]).split(" ")[0]
			os.makedirs(APP_CKPT_DIR[i])
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
	global NUM_APPS, APP_NAME, CKPT_INTERVAL, SWTICH_POINT 
	global DMTCP_PATH, DMTCP_BIN, DMTCP_LAUNCH, DMTCP_RESTART, DMTCP_COMMAND
	global SCALE_FACTOR

	# Parse the arguments and set the global constants
	parser = argparse.ArgumentParser(prog="swtch_ckpt_run", description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter)

	parser.add_argument("-n", "--num-apps", type=int, help="The number of applications to run. Default = 2")
	parser.add_argument("-a", "--app-name", type=str, nargs='+', help="The names of the n applications. Specify in the same order as --ckpt-int.")
	parser.add_argument("-i", "--ckpt-int", type=float, nargs='+', help="The checkpointing interval of the n applications. Specify in the same order as --app-name.")
	parser.add_argument("-c", "--ckpts-lw", type=int, help="The number of checkpoints after which the low weight applications should switch. Default = 2")
	parser.add_argument("-t", "--run-time", type=float, help="The total run time of the program in hours. Default = 100 hours")
	parser.add_argument("-m", "--mtbf", type=float, help="The MTBF of the system. Default = 10 hours")
	parser.add_argument("-w", "--weibull-shape", type=float, help="The shape parameter of the Weibull failure curve. Default = 0.6")
	parser.add_argument("-s", "--scale-factor", type=float, help="The paramter to scale hours to seconds. Default = 1800")
	parser.add_argument("-d", "--dmtcp-path", type=str, help="The path to the DMTCP root directory. Default = ../../dmtcp")
	
	args = parser.parse_args()

	if args.scale_factor:
		SCALE_FACTOR = args.scale_factor
	if args.num_apps:
		NUM_APPS = args.num_apps
	if args.app_name:
		APP_NAME = args.app_name
	if args.ckpt_int:
		CKPT_INTERVAL = [int(HOURS_TO_SECS(app/SCALE_FACTOR)) for app in args.ckpt_int]
	
	# Verify that the number of apps is consistent accross the variables
	if (NUM_APPS != len(APP_NAME)) or (NUM_APPS != len(CKPT_INTERVAL)):
		print("ERROR: The number of apps in --app-name and --ckpt-int should be consistent with --num-apps.\n")
		exit(-1)
	
	if args.ckpts_lw:
		SWITCH_POINT = args.ckpts_lw
	if args.run_time:
		TOTAL_TIME = HOURS_TO_SECS(args.run_time/SCALE_FACTOR)
	if args.mtbf:
		MTBF = HOURS_TO_SECS(args.mtbf/SCALE_FACTOR)
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

	# Remove any existing checkpoint data files and add new ones
	prepareCkptDirs()
	
	# Sort apps for scheduling
	sortApps()

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
	
	# Kill any exisiting dmtcp processes
	subprocess.call(DMTCP_COMMAND + ' --kill', shell=True)
	
	exit()

# Program beginning #
if __name__ == "__main__":
	main()
