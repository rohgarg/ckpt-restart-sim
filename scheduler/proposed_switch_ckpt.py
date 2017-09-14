#!/usr/bin/python

# Import libraries #

import sys, argparse
import shlex, glob
import os, subprocess, threading
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

DESCRIPTION = "The program runs two application using the switch checkpointing method.\n"

SCALE_FACTOR = 1800                                     # The factor which the times should be scaled down by
                                                        # Current value scales 100 hours to 200 seconds

TOTAL_TIME = HOURS_TO_SECS(100/SCALE_FACTOR)            # Total time that the program should run for

MTBF = HOURS_TO_SECS(10/SCALE_FACTOR)                   # Mean time between failures for the entire system
WEIBULL_SHAPE = 0.6                                     # Shape parameter for failure calculation
WEIBULL_SCALE = MTBF/gamma(1+(1/WEIBULL_SHAPE))         # Scale parameter for failure calculation

CKPT_INTERVAL = [0]*2
CKPT_INTERVAL[0] = int(HOURS_TO_SECS(1/SCALE_FACTOR))   # Checkpointing interval (or compute time per interval) for app 1
CKPT_INTERVAL[1] = int(HOURS_TO_SECS(5/SCALE_FACTOR))   # Checkpointing interval (or compute time per interval) for app 2
NUM_CKPTS_LW = 2                                        # Number of checkpoints after which app 1 should switch

APP_NAME = ['app']*2
APP_NAME[0] = '../dmtcp/test/dmtcp1'                    # Name of app 1
APP_NAME[1] = '../dmtcp/test/dmtcp2'                    # Name of app 2

APP_NAME_OUT = ['app.out']*2
APP_NAME_OUT[0] = 'app1.out'                            # Output file for app 1
APP_NAME_OUT[1] = 'app2.out'                            # Output file for app 2

# Global Variables #

gvTotalCO = [0]*2                # Total checkpointing overhead of app 1 and 2
gvTotalUW = [0]*2                # Total useful work done by app 1 and 2
gvTotalLW = [0]*2                # Total lost work of app 1 and 2
gvTotalRT = [0]*2                # Total run time of app 1 and 2
gvTotalCP = [0]*2                # Total number of checkpoints during app 1 and 2

gvTotalFL = 0                    # Total number of system failures

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

	global gvTotalFL
	global gvTotalCO, gvTotalUW, gvTotalLW, gvTotalRT, gvTotalCP

	# Scale back the values in seconds to hours
	TotalCO = [(SECS_TO_HOURS(gvTotalCO[0])*SCALE_FACTOR), (SECS_TO_HOURS(gvTotalCO[1])*SCALE_FACTOR)]
	TotalUW = [(SECS_TO_HOURS(gvTotalUW[0])*SCALE_FACTOR), (SECS_TO_HOURS(gvTotalUW[1])*SCALE_FACTOR)]
	TotalLW = [(SECS_TO_HOURS(gvTotalLW[0])*SCALE_FACTOR), (SECS_TO_HOURS(gvTotalLW[1])*SCALE_FACTOR)]
	TotalRT = [(SECS_TO_HOURS(gvTotalRT[0])*SCALE_FACTOR), (SECS_TO_HOURS(gvTotalRT[1])*SCALE_FACTOR)]

	string  = "\n"
	string += "Process Name         = " + APP_NAME[0] + "\n"
	string += "Checkpoint Time      = " + str("%.2f" % TotalCO[0]) + "h\n"
	string += "Useful Work          = " + str("%.2f" % TotalUW[0]) + "h\n"
	string += "Lost Work            = " + str("%.2f" % TotalLW[0]) + "h\n"
	string += "Run Time             = " + str("%.2f" % TotalRT[0]) + "h\n"
	string += "Num Checkpoints      = " + str(gvTotalCP[0]) + "\n"
	string += "\n"
	string += "Process Name         = " + APP_NAME[1] + "\n"
	string += "Checkpoint Time      = " + str("%.2f" % TotalCO[1]) + "h\n"
	string += "Useful Work          = " + str("%.2f" % TotalUW[1]) + "h\n"
	string += "Lost Work            = " + str("%.2f" % TotalLW[1]) + "h\n"
	string += "Run Time             = " + str("%.2f" % TotalRT[1]) + "h\n"
	string += "Num Checkpoints      = " + str(gvTotalCP[1]) + "\n"
	string += "\n"
	string += "Total runtime statistics:\n"
	string += "Checkpoint Time      = " + str("%.2f" % (TotalCO[0]+TotalCO[1])) + "h\n"
	string += "Useful Work          = " + str("%.2f" % (TotalUW[0]+TotalUW[1])) + "h\n"
	string += "Lost Work            = " + str("%.2f" % (TotalLW[0]+TotalLW[1])) + "h\n"
	string += "Run Time             = " + str("%.2f" % (TotalRT[0]+TotalRT[1])) + "h\n"
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

	# List of current app's checkpoint files
	ckptFiles = glob.glob('ckpt_'+APP_NAME[gvCurrentApp]+'_*.dmtcp')

	# Launch the currently set application
	string = ''

	# If there are no checkpoint files, then start afresh
	if (len(ckptFiles) == 0):
		string = '../dmtcp/bin/dmtcp_launch '
		# Set the ckeckpointing interval
		string += '-i ' + str(CKPT_INTERVAL[gvCurrentApp]) + ' '
		# If the LW app is being started, set the --exit-after-ckpt option
		if (gvCurrentApp == 0):
			string += '--exit-after-ckpt ' + str(NUM_CKPTS_LW) + ' '
		string += APP_NAME[gvCurrentApp]
		#string += '>> ' + APP_NAME_OUT[gvCurrentApp] +' &'
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

		string = '../dmtcp/bin/dmtcp_restart '
		# Set the ckeckpointing interval
		string += '-i ' + str(CKPT_INTERVAL[gvCurrentApp]) + ' '
		# If the LW app is being started, set the --exit-after-ckpt option
		if (gvCurrentApp == 0):
			string += '--exit-after-ckpt ' + str(NUM_CKPTS_LW) + ' '
		string += ckptFile
		#string += '>> ' + APP_NAME_OUT[gvCurrentApp] +' &'

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

	global gvStartTime, gvDone, gvStatsLock, gvCurrentApp, gvTotalFL

	# Calculate when the next failure should take place
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
		subprocess.call('../dmtcp/bin/dmtcp_command --kill', shell=True)

	# Acquire the lock on calculate stats
	gvStatsLock.acquire()

	# No need to calculate if the entire run has already ended
	if (gvDone is False):

		calculateStats(timeDiff)

		# If switching, move on to the HW app
		# Else had a failure, so run the LW app
		# And increment the number of failures
		if switch:
			gvCurrentApp = 1
		else:
			gvCurrentApp = 0
			gvTotalFL += 1

		gvStartTime = time.time()

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
	subprocess.call('../dmtcp/bin/dmtcp_command --kill', shell=True)
	calculateStats(timeDiff)

	# Release the lock on calculate stats
	gvStatsLock.release()

# DESCRIPTION:
# > Main function parses arguments and starts the threads
# INPUTS:
# > None
# OUTPUTS:
# > None
def main():

	global TOTAL_TIME
	global MTBF, WEIBULL_SHAPE, WEIBULL_SCALE
	global CKPT_INTERVAL, NUM_CKPTS_LW, APP_NAME

	# Parse the arguments and set the global constants
	parser = argparse.ArgumentParser(prog="swtch_ckpt_run", description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter)

	parser.add_argument("-l", "--name-lw", type=str, help="The name of the low weight application.")
	parser.add_argument("-g", "--name-hw", type=str, help="The name of the high weight application.")
	parser.add_argument("-t", "--run-time", type=float, help="The total run time of the program in hours. Default = 100 hours.")
	parser.add_argument("-m", "--mtbf", type=float, help="The MTBF of the system. Default = 10 hours.")
	parser.add_argument("-c", "--ckpts-lw", type=int, help="The number of checkpoints after which the low weight applications should switch. Default = 2.")
	parser.add_argument("-i", "--ckpt-int-lw", type=float, help="The checkpointing interval of the low weight application. Default = 1 hour.")
	parser.add_argument("-n", "--ckpt-int-hw", type=float, help="The checkpointing interval of the high weight application. Default = 5 hours.")
	parser.add_argument("-w","--weibull-shape", type=float, help="The shape parameter of the Weibull failure curve. Default = 0.6.")
	
	args = parser.parse_args()

	if args.name_lw:
		APP_NAME[0] = args.name_lw
	if args.name_hw:
		APP_NAME[1] = args.name_hw
	if args.run_time:
		TOTAL_TIME = HOURS_TO_SECS(args.run_time/SCALE_FACTOR)
	if args.mtbf:
		MTBF = HOURS_TO_SECS(args.mtbf/SCALE_FACTOR)
	if args.ckpts_lw:
		NUM_CKPTS_LW = args.ckpts_lw
	if args.ckpt_int_lw:
		CKPT_INTERVAL[0] = int(HOURS_TO_SECS(args.ckpt_int_lw/SCALE_FACTOR))
	if args.ckpt_int_hw:
		CKPT_INTERVAL[1] = int(HOURS_TO_SECS(args.ckpt_int_hw/SCALE_FACTOR))
	if args.weibull_shape:
		WEIBULL_SHAPE = args.weibull_shape

	WEIBULL_SCALE = MTBF/gamma(1+(1/WEIBULL_SHAPE))

	# Remove any existing checkpoint data files
	if (len(glob.glob('ckpt_*.dmtcp')) != 0):
		subprocess.call('rm ckpt_*.dmtcp', shell=True)
	
	# Remove any existing checkpoint restart files
	if (len(glob.glob('dmtcp_restart_script*.sh')) != 0):
		subprocess.call('rm dmtcp_restart_script*.sh', shell=True)

	# Kill any exisiting dmtcp processes
	subprocess.call('../dmtcp/bin/dmtcp_command --kill', shell=True)

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

	# Remove any generated checkpoint data files
	if (len(glob.glob('ckpt_*.dmtcp')) != 0):
		subprocess.call('rm ckpt_*.dmtcp', shell=True)
	
	# Remove any generated checkpoint restart files
	if (len(glob.glob('dmtcp_restart_script*.sh')) != 0):
		subprocess.call('rm dmtcp_restart_script*.sh', shell=True)

	# Remove any generated timings files
	if (len(glob.glob('timings.*.csv')) != 0):
		subprocess.call('rm timings.*.csv', shell=True)

	exit()

# Program beginning #
if __name__ == "__main__":
	main()
