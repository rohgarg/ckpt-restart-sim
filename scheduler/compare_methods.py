#!/usr/bin/python

# Import libraries #

import sys, argparse
import shlex, glob
import os, subprocess, threading, shutil
import time, math, random

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

DESCRIPTION = "The program runs two application in isolation and using switch checkpointing, and compares the results.\n"

SCALE_FACTOR = 1800

TOTAL_TIME = 100                 # Total time that the program should run for

MTBF = 10                        # Mean time between failures for the entire system
WEIBULL_SHAPE = 0.6              # Shape parameter for failure calculation

CKPT_INTERVAL = [0]*2
CKPT_INTERVAL[0] = 1             # Checkpointing interval (or compute time per interval) for app 1
CKPT_INTERVAL[1] = 5             # Checkpointing interval (or compute time per interval) for app 2
NUM_CKPTS_LW = 2                 # Number of checkpoints after which app 1 should switch

APP_NAME = ['app']*2             # Name of apps

DMTCP_PATH = "../../dmtcp"

# Global Variables #

gvTotalCOS = [0]*2                # Total checkpointing overhead of app 1 and 2
gvTotalUWS = [0]*2                # Total useful work done by app 1 and 2
gvTotalLWS = [0]*2                # Total lost work of app 1 and 2
gvTotalRTS = [0]*2                # Total run time of app 1 and 2
gvTotalCPS = [0]*2                # Total number of checkpoints during app 1 and 2
gvTotalFLS = [0]*2                # Total number of failures

gvTotalCOI = [0]*2                # Total checkpointing overhead of app 1 and 2
gvTotalUWI = [0]*2                # Total useful work done by app 1 and 2
gvTotalLWI = [0]*2                # Total lost work of app 1 and 2
gvTotalRTI = [0]*2                # Total run time of app 1 and 2
gvTotalCPI = [0]*2                # Total number of checkpoints during app 1 and 2
gvTotalFLI = [0]*2                # Total number of failures

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

	string  = "\n                       Isolated		Switch Ckpt\n\n"
	string += "Process Name         = " + APP_NAME[0] + "\n\n"
	string += "Checkpoint Time      = " + gvTotalCOI[0] + "		" + gvTotalCOS[0] + "\n"
	string += "Useful Work          = " + gvTotalUWI[0] + "		" + gvTotalUWS[0] + "\n"
	string += "Lost Work            = " + gvTotalLWI[0] + "		" + gvTotalLWS[0] + "\n"
	string += "Run Time             = " + gvTotalRTI[0] + "		" + gvTotalRTS[0] + "\n"
	string += "Num Checkpoints      = " + gvTotalCPI[0] + "		" + gvTotalCPS[0] + "\n"
	string += "Num Failures         = " + gvTotalFLI[0] + "		" + gvTotalFLS[0] + "\n"
	string += "\n"
	string += "Process Name         = " + APP_NAME[1] + "\n\n"
	string += "Checkpoint Time      = " + gvTotalCOI[1] + "		" + gvTotalCOS[1] + "\n"
	string += "Useful Work          = " + gvTotalUWI[1] + "		" + gvTotalUWS[1] + "\n"
	string += "Lost Work            = " + gvTotalLWI[1] + "		" + gvTotalLWS[1] + "\n"
	string += "Run Time             = " + gvTotalRTI[1] + "		" + gvTotalRTS[1] + "\n"
	string += "Num Checkpoints      = " + gvTotalCPI[1] + "		" + gvTotalCPS[1] + "\n"
	string += "Num Failures         = " + gvTotalFLI[1] + "		" + gvTotalFLS[1] + "\n"
	string += "\n"
	string += "Total runtime statistics:" + "\n\n"
	string += "Checkpoint Time      = " + str(float(gvTotalCOI[0].split('h')[0])+float(gvTotalCOI[1].split('h')[0])) + "h		"  + str(float(gvTotalCOS[0].split('h')[0])+float(gvTotalCOS[1].split('h')[0])) + "h\n"
	string += "Useful Work          = " + str(float(gvTotalUWI[0].split('h')[0])+float(gvTotalUWI[1].split('h')[0])) + "h		"  + str(float(gvTotalUWS[0].split('h')[0])+float(gvTotalUWS[1].split('h')[0])) + "h\n"
	string += "Lost Work            = " + str(float(gvTotalLWI[0].split('h')[0])+float(gvTotalLWI[1].split('h')[0])) + "h		"  + str(float(gvTotalLWS[0].split('h')[0])+float(gvTotalLWS[1].split('h')[0])) + "h\n"
	string += "Run Time             = " + str(float(gvTotalRTI[0].split('h')[0])+float(gvTotalRTI[1].split('h')[0])) + "h		"  + str(float(gvTotalRTS[0].split('h')[0])+float(gvTotalRTS[1].split('h')[0])) + "h\n"
	string += "Num Failures         = " + str(int(gvTotalFLI[0])+int(gvTotalFLI[1])) + "		" + str(int(gvTotalFLS[0])+int(gvTotalFLS[1])) + "\n"

	print(string)

# DESCRIPTION:
# > Main function parses arguments and starts the threads
# INPUTS:
# > None
# OUTPUTS:
# > None
def main():

	global TOTAL_TIME
	global MTBF, WEIBULL_SHAPE
	global CKPT_INTERVAL, NUM_CKPTS_LW, APP_NAME
	global DMTCP_PATH
	global SCALE_FACTOR

	# Parse the arguments and set the global constants
	parser = argparse.ArgumentParser(prog="compare_methods", description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter)

	parser.add_argument("-d", "--dmtcp-path", type=str, help="The path to the DMTCP root directory. Default = ../../dmtcp")
	parser.add_argument("-l", "--name-lw", type=str, help="The name of the low weight application. REQUIRED.")
	parser.add_argument("-g", "--name-hw", type=str, help="The name of the high weight application. REQUIRED.")
	parser.add_argument("-t", "--run-time", type=str, help="The total run time of the program in hours. Default = 100 hours.")
	parser.add_argument("-m", "--mtbf", type=str, help="The MTBF of the system. Default = 10 hours.")
	parser.add_argument("-c", "--ckpts-lw", type=str, help="The number of checkpoints after which the low weight applications should switch. Default = 2.")
	parser.add_argument("-i", "--ckpt-int-lw", type=str, help="The checkpointing interval of the low weight application. Default = 1 hour.")
	parser.add_argument("-n", "--ckpt-int-hw", type=str, help="The checkpointing interval of the high weight application. Default = 5 hours.")
	parser.add_argument("-w", "--weibull-shape", type=str, help="The shape parameter of the Weibull failure curve. Default = 0.6.")
	parser.add_argument("-s", "--scale-factor", type=str, help="The parameter to scale hours to seconds. Default = 1800.")	

	args = parser.parse_args()

	if args.dmtcp_path:
		DMTCP_PATH = args.dmtcp_path
	if args.name_lw:
		APP_NAME[0] = args.name_lw
	if args.name_hw:
		APP_NAME[1] = args.name_hw
	if args.run_time:
		TOTAL_TIME = args.run_time
	if args.mtbf:
		MTBF = args.mtbf
	if args.ckpts_lw:
		NUM_CKPTS_LW = args.ckpts_lw
	if args.ckpt_int_lw:
		CKPT_INTERVAL[0] = args.ckpt_int_lw
	if args.ckpt_int_hw:
		CKPT_INTERVAL[1] = args.ckpt_int_hw
	if args.weibull_shape:
		WEIBULL_SHAPE = args.weibull_shape
	if args.scale_factor:
		SCALE_FACTOR = args.scale_factor

	string  = 'python proposed_switch_ckpt.py '
	string += '-d ' + DMTCP_PATH + ' '
	string += '-l \"' + APP_NAME[0] + '\" '
	string += '-g \"' + APP_NAME[1] + '\" '
	string += '-t ' + TOTAL_TIME + ' '
	string += '-m ' + MTBF + ' '
	string += '-c ' + NUM_CKPTS_LW + ' '
	string += '-i ' + CKPT_INTERVAL[0] + ' '
	string += '-n ' + CKPT_INTERVAL[1] + ' '
	string += '-w ' + WEIBULL_SHAPE + ' '
	string += '-s ' + SCALE_FACTOR
	print ("Now running: " + string)
	proc1 = subprocess.Popen(shlex.split(string), stdout=subprocess.PIPE)

	app = 0
	for line in proc1.stdout:
		line = line.rstrip().strip()
		if "Failures" in line:
			gvTotalFLS[app] = line.split('= ')[1]
			app += 1
			if app == 2:
				break
		if "Num Checkpoints" in line:
			gvTotalCPS[app] = line.split('= ')[1]
		elif "Checkpoint" in line:
			gvTotalCOS[app] = line.split('= ')[1]
		elif "Useful" in line:
			gvTotalUWS[app] = line.split('= ')[1]
		elif "Lost" in line:
			gvTotalLWS[app] = line.split('= ')[1]
		elif "Run" in line:
			gvTotalRTS[app] = line.split('= ')[1]

	string  = 'python isolated_app.py '
	string += '-d ' + DMTCP_PATH + ' '
	string += '-n \"' + APP_NAME[0] + '\" '
	string += '-t ' + str(float(TOTAL_TIME)/2) + ' '
	string += '-m ' + MTBF + ' '
	string += '-i ' + CKPT_INTERVAL[0] + ' '
	string += '-w ' + WEIBULL_SHAPE + ' '
	string += '-s ' + SCALE_FACTOR
	print ("Now running: " + string)
	proc2 = subprocess.Popen(shlex.split(string), stdout=subprocess.PIPE)

	for line in proc2.stdout:
		line = line.rstrip().strip()
		if "Num Checkpoints" in line:
			gvTotalCPI[0] = line.split('= ')[1]
		elif "Checkpoint" in line:
			gvTotalCOI[0] = line.split('= ')[1]
		elif "Useful" in line:
			gvTotalUWI[0] = line.split('= ')[1]
		elif "Lost" in line:
			gvTotalLWI[0] = line.split('= ')[1]
		elif "Run" in line:
			gvTotalRTI[0] = line.split('= ')[1]
		elif "Failures" in line:
			gvTotalFLI[0] = line.split('= ')[1]
	
	string  = 'python isolated_app.py '
	string += '-d ' + DMTCP_PATH + ' '
	string += '-n \"' + APP_NAME[1] + '\" '
	string += '-t ' + str(float(TOTAL_TIME)/2) + ' '
	string += '-m ' + MTBF + ' '
	string += '-i ' + CKPT_INTERVAL[1] + ' '
	string += '-w ' + WEIBULL_SHAPE + ' '
	string += '-s ' + SCALE_FACTOR
	print ("Now running: " + string)
	proc3 = subprocess.Popen(shlex.split(string), stdout=subprocess.PIPE)

	for line in proc3.stdout:
		line = line.rstrip().strip()
		if "Num Checkpoints" in line:
			gvTotalCPI[1] = line.split('= ')[1]
		elif "Checkpoint" in line:
			gvTotalCOI[1] = line.split('= ')[1]
		elif "Useful" in line:
			gvTotalUWI[1] = line.split('= ')[1]
		elif "Lost" in line:
			gvTotalLWI[1] = line.split('= ')[1]
		elif "Run" in line:
			gvTotalRTI[1] = line.split('= ')[1]
		elif "Failures" in line:
			gvTotalFLI[1] = line.split('= ')[1]
	
	# Print the final statistics
	printStats()

	exit()

# Program beginning #
if __name__ == "__main__":
	main()
