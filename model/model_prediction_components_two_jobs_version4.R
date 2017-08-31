library(MASS)
library(qualityTools)


# Runtime and checkpoint configuration parameters
MAX_RUN_TIME = 1000
BASE_DELTA = 0.5
DELTA_FACTOR = 25
OCI_STRETCH_FACTOR = 4

# Switching configuration parameters
MAX_SWITCH_POINT = 25

# Failure realated configuration parameters
MTBF = 10 #in hours
SHAPE = 0.6
LAMBDA = MTBF/(gamma(1 + 1/SHAPE))
AVG_LOST_WORK_FRACTION = 0.4

# These are pretty much fixed
INFINITE = 99999
HOUR = 1


round_me <- function (input)
{ 
	result <- round(input, 5)
	return (result)
}

estimate_OCI <- function (mtbf, delta)
{ 
	result <- (sqrt(2*mtbf*delta) - delta)
	return (result)
}

failure_probability <- function (time_low, time_high, lambda_parameter, shape_parameter)
{ 
	
	result <- exp(-((time_low/lambda_parameter )^shape_parameter)) - exp(-((time_high/lambda_parameter)^shape_parameter))

	return (result)
}

wasted_work_overhead <- function (start_time, my_checkpoint_threshold, avg_lost_work_fraction, tau, delta)
{ 
	end_time= start_time + my_checkpoint_threshold*(tau + delta)
	num_fail <- failure_probability(start_time, end_time, LAMBDA, SHAPE)*(MAX_RUN_TIME/MTBF)
	#cat("Num fail ", num_fail, "\n")
	result <- num_fail*avg_lost_work_fraction*(tau+delta)
	return (result)
}

io_overhead <- function (start_time, my_checkpoint_threshold, tau, delta)
{ 
	io_overhead = 0
	myseq <- seq(1, my_checkpoint_threshold, by = 1) 

	for (i in myseq ){

		low_time = start_time + i*(tau + delta)
		high_time= low_time + (tau + delta)
		if(i == my_checkpoint_threshold){high_time= low_time + 9999*(tau + delta)}

		regional_num_fail = (MAX_RUN_TIME/MTBF)*failure_probability(low_time, high_time, LAMBDA, SHAPE)

		io_overhead <- (io_overhead + i*regional_num_fail*delta)

		#cat("i: ", i, " low_time ", low_time, " high_time ", high_time, " regional_num_fail ",  regional_num_fail, " iter_private_io ", i*regional_num_fail*delta, " io_overhead ", io_overhead, "\n")

	}
	
	return (io_overhead)
}

useful_work <- function (start_time, my_checkpoint_threshold, tau, delta)
{ 
	useful_work = 0
	myseq <- seq(1, my_checkpoint_threshold, by = 1) 

	for (i in myseq ){
		
		low_time = start_time + i*(tau + delta)
		high_time= low_time + (tau + delta)
		if(i == my_checkpoint_threshold){high_time= low_time + 9999*(tau + delta)}

		regional_num_fail = (MAX_RUN_TIME/MTBF)*failure_probability(low_time, high_time, LAMBDA, SHAPE)

		useful_work <- useful_work + i*regional_num_fail*tau

	}
	
	return (useful_work)
}


cat("\n---------------Parameters----------------------")
cat("\nMaximum run time", MAX_RUN_TIME, "\nMTBF ", MTBF, "\nShape ", SHAPE, "\nScale ", LAMBDA, 
	"\nAvg. lost work fraction", AVG_LOST_WORK_FRACTION, "\nBase Delta ", BASE_DELTA, "\nDelta Factor ", DELTA_FACTOR, 
	"\nOCI Stretch Factor ", OCI_STRETCH_FACTOR )
cat("\n-----------------------------------------------")


#--------------------- Runs in Isoltation --------------------------------------#

MAX_RUN_TIME = MAX_RUN_TIME/2
SWITCH_POINT = INFINITE

#--------------------- Light Weight Application (Isolation) --------------------------------------#

light_weight_app_delta = BASE_DELTA/DELTA_FACTOR
light_weight_app_tau  = round(estimate_OCI(MTBF, light_weight_app_delta),2)

DELTA = light_weight_app_delta
TAU = light_weight_app_tau 

my_checkpoint_threshold = INFINITE
start_time = 0
end_time= start_time + INFINITE*(TAU + DELTA)

#cat("Isolation: Light Weight Application: delta: ", DELTA, " tau: ", TAU, " Switch point: ", SWITCH_POINT, " End time: ", end_time, "\n")

isolated_light_weight_app_wasted_work <- wasted_work_overhead(start_time, my_checkpoint_threshold, AVG_LOST_WORK_FRACTION, TAU, DELTA)
isolated_light_weight_app_checkpoint_work <- io_overhead(start_time, my_checkpoint_threshold, TAU, DELTA)
isolated_light_weight_app_useful_work <- useful_work(start_time, my_checkpoint_threshold, TAU, DELTA)

isolated_light_weight_app_total_time = isolated_light_weight_app_useful_work + isolated_light_weight_app_checkpoint_work + isolated_light_weight_app_wasted_work

#--------------------- Heavy Weight Application (Isolation) --------------------------------------#

heavy_weight_app_delta = round(BASE_DELTA,2)
heavy_weight_app_tau   = round(estimate_OCI(MTBF, heavy_weight_app_delta),2)

DELTA = heavy_weight_app_delta
TAU = heavy_weight_app_tau 

my_checkpoint_threshold = INFINITE
start_time = 0
end_time= start_time + INFINITE*(TAU + DELTA)

#cat("Isolation: Heavy Weight Application is running: delta: ", DELTA, "  tau: ", TAU, " Switch point: ", SWITCH_POINT, " End time: ", end_time, "\n")

isolated_heavy_weight_app_wasted_work <- wasted_work_overhead(start_time, my_checkpoint_threshold, AVG_LOST_WORK_FRACTION, TAU, DELTA)
isolated_heavy_weight_app_checkpoint_work <- io_overhead(start_time, my_checkpoint_threshold, TAU, DELTA)
isolated_heavy_weight_app_useful_work <- useful_work(start_time, my_checkpoint_threshold, TAU, DELTA)

isolated_heavy_weight_app_total_time = isolated_heavy_weight_app_useful_work + isolated_heavy_weight_app_checkpoint_work + isolated_heavy_weight_app_wasted_work

MAX_RUN_TIME = 2*MAX_RUN_TIME

#--------------------- Both Applications done (Isolation) --------------------------------------#

cat("\n---------------Isotation Results without OCI Stretch----------------")
cat ("\nLight Weight App: Total Time: ", isolated_light_weight_app_total_time, 
	" Useful: ", isolated_light_weight_app_useful_work, 
	" Checkpoint: ", isolated_light_weight_app_checkpoint_work, 
	" Lost: ", isolated_light_weight_app_wasted_work)

cat ("\nHeavy Weight App: Total Time: ", isolated_heavy_weight_app_total_time, 
	" Useful: ", isolated_heavy_weight_app_useful_work, 
	" Checkpoint: ", isolated_heavy_weight_app_checkpoint_work, 
	" Lost: ", isolated_heavy_weight_app_wasted_work)

cat ("\nAll Combine Apps: Total Time: ", isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time, 
	" Useful: ", isolated_light_weight_app_useful_work + isolated_heavy_weight_app_useful_work, 
	" Checkpoint: ", isolated_light_weight_app_checkpoint_work + isolated_heavy_weight_app_checkpoint_work, 
	" Lost: ", isolated_light_weight_app_wasted_work + isolated_heavy_weight_app_wasted_work, "\n")

cat("\n---------------Isotation Results without OCI Stretch (*scaled*)----------------")
cat ("\nLight Weight App: Total Time: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*isolated_light_weight_app_total_time, 
	" Useful: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*isolated_light_weight_app_useful_work, 
	" Checkpoint: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*isolated_light_weight_app_checkpoint_work, 
	" Lost: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*isolated_light_weight_app_wasted_work)

cat ("\nHeavy Weight App: Total Time: ", isolated_heavy_weight_app_total_time, 
	" Useful: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*isolated_heavy_weight_app_useful_work, 
	" Checkpoint: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*isolated_heavy_weight_app_checkpoint_work, 
	" Lost: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*isolated_heavy_weight_app_wasted_work)

cat ("\nAll Combine Apps: Total Time: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time), 
	" Useful: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*(isolated_light_weight_app_useful_work + isolated_heavy_weight_app_useful_work), 
	" Checkpoint: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*(isolated_light_weight_app_checkpoint_work + isolated_heavy_weight_app_checkpoint_work), 
	" Lost: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*(isolated_light_weight_app_wasted_work + isolated_heavy_weight_app_wasted_work), "\n")


cat("\n-----------------------------------------------")

#--------------------- Runs in Isoltation with OCI_STRETCH_FACTOR --------------------------------------#

MAX_RUN_TIME = MAX_RUN_TIME/2
SWITCH_POINT = INFINITE

#--------------------- Light Weight Application (Isolation) --------------------------------------#

light_weight_app_delta = BASE_DELTA/DELTA_FACTOR
light_weight_app_tau  = round(estimate_OCI(MTBF, light_weight_app_delta),2)

DELTA = light_weight_app_delta
TAU = light_weight_app_tau 

my_checkpoint_threshold = INFINITE
start_time = 0
end_time= start_time + INFINITE*(TAU + DELTA)

#cat("Isolation: Light Weight Application: delta: ", DELTA, " tau: ", TAU, " Switch point: ", SWITCH_POINT, " End time: ", end_time, "\n")

isolated_light_weight_app_wasted_work <- wasted_work_overhead(start_time, my_checkpoint_threshold, AVG_LOST_WORK_FRACTION, TAU, DELTA)
isolated_light_weight_app_checkpoint_work <- io_overhead(start_time, my_checkpoint_threshold, TAU, DELTA)
isolated_light_weight_app_useful_work <- useful_work(start_time, my_checkpoint_threshold, TAU, DELTA)

isolated_light_weight_app_total_time = isolated_light_weight_app_useful_work + isolated_light_weight_app_checkpoint_work + isolated_light_weight_app_wasted_work

#--------------------- Heavy Weight Application (Isolation) --------------------------------------#

heavy_weight_app_delta = round(BASE_DELTA,2)
heavy_weight_app_tau   = round(estimate_OCI(MTBF, heavy_weight_app_delta),2)

DELTA = heavy_weight_app_delta
TAU = OCI_STRETCH_FACTOR*heavy_weight_app_tau 

my_checkpoint_threshold = INFINITE
start_time = 0
end_time= start_time + INFINITE*(TAU + DELTA)

#cat("Isolation: Heavy Weight Application is running: delta: ", DELTA, "  tau: ", TAU, " Switch point: ", SWITCH_POINT, " End time: ", end_time, "\n")

isolated_heavy_weight_app_wasted_work <- wasted_work_overhead(start_time, my_checkpoint_threshold, AVG_LOST_WORK_FRACTION, TAU, DELTA)
isolated_heavy_weight_app_checkpoint_work <- io_overhead(start_time, my_checkpoint_threshold, TAU, DELTA)
isolated_heavy_weight_app_useful_work <- useful_work(start_time, my_checkpoint_threshold, TAU, DELTA)

isolated_heavy_weight_app_total_time = isolated_heavy_weight_app_useful_work + isolated_heavy_weight_app_checkpoint_work + isolated_heavy_weight_app_wasted_work

MAX_RUN_TIME = 2*MAX_RUN_TIME

#--------------------- Both Applications done (Isolation) --------------------------------------#

cat("\n---------------Isotation Results with OCI_STRETCH_FACTOR ----------------")
cat ("\nLight Weight App: Total Time: ", isolated_light_weight_app_total_time, 
	" Useful: ", isolated_light_weight_app_useful_work, 
	" Checkpoint: ", isolated_light_weight_app_checkpoint_work, 
	" Lost: ", isolated_light_weight_app_wasted_work)

cat ("\nHeavy Weight App: Total Time: ", isolated_heavy_weight_app_total_time, 
	" Useful: ", isolated_heavy_weight_app_useful_work, 
	" Checkpoint: ", isolated_heavy_weight_app_checkpoint_work, 
	" Lost: ", isolated_heavy_weight_app_wasted_work)

cat ("\nAll Combine Apps: Total Time: ", isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time, 
	" Useful: ", isolated_light_weight_app_useful_work + isolated_heavy_weight_app_useful_work, 
	" Checkpoint: ", isolated_light_weight_app_checkpoint_work + isolated_heavy_weight_app_checkpoint_work, 
	" Lost: ", isolated_light_weight_app_wasted_work + isolated_heavy_weight_app_wasted_work, "\n")

cat("\n---------------Isotation Results with OCI_STRETCH_FACTOR (*scaled*)----------------")
cat ("\nLight Weight App: Total Time: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*isolated_light_weight_app_total_time, 
	" Useful: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*isolated_light_weight_app_useful_work, 
	" Checkpoint: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*isolated_light_weight_app_checkpoint_work, 
	" Lost: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*isolated_light_weight_app_wasted_work)

cat ("\nHeavy Weight App: Total Time: ", isolated_heavy_weight_app_total_time, 
	" Useful: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*isolated_heavy_weight_app_useful_work, 
	" Checkpoint: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*isolated_heavy_weight_app_checkpoint_work, 
	" Lost: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*isolated_heavy_weight_app_wasted_work)

cat ("\nAll Combine Apps: Total Time: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time), 
	" Useful: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*(isolated_light_weight_app_useful_work + isolated_heavy_weight_app_useful_work), 
	" Checkpoint: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*(isolated_light_weight_app_checkpoint_work + isolated_heavy_weight_app_checkpoint_work), 
	" Lost: ", (MAX_RUN_TIME/(isolated_light_weight_app_total_time + isolated_heavy_weight_app_total_time))*(isolated_light_weight_app_wasted_work + isolated_heavy_weight_app_wasted_work), "\n")


cat("\n-----------------------------------------------")

#----------------------Both Applications Run Togther with Switching Enabled------------------------------------#


my_switch_seq <- seq(1, MAX_SWITCH_POINT, by = 1) 

for (i in my_switch_seq ){

SWITCH_POINT = i

#--------------------- Light Weight Application (Switching) --------------------------------------#

light_weight_app_delta = BASE_DELTA/DELTA_FACTOR
light_weight_app_tau  = round(estimate_OCI(MTBF, light_weight_app_delta),2)

DELTA = light_weight_app_delta
TAU = light_weight_app_tau 

low_end  = 0
high_end = SWITCH_POINT
my_checkpoint_threshold = high_end
start_time = low_end*(TAU + DELTA)
end_time= start_time + high_end*(TAU + DELTA)

#cat("Light Weight Application is running: delta: ", DELTA, " tau: ", TAU, " Switch point: ", SWITCH_POINT, " End time: ", end_time, "\n")

light_weight_app_wasted_work <- wasted_work_overhead(start_time, my_checkpoint_threshold, AVG_LOST_WORK_FRACTION, TAU, DELTA)
light_weight_app_checkpoint_work <- io_overhead(start_time, my_checkpoint_threshold, TAU, DELTA)
light_weight_app_useful_work <- useful_work(start_time, my_checkpoint_threshold, TAU, DELTA)

light_weight_app_total_time = light_weight_app_useful_work + light_weight_app_checkpoint_work + light_weight_app_wasted_work

#--------------------- Heavy Weight Application (Switching) --------------------------------------#

heavy_weight_app_delta = round(BASE_DELTA,2)
heavy_weight_app_tau   = round(estimate_OCI(MTBF, heavy_weight_app_delta),2)

DELTA = heavy_weight_app_delta
TAU = OCI_STRETCH_FACTOR*heavy_weight_app_tau 

low_end  = SWITCH_POINT
high_end = INFINITE
my_checkpoint_threshold = high_end
start_time = low_end*(light_weight_app_tau + light_weight_app_delta) # note why light weight app parameters are being used.
end_time= start_time + high_end*(TAU + DELTA)

#cat("Heavy Weight Application is running: delta: ", DELTA, "  tau: ", TAU, " Switch point: ", SWITCH_POINT, " End time: ", end_time, "\n")

heavy_weight_app_wasted_work <- wasted_work_overhead(start_time, my_checkpoint_threshold, AVG_LOST_WORK_FRACTION, TAU, DELTA)
heavy_weight_app_checkpoint_work <- io_overhead(start_time, my_checkpoint_threshold, TAU, DELTA)
heavy_weight_app_useful_work <- useful_work(start_time, my_checkpoint_threshold, TAU, DELTA)

heavy_weight_app_total_time = heavy_weight_app_useful_work + heavy_weight_app_checkpoint_work + heavy_weight_app_wasted_work

#--------------------- Both Applications done --------------------------------------#

cat("\n------------------Switching Results (with OCI_STRETCH_FACTOR): Switch Point ", i, "---------------------")
cat("\nSwitch Point ", i)
cat("\nLight Weight App: Total Time: ", round_me(light_weight_app_total_time), " Useful: ", round_me(light_weight_app_useful_work), " Checkpoint: ", round_me(light_weight_app_checkpoint_work), " Lost: ", round_me(light_weight_app_wasted_work))
cat ("\nHeavy Weight App: Total Time: ", round_me(heavy_weight_app_total_time), " Useful: ", round_me(heavy_weight_app_useful_work), " Checkpoint: ", round_me(heavy_weight_app_checkpoint_work), " Lost: ", round_me(heavy_weight_app_wasted_work))

cat ("\nAll Combine Apps: Total Time: ", round_me(light_weight_app_total_time + heavy_weight_app_total_time), 
	" Useful: ", round_me(light_weight_app_useful_work + heavy_weight_app_useful_work), 
	" Checkpoint: ", round_me(light_weight_app_checkpoint_work + heavy_weight_app_checkpoint_work), 
	" Lost: ", round_me(light_weight_app_wasted_work + heavy_weight_app_wasted_work), "\n")


cat("\nSwitch Point ", i, " (*scaled*)")
cat("\nLight Weight App: Total Time: ", (MAX_RUN_TIME/(light_weight_app_total_time + heavy_weight_app_total_time))*round_me(light_weight_app_total_time), " Useful: ", (MAX_RUN_TIME/(light_weight_app_total_time + heavy_weight_app_total_time))*round_me(light_weight_app_useful_work), " Checkpoint: ", (MAX_RUN_TIME/(light_weight_app_total_time + heavy_weight_app_total_time))*round_me(light_weight_app_checkpoint_work), " Lost: ", (MAX_RUN_TIME/(light_weight_app_total_time + heavy_weight_app_total_time))*round_me(light_weight_app_wasted_work))
cat ("\nHeavy Weight App: Total Time: ",(MAX_RUN_TIME/(light_weight_app_total_time + heavy_weight_app_total_time))*round_me(heavy_weight_app_total_time), " Useful: ", (MAX_RUN_TIME/(light_weight_app_total_time + heavy_weight_app_total_time))*round_me(heavy_weight_app_useful_work), " Checkpoint: ", (MAX_RUN_TIME/(light_weight_app_total_time + heavy_weight_app_total_time))*round_me(heavy_weight_app_checkpoint_work), " Lost: ", round_me(heavy_weight_app_wasted_work))

cat ("\nAll Combine Apps: Total Time: ", (MAX_RUN_TIME/(light_weight_app_total_time + heavy_weight_app_total_time))*round_me(light_weight_app_total_time + heavy_weight_app_total_time), 
	" Useful: ", (MAX_RUN_TIME/(light_weight_app_total_time + heavy_weight_app_total_time))*round_me(light_weight_app_useful_work + heavy_weight_app_useful_work), 
	" Checkpoint: ", (MAX_RUN_TIME/(light_weight_app_total_time + heavy_weight_app_total_time))*round_me(light_weight_app_checkpoint_work + heavy_weight_app_checkpoint_work), 
	" Lost: ", (MAX_RUN_TIME/(light_weight_app_total_time + heavy_weight_app_total_time))*round_me(light_weight_app_wasted_work + heavy_weight_app_wasted_work), "\n")

threshold = as.integer((isolated_heavy_weight_app_useful_work - heavy_weight_app_useful_work)*100/isolated_heavy_weight_app_useful_work)
cat("percent ", threshold, "\n")

###
#if(threshold>0) {
#	cat("Yes \n")
#	turning_point = i
#	break 
#}

}

#cat("Switch point ", turning_point, "\n")
####

#cat ("Fail prob. ", (MAX_RUN_TIME/MTBF)*failure_probability(start_time, end_time, LAMBDA, SHAPE))
#cat ("\n----------- Application (low_end, high_end) (", low_end, ",", high_end, ")---------------")
#cat ("\nMaxt Time:", MAX_RUN_TIME, " Total Time: ", total_time, " Useful: ", total_useful_work, " Checkpoint: ", total_checkpoint_work, " Lost: ", total_wasted_work)
#cat ("\n\n")

#cat ("\n ----------- Weibull (min max) (", LOW, ",", HIGH, ")---------------")
#cat ("\n Avg lost work fraction ", lost_work/total_work)
#cat ("\n Probability of Failure in this interval ", falls_in_this_period/MAX)
#cat ("\n Probability of Failure in this interval (theoretical)", (exp(-((MIN_PERIOD/t1_w)^t2_w)) - exp(-((MAX_PERIOD/t1_w)^t2_w))), "\n\n\n" )
