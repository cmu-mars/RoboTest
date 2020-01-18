# Common System Packages
import os
import sys
import time
import random
import logging
import threading
import subprocess
import datetime

import numpy as np
from numpy.linalg import norm # L2 norm

# HTTP server related Packages 
import requests
from flask import Flask, request, jsonify, make_response, redirect, url_for
import json
from werkzeug.serving import make_server
import traceback
from werkzeug.wsgi import ClosingIterator

# Local Packages
from test_spec import TestSpec, perturbation_types
from mapserver import MapServer

class AfterResponse:
    def __init__(self, app=None):
        self.callbacks = []
        if app:
            self.init_app(app)

    def __call__(self, callback):
        self.callbacks.append(callback)
        return callback

    def init_app(self, app):
        # install extension
        app.after_response = self

        # install middleware
        app.wsgi_app = AfterResponseMiddleware(app.wsgi_app, self)

    def flush(self):
        for fn in self.callbacks:
            try:
                fn()
            except Exception:
                traceback.print_exc()

class AfterResponseMiddleware:
    def __init__(self, application, after_response_ext):
        self.application = application
        self.after_response_ext = after_response_ext

    def __call__(self, environ, after_response):
        iterator = self.application(environ, after_response)
        try:
            return ClosingIterator(iterator, [self.after_response_ext.flush])
        except Exception:
            traceback.print_exc()
            return iterator

def usage():
    print("=================How To Run th_server.py================================")
    print("python3.6 th_server.py ta_url ta_port mission_map_file test_spec log_dir")
    print("========================================================================")



th_host = "0.0.0.0"
th_port = 8081

# Setup Flask APP and Logger

# Suppress the debug logs from urlib3
logging.getLogger("urllib3").setLevel(logging.INFO)
# Set up log level for TH
log_level_env = os.environ.get('TH_LOG_LEVEL').upper()
if log_level_env and (log_level_env == 'INFO'):
    logging.basicConfig(level=logging.INFO)
else:
    logging.basicConfig(level=logging.DEBUG)


app = Flask(__name__)
AfterResponse(app)
#   live            : TH send a request to start the mission
#   at-waypoint     : It impacts TH's perturbation requests since the robot reaches a target.
#   error           : TH should go to stop itself
#   done            : TH should go to stop itself
#   others          : no special handling is needed
ta_req_type = "other"
@app.after_response
def event_trigger_for_special_ta_requests():
    global ta_alive
    global cur_target_done
    global mission_done
    global ta_req_type
    logging.info(f"[After Response] ta_req_type is {ta_req_type}")

    # if works, add 'live' case
    if ta_req_type == "live":
        ta_alive.set()
    elif ta_req_type == "at-waypoint":
        cur_target_done.set()
    elif ta_req_type == "adapt-started":
        is_adapting.set()
        can_perturb.clear()
    elif ta_req_type == "adapt-done":
        is_adapting.clear()
        can_perturb.set()
    elif (ta_req_type == "error") or (ta_req_type == "done"):
        mission_done.set()
        last_target_done.set() # signal to stop battery observation
        cur_target_done.set() # notify the running perturbation to stop
        can_perturb.clear()

    ta_req_type = "other"


# [Setup logger]
def create_custom_logger(logger_name, log_filepath, log_level, enable_console=False):
    ## Create a custom logger
    logger = logging.getLogger(logger_name)

    ## Create handlers
    f_handler = logging.FileHandler(log_filepath)
    f_handler.setLevel(log_level)
    ## Create formatters and add it to handlers
    f_format = logging.Formatter('%(name)s\t| [%(levelname)s] [%(asctime)s] %(message)s ')
    f_handler.setFormatter(f_format)
    ## Add handlers to the logger
    logger.addHandler(f_handler)

    if enable_console:
        ## Create handlers
        c_handler = logging.StreamHandler()
        c_handler.setLevel(log_level)
        ## Create formatters and add it to handlers
        c_format = logging.Formatter('[%(asctime)s][%(name)s][%(levelname)s] %(message)s ')
        c_handler.setFormatter(c_format)
        ## Add handlers to the logger
        logger.addHandler(c_handler)

    return logger

# Parse Input Parameters
if len(sys.argv) != 6:
    logging.error(f"Failed to parse input paramters to the TH server. The number of input paramters is not 6. Input parameters: {sys.argv}")
    usage()
    exit(1)

ta_url          = sys.argv[1]
ta_port         = sys.argv[2]
ta_url          = ta_url+":"+ta_port

test_map_fp     = sys.argv[3]
test_spec_fp    = sys.argv[4]
log_dir         = sys.argv[5]

if not log_dir.endswith("/"):
    log_dir = log_dir + "/"

# Parse Test Spec
test_map = MapServer(test_map_fp)
test_spec = None
try:
    with open(test_spec_fp) as fp:
        test_spec = json.load(fp)
    case_level = test_spec['test_configuration']['level']
    start_loc = test_spec['test_configuration']['start-loc']
    targets = test_spec["test_configuration"]["target-locs"]
    num_targets = len(targets)
    power_model = test_spec['test_configuration']['power-model']
    perturbation_seqs = None # used by Case B, C and D
    if case_level != 'a':
         perturbation_seqs = test_spec["perturbation"]["perturbSeqs"]

except Exception as e:
    err_msg = f"Failed to load test spec at {test_spec_fp}. Error is:\n{e}"
    raise Exception(err_msg)

# Store the mission result
mission_result = {}
mission_result['test_configuration'] = test_spec['test_configuration']
mission_result['mission_start'] = {'wall_clock': 0, 'sim_time': 0}
mission_result['mission_done'] = {'wall_clock': 0, 'sim_time': 0}
mission_result['num_targets_tried'] = 0
mission_result['num_targets_reached'] = 0
if case_level != 'a':
    mission_result['perturbation_stat'] = {}
    mission_result['perturbation_stat']['num_perturbations_tried'] = 0
    mission_result['perturbation_stat']['num_successful_perturbations'] = 0
    mission_result['perturbation_stat']['num_successful_easy_perturbations'] = 0
    mission_result['perturbation_stat']['num_successful_medium_perturbations'] = 0
    mission_result['perturbation_stat']['num_successful_hard_perturbations'] = 0

for i in range(1, 1+num_targets):
    mission_result[f"Target{i}"] = {
            'is_tried': False,
            'is_reached': False,
            'robot_loc': {'x':0, 'y':0},
            'plan': [], # the final plan of the robot for this target
            }
    if case_level != 'a':
        mission_result[f"Target{i}"]['num_perturbations_tried'] = 0
        mission_result[f"Target{i}"]['num_successful_perturbations'] = 0
        mission_result[f"Target{i}"]['perturbations'] = []
        for p in test_spec["perturbation"]["perturbSeqs"][f"Target{i}"]:
            p["status"] = ""
            mission_result[f"Target{i}"]["perturbations"].append(p)

# Obtain test_ID and S3 bucket and create logger
test_ID = os.environ.get('TEST_ID')
if (not test_ID) or (len(test_ID) == 0):
    err_msg = "Test ID undefined; Stop the test"
    raise Exception(err_msg)
th_log_filename = log_dir + test_ID + ".log"
logger_th_server = create_custom_logger("CP1_TH", th_log_filename, logging.DEBUG)
logger_th_server.info('{:=^60}'.format(test_ID))
logger_th_server.info(f"Logging to {th_log_filename}")
logger_th_server.info("[test_spec]: test ID {}\n{}".format(
    test_ID,
    json.dumps(test_spec, indent=4)))
logger_th_server.info(f"[Log Level] {log_level_env}")

s3_bucket_url = os.environ.get('S3_BUCKET_CP1_PATH')
if (not s3_bucket_url) or (len(s3_bucket_url) == 0):
    err_msg = "S3 bucket URL undefined; cannot sequester logs"
    logger_th_server.error(err_msg, exc_info=True)
    raise Exception(err_msg)
else:
    logger_th_server.info(f"S3 bucket URL is {s3_bucket_url}")


# In the current test design, at most one obstacle will be exist in the map at a time.
# It is used to remove the placed obstacle when a target is reached.
placedObstacleID = None

# cur_target_ID is used as one condition to stop the monitoring of robot battery in time.
# Otherwise, battery checking keeps sending /observe request to the TA,
# while the TA is shutting down. This makes the TH consider some error is
# happening in the TA and thus go to shut down the TH before the TA sends
# the /done message. cur_target_ID is updated in run_mission()
cur_target_ID = 0

# Threshold of Battery level that can be set in perturbation
battery_set_unit = 3255 # 1% of battery_capacity
battery_capacity = 32559 
battery_set_threshold_ratio = 0.1
battery_set_threshold = int(battery_capacity * battery_set_threshold_ratio)

# The plan towards the current target.
# TA will send it in /live, /at-waypoint and all status messages when TA is alive.
# For case b: the plan carried in /live and /at-waypoint messages will be used
# For case c and d: the plan carried in /live, /at-waypoint and /status (adapt-done) messages will be used
cur_mov_plan = {'plan':[], 'sentByTAStatus': ""}

# Events
ta_alive = threading.Event() # trigger the mission start request /start from the TH to the TA
# When perturbation is allowed:
# case 'a': no perturbation
# case 'b': allowed as long as TA is alive and the robot is not charging
# case 'c': allowed when TA is alive and not in adaptation phase
# case 'd': the same as case 'c'
can_perturb = threading.Event() # guard TH's perturbation requests away from the adaptations in TA
stop_th = threading.Event() # trigger the thread to shutting the TH
mission_done = threading.Event() # trigger the event stop_th
cur_target_done = threading.Event() # guard each task's perturbations
is_adapting = threading.Event()
last_target_done = threading.Event()
robot_status_ready = threading.Event()
robot_status_use = threading.Event()

# Before the mission starts, robot does not aim for any target. So, set cur_target_done and mission_done.
cur_target_done.set()
mission_done.set()
is_adapting.clear()
last_target_done.clear()
robot_status_ready.clear()
robot_status_use.clear()

# Used to store the robot status returned from /observe request 
robot_status = {'sim-time': 0, 'plan': [], 'y': 0, 'x': 0, 'status': '', 'charge': 0}

# Send /observe to the TA every <time_interval_observation> seconds
time_interval_observation = 1

# Used to throttle the messages that indicate the robot is too close
# to a waypoint during the computation of an obstacle's location
#can_perturb_check_counter       = 0
#robot_dist_check_counter        = 0
#robot_observation_counter       = 0
#robot_status_use_check_counter  = 0
#not_charging_check_counter      = 0


# [Routes - Process Requests Sent From TA]
@app.route('/index', methods=['GET'])
def TH_alive():
    return make_response("TH server is running!\n", 200)

@app.route('/ready', methods=['POST'])
def TA_is_ready():
    '''
        Listen to the '/ready' requst from TA and then send mission to TA
    '''
    global logger_th_server

    logger_th_server.info("received /ready from TA.") # should display 'bar'
    try:
        data = test_spec["test_configuration"] 
        return make_response(jsonify(data), 200)
    except Exception as e:
        exception_msg = "TH encountered an error producing configuration data: "+str(e)
        logger_th_server.error(exception_msg, exc_info=True)
        ta_req_type == "error"
        return make_response(exception_msg, 400)


# [CP1 Status sent by TA]
# one of the possible status codes * learning-started - the learning phase has started * learning-done - the learning phase has been * adapt-started - the SUT has started adapting and cannot be perturbed * adapt-done - the SUT has finished adapting * charging-started - the turtlebot is currently charging * charging-done - the turtlebot has stopped charging * parsing-error - one or more of the function descriptions failed to parse * learning-error - an error was encountered in learning one or more of the hidden functions * other-error - an error was encountered that is not covered by the other error codees
allowed_values = ["learning-started", "learning-done", "adapt-started", "adapt-done", "charging-started", "charging-done", "parsing-error", "learning-error", "other-error", "RAINBOW_READY"    , "MISSION_SUCCEEDED", "MISSION_FAILED", "ADAPTING", "ADAPTED", "ADAPTED_FAILED"]

@app.route('/status', methods=['POST'])
def ta_status():
    '''
        Acknowledge TA status
    '''
    global logger_th_server
    global ta_alive
    global cur_target_done
    global ta_req_type

    global cur_mov_plan
    global num_targets
    global last_target_done
    global mission_result
    global targets
    global case_level

    try:
        status_content = request.json
        status = status_content['status']
 
        if status in ["live", "at-waypoint", "adapt-done"]:
            # "live"        : the TA is alive
            # "at-waypoint" : reach to the current target location
            # "adapt-done"  : adaptation is done. (case c and d)
            ta_req_type = status

            # when the current task is done.
            if (status == "at-waypoint"):
                # Log into mission result if the current target is actually reached.
                logger_th_server.debug(f"[at-waypoint] cur_target_ID: {cur_target_ID}. num_targets: {num_targets}.")

                x = status_content['x']
                y = status_content['y']
                robot_loc = np.array([x, y])

                cur_target_waypoint_name = cur_mov_plan["plan"][-1] #targets[cur_target_ID-1]
                target_loc_dict = test_map.waypoint_to_coords(cur_target_waypoint_name)
                target_loc = np.array([target_loc_dict["x"], target_loc_dict["y"]])

                distance_robot_to_target = norm(robot_loc-target_loc)
                logger_th_server.info(f"[at-waypoint] distance between robot ({robot_loc}) and the current target {cur_target_waypoint_name} ({target_loc}) : {distance_robot_to_target}.")
                if distance_robot_to_target < obstacle_target_safe_distance_threshold:
                    mission_result[f"Target{cur_target_ID}"]['is_reached'] = True
                    mission_result['num_targets_reached'] += 1

                    mission_result[f"Target{cur_target_ID}"]['robot_loc']['x'] = x
                    mission_result[f"Target{cur_target_ID}"]['robot_loc']['y'] = y

                    mission_result[f"Target{cur_target_ID}"]['plan'] = cur_mov_plan["plan"]

                if (cur_target_ID == num_targets):
                    last_target_done.set()
                    logger_th_server.debug(f"[at-waypoint] last_target_done is set. Battery monitoring should be stopped.")

            # A new plan is set by the TA.
            logger_th_server.debug(f"[{status}] [old plan - {cur_mov_plan}")
            cur_mov_plan["plan"] = status_content['plan']
            cur_mov_plan["sentByTAStatus"] = status
            logger_th_server.debug(f"[{status}] [new plan - {cur_mov_plan}")

        elif status == "adapt-started":
            ta_req_type = status
        else:
            ta_req_type = "other"

        logger_th_server.info(f"[TA Status Message] {status_content}")

        ack_msg = f"[CP1_TH ACK - TA Status Message] {status}."
        return make_response(ack_msg, 200)
    except Exception as e:
        exception_msg = "[TA Status] TH encountered an error with the TA status message.\nTA status message: {}.\nTH error: {}".format(request.json, str(e))
        logger_th_server.error(exception_msg, exc_info=True)
        ta_req_type == "error"
        return make_response(exception_msg, 400)

@app.route('/error', methods=['POST'])
def ta_non_recoverable_error():
    global logger_th_server
    global ta_req_type
    global robot_status

    # save the time info when mission is done.
    time_stamp=time.strftime("%Y-%m-%d_%H-%M-%S", time.gmtime())
    dt = datetime.datetime.strptime(time_stamp, "%Y-%m-%d_%H-%M-%S")
    time_stamp_ms = int(time.mktime(dt.timetuple()) * 1000) # millium seconds

    mission_result['mission_done']['wall_clock']   = time_stamp_ms
    mission_result['mission_done']['sim_time']     = robot_status['sim-time']

    error_content = request.json
    error_type = error_content['error']
    error_msg = error_content['message']
    logger_th_server.error(f"Error_Type: {error_type}, error_msg: {error_msg}", exc_info=True)
    ack_msg = f"TH has stop the test due to the reported non-recoverable error {error_type}: {error_msg}"

    ta_req_type = "error"

    return make_response(ack_msg, 200)


@app.route('/done', methods=['POST'])
def test_done():
    '''
        Process '/done' request from TA, which indicates the test is done. 
    '''
    global logger_th_server
    global ta_req_type
    global num_targets

    response = None
    try:
        content = request.json
        mission_outcome = content['outcome']
        tasks_finished = content['tasks-finished']
        num_tasks_finished = len(tasks_finished)

        # save the time info when mission is done.
        time_stamp=time.strftime("%Y-%m-%d_%H-%M-%S", time.gmtime())
        dt = datetime.datetime.strptime(time_stamp, "%Y-%m-%d_%H-%M-%S")
        time_stamp_ms = int(time.mktime(dt.timetuple()) * 1000) # millium seconds

        mission_result['mission_done']['wall_clock']   = time_stamp_ms
        mission_result['mission_done']['sim_time']     = content['sim-time']

        mission_msg = ""
        if mission_outcome == "at-goal":
            if num_tasks_finished == num_targets:
                mission_msg = f"[Test Done: Mission Completed] {num_tasks_finished} tasks finished:\n"
            else:
                mission_msg = f"[Test Done: Mission Incompleted] {num_tasks_finished} tasks finished:\n"
        elif mission_outcome == "out-of-battery":
            mission_msg = f"[Test Done: Abrupt - Low Energy] {num_tasks_finished} tasks finished:\n"
        else: # unknown mission outcome message
            raise ValueError(f"Unknown Mission Outcome Message: {mission_outcome}.\nFull request content: {content}")

        for task_status in tasks_finished:
            mission_msg += f"\tReached the target location {task_status['name']} ({task_status['x']}, {task_status['y']}) at the sim-time, {task_status['sim-time']}\n"

        mission_msg += f"Final robot's status: charge = {content['charge']} mAh,  ({content['x']}, {content['y']}) at the sim-time, {content['sim-time']}\n"

        logger_th_server.info(mission_msg)

        ack_msg = f"[CP1_TH] ACK - Test Done."
        response = make_response(ack_msg, 200)
    except Exception as e:
        exception_msg = "TH encountered an error at the completion of the mission: "+str(e)
        logger_th_server.error(exception_msg, exc_info=True)
        ta_req_type == "error"
        response = make_response(exception_msg, 400)

    ta_req_type = "done"

    return response


# [Requests Sent To TA]
def observe_req(src, endpoint, logger, is_periodical=False):

    req_name = "/observe"
    if not is_periodical:
        logger.info(f"#{src}# Sending {req_name} request to TA: {endpoint}")
    try:
        response = requests.get(
                url = endpoint,
                headers = {"Accept": "application/json"})
    except Exception:
        logger.error("#{src}# Fatal error when sending {req_name} request", exc_info=True)
        return False

    status_code = response.status_code
    if status_code == 200:
        robot_status = response.json()
        # If the /observe request is issued in an adhoc situation,
        # dump the status directly
        if not is_periodical:
            logger.info("[Robot Status] "+str(robot_status))
        return robot_status
    else:
        if status_code == 400:
            logger.error(response.json(), exc_info=True)
        else: 
            logger.error(f"#{src}# Unknown response code of {req_name} request: {status_code}", exc_info=True)
        return False

def place_obstacle_req(src, endpoint, logger, obstacle_cood):
    '''
        obstacle_cood: a dict, {'x': x_cood, 'y': y_cood}
    '''
    global placedObstacleID
    global cur_target_done
    global can_perturb

    if placedObstacleID != None:
        logger.error(f"#{src}# The TH tries to place an obstacle while the obstacle, {placedObstacleID}, already exists on the map. Note: at most one obstacle should be on the map to avoid trapping the robto and also remove invalid (ineffective) obstacles.", exc_info=True)
        return False

    req_name = "/perturb/place-obstacle"
    logger.info(f"#{src}# Sending {req_name} to TA: {endpoint}")
    try:
        response = requests.post(
                url = endpoint,
                headers = {
                    "Accept": "application/json",
                    'Content-Type': 'application/json'},
                json=obstacle_cood)
    except Exception:
        logger.error("#{src}# Fatal error when sending {req_name} request", exc_info=True)
        return False

    status_code = response.status_code
    if status_code == 200:
        data = response.json()
        placedObstacleID = data["obstacleid"]
        sim_time = data['sim-time']
        logger.info(f"[Perturb - Place Obstacle] {placedObstacleID} is placed at the location {obstacle_cood} at sim-time {sim_time}")
        return True
    else:
        if status_code == 400:
            logger.error(response.json(), exc_info=True)
        else: 
            logger.error(f"#{src}# Unknown response code of {req_name} request: {status_code}", exc_info=True)
        return False

def remove_obstacle_req(src, endpoint, logger, obstacle_id):

    req_name= "/perturb/remove-obstacle "
    logger.info(f"#{src}#Sending {req_name} request to TA: {endpoint}")
    try:
        response = requests.post(
                url = endpoint,
                headers = {
                    "Accept": "application/json",
                    'Content-Type': 'application/json'},
                json={"obstacleid":obstacle_id})
    except Exception:
        logger.error("#{src}# Fatal error when sending {req_name} request", exc_info=True)
        return False

    status_code = response.status_code
    if status_code == 200:
        data = response.json()
        sim_time = data['sim-time']
        logger.info(f"[Perturb - Remove Obstacle] {obstacle_id} is removed at sim-time {sim_time}")
        return True
    else:
        if status_code == 400:
            logger.error(response.json(), exc_info=True)
        else: 
            logger.error(f"#{src}# Unknown response code of {req_name} request: {status_code}", exc_info=True)
        return False

def set_battery_req(src, endpoint, logger, charge):

    req_name = "/perturb/battery"
    logger.info(f"#{src}# Sending {req_name} request to TA: {endpoint}")
    try:
        response = requests.post(
                url = endpoint,
                headers = {
                    "Accept": "application/json",
                    'Content-Type': 'application/json'},
                json={"charge":charge})
    except Exception:
        logger.error("#{src}# Fatal error when sending {req_name} request", exc_info=True)
        return False

    status_code = response.status_code
    if status_code == 200:
        data = response.json()
        sim_time = data['sim-time']
        logger.info(f"[Perturb - Set Battery] Battery charge is set to {charge} at sim-time {sim_time}")
        return True
    else:
        if status_code == 400:
            logger.error(response.json(), exc_info=True)
        else: 
            logger.error(f"#{src}# Unknown response code of {req_name} request: {status_code}", exc_info=True)
        return False


def start_mission_req(src, endpoint, logger):
    global can_perturb

    req_name = "/start"
    logger.info(f"#{src}# Sending {req_name} request to TA: {endpoint}")
    try:
        time.sleep(3)
        response = requests.post(
                url = endpoint,
                headers = {"Accept": "application/json"})
    except Exception:
        logger.error(f"#{src}# Fatal error when sending {req_name} request", exc_info=True)
        return False

    status_code = response.status_code
    if status_code == 200 or status_code == 204: # 204 - response body has no content
        logger.info(f"Mission is started in TA")
        can_perturb.set()
        return True
    else:
        if status_code == 400:
            logger.error(response.json(), exc_info=True)
        else: 
            logger.error(f"#{src}# Unknown response code of {req_name} request: {status_code}", exc_info=True)
        return False

ta_endpoints = {
        "start_mission": ta_url+"/start",
        "robot_status": ta_url+"/observe",
        "place_obstacle": ta_url+"/perturb/place-obstacle",
        "remove_obstacle": ta_url+"/perturb/remove-obstacle",
        "set_battery": ta_url+"/perturb/battery"}


# [Utility Functions]
def do_perturbation(perturbation, logger):
    '''
        Assumption: when calling do_perturbation, can_perturb is set.
    '''

    perturbation_type = perturbation['type']
    if perturbation_type in perturbation_types["obstacle"]: 
        return obstacle_perturbation(perturbation, logger)
    elif perturbation_type in perturbation_types["battery"]:
        return battery_perturbation(perturbation, logger)
    else:
        logger.error(f"[Do Perturbation] Unsupported perturbation type: {perturbation_type}", exc_info=True)
        return False

def battery_perturbation(perturbation, logger):
    global battery_set_threshold
    global ta_endpoints

    global can_perturb
    global mission_done
    global cur_target_done

    global robot_status_ready
    global robot_status_use
    global robot_status
    global time_interval_observation

    p_type = perturbation['type']
    ratio  = perturbation['ratio']
    
    perturbation_result = False

    can_perturb_check_counter = 0
    robot_status_ready_check_counter  = 0

    while not perturbation_result:

        if mission_done.is_set():
            logger.error(f"[Battery Perturbation] mission_done is set when observing the robot's location. ({p_type}, {ratio}).", exc_info=True)
            break
        elif cur_target_done.is_set():
            logger.error(f"[Battery Perturbation] cur_target_done is set when observing the robot's location. ({p_type}, {ratio}).", exc_info=True)
            break
        elif not can_perturb.is_set():
            if (can_perturb_check_counter % 10) == 0:
                logger.info(f"[Battery Perturbation] Charging or adaptation happens when observing the robot's location. ({p_type}, {ratio}).")
            can_perturb_check_counter += 1
            robot_status_use.clear()
            time.sleep(time_interval_observation)
            continue

        logger.debug(f"[Battery Perturbation] Can perturb now.")

        logger.debug(f"[Battery Perturbation] robot_status: ready - {robot_status_ready.is_set()}, use - {robot_status_use.is_set()}")
        if not robot_status_ready.is_set():
            if (robot_status_ready_check_counter % 10) == 0:
                logger.info(f"[Battery Perturbation] robot_status is not ready for use.")
            robot_status_ready_check_counter += 1
            time.sleep(time_interval_observation)
            continue
        logger.debug(f"[Battery Perturbation] robot_status is ready.")

        # use robot status
        robot_status_use.set()

        if robot_status != False:
            x = robot_status['x']
            y = robot_status['y']
            battery = robot_status['battery']
            sim_time = robot_status['sim-time']

            if battery > battery_set_threshold:
                new_battery = battery - ratio*(battery-battery_set_threshold)
                if mission_done.is_set():
                    logger.error(f"[Battery Perturbation] mission_done is set when doing battery perturbation, ({p_type}, {ratio}).", exc_info=True)
                    break
                elif cur_target_done.is_set():
                    logger.error(f"[Battery Perturbation] cur_target_done is set when doing battery perturbation, ({p_type}, {ratio}).", exc_info=True)
                    break
                elif not can_perturb.is_set():
                    if (can_perturb_check_counter % 10) == 0:
                        logger.info(f"[Battery Perturbation] Charging or adaptation happens when doing battery perturbation, ({p_type}, {ratio}), at the sim-time, {sim_time}, and location ({x}, {y}). Resume the perturbation until the adaptation is done.")
                    can_perturb_check_counter += 1
                    robot_status_use.clear()
                    time.sleep(time_interval_observation)
                    continue
                else:
                    logger.info(f"[Battery Perturbation] ({p_type}, {ratio}) starts to setting battery level from {battery} to {new_battery}.")
                    battery_set_result = set_battery_req("battery_perturbation", ta_endpoints['set_battery'], logger, new_battery) 
                    if battery_set_result == False:
                        logger.error(f"[Battery Perturbation] ({p_type}, {ratio}) fails", exc_info=True)
                        break
                    else:
                        logger.info(f"[Battery Perturbation] ({p_type}, {ratio}) succeeds")
                        perturbation_result = True
            else:
                logger.error(f"[Battery Perturbation] fail because the robot's battery level, {battery}, is <= the threshold, {battery_set_threshold}.", exc_info=True)
                break

        else: # perturbation fails because of the failure of /observe request to the TA
            logger.error(f"[Battery Perturbation] fail because /observe request fails.", exc_info=True)
            break

        robot_status_use.clear()
        
    return perturbation_result # The battery perturbation is made successfully

# In cp1_controller, robotcontrol/bot_controller.py considers robot is close
# enough to a target waypoint if their distance is smaller than 2.
# Source:   https://github.com/cmu-mars/cp1_controllers/blob/master/robotcontrol/bot_controller.py
#
# line 27   distance_threshold = 2
# line 294  elif d <= distance_threshold and not success:
#               rospy.logwarn(
#                   "Apparently the robot could accomplish the task but ig_server reported differently!")
#               start = target
# line 298      success = True
#
# So, place the obstacle at least 2m and 3m away from the target and the robot respectively
obstacle_target_safe_distance_threshold = 2
obstacle_robot_safe_distance_threshold = 3

# Used when determining which segment the robot locates.
# When the distance between the robot and a segment is smaller
# than the threshold, consider the robot is in the segment.
to_seg_dist_threshold = 0.5

# the difference threshold for either x-coordinates or y-coordianates of two endpoints of a segment in the map
seg_same_coords_threshold = 1

l1_coord = np.array([test_map.waypoint_to_coords("l1")["x"], test_map.waypoint_to_coords("l1")["y"]])
l2_coord = np.array([test_map.waypoint_to_coords("l2")["x"], test_map.waypoint_to_coords("l2")["y"]])
l7_coord = np.array([test_map.waypoint_to_coords("l7")["x"], test_map.waypoint_to_coords("l7")["y"]])
l8_coord = np.array([test_map.waypoint_to_coords("l8")["x"], test_map.waypoint_to_coords("l8")["y"]])

def point_to_line_dist(p3, p1, p2):
    '''
        calculate the distance between point p3 and the line
        represented by the points, p1 and p2.
        p1, p2 and p3 are 1D numpy array, (x, y)
    '''
    return norm(np.cross(p2-p1, p1-p3))/norm(p2-p1)


def robot_in_horizontal_seg(robot_coord, w1_coord, w2_coord):
    global to_seg_dist_threshold
    max_x = max(w1_coord[0], w2_coord[0])
    min_x = min(w1_coord[0], w2_coord[0])
    dist = point_to_line_dist(robot_coord, w1_coord, w2_coord) 

    logger_th_server.debug(f"[Horizontal Segment Location] dist {dist}, p1 {w1_coord}, p2 {w2_coord}, robot loc {robot_coord}")
    if dist  < to_seg_dist_threshold:
        if robot_coord[0] >= min_x and robot_coord[0] <= max_x:
            return True
    return False

def robot_in_vectical_seg(robot_coord, w1_coord, w2_coord):
    global to_seg_dist_threshold
    max_y = max(w1_coord[1], w2_coord[1])
    min_y = min(w1_coord[1], w2_coord[1])
    dist = point_to_line_dist(robot_coord, w1_coord, w2_coord) 

    logger_th_server.debug(f"[Vertical Segment Location] dist {dist}, p1 {w1_coord}, p2 {w2_coord}, robot loc {robot_coord}")
    if dist  < to_seg_dist_threshold:
        if robot_coord[1] >= min_y and robot_coord[1] <= max_y:
            return True
    return False


def two_points_are_equal(p1, p2):
    return (p1[0]==p2[0]) and (p1[1]==p2[1])

def compute_coord_in_line(p1, p2, d13, d12):
    '''
    # point 3 is in the segment of point 1 and point 2
    '''
    p3_x = p1[0] + (p2[0] - p1[0]) * d13 / d12
    p3_y = p1[1] + (p2[1] - p1[1]) * d13 / d12

    return p3_x, p3_y

def compute_obstacle_location(x, y, ratio, mov_plan):
    global test_map
    global to_seg_dist_threshold
    global obstacle_target_safe_distance_threshold
    global obstacle_robot_safe_distance_threshold


    
    plan = mov_plan["plan"]
    sent_by_TA_status = mov_plan["sentByTAStatus"]
    coords = []

    for waypoint in plan:
        coord_dict = test_map.waypoint_to_coords(waypoint)
        coords.append(np.array([coord_dict["x"], coord_dict["y"]]))
    robot_coord = np.array([x, y])

    # Determine which segment the robot locates
    total_segments = len(plan)-1

    # Determine where the obstacle should be placed
    ## compute the distance from the obstacle to the robot
    cur_segment_distances = [] # the first one is the distance between the robot and the current heading waypoint

    logger_th_server.debug(f"[Compute Obstacle Loc] plan: {plan}")

    # if the robot is in either segment l1-l2 (moving to l2) or l7-l8 (moving to l7),
    # the distance from the robot to the its current heading waypoint
    # (l2 or l7) is not considered in the obstacle placement.
    logger_th_server.debug(f"[Compute Obstacle Loc] Check if the robot {robot_coord} is in either l1-l2 or l7-l8 segment.")
    if (robot_in_horizontal_seg(robot_coord, l1_coord, l2_coord) or robot_in_horizontal_seg(robot_coord, l7_coord, l8_coord)):
        logger_th_server.debug(f"[Compute Obstacle Loc] The robot {robot_coord} is either moving from l1->l2 or l7->l8.")

        robot_coord = coords[0]
        robot_segment_num = 1

        for segment_ID in range(robot_segment_num, total_segments+1):
                key1 = plan[segment_ID-1]+"-"+plan[segment_ID]
                key2 = plan[segment_ID]+"-"+plan[segment_ID-1]
                key = None       
                if key1 in test_map.segment_distances:
                    key = key1
                elif key2 in test_map.segment_distances:
                    key = key2
                else:
                    raise ValueError(f"[Compute Obstacle Loc] The segment, {key1}, indicated in the current plan, {plan}, is not the test map.")
                cur_segment_distances.append(test_map.segment_distances[key])

    else:
        logger_th_server.debug(f"[Compute Obstacle Loc] The robot {robot_coord} locates in neither l1-l2 nor l7-l8 segment.")
        if sent_by_TA_status == "adapt-done":
            robot_segment_num = 0 # represent the segment from the robot location to the first waypoint in the new plan
        else:
            # live or at-waypoint status: assume the length of the plan >= 2
            robot_segment_num = 1 # The segment number that the robot currently locates
            while robot_segment_num <= total_segments:
                if abs(coords[robot_segment_num-1][1] - coords[robot_segment_num][1]) < seg_same_coords_threshold:
                    if robot_in_horizontal_seg(robot_coord, coords[robot_segment_num-1], coords[robot_segment_num]):
                        break
                elif abs(coords[robot_segment_num-1][0] - coords[robot_segment_num][0]) < seg_same_coords_threshold:
                    if robot_in_vectical_seg(robot_coord, coords[robot_segment_num-1], coords[robot_segment_num]):
                        break

                robot_segment_num += 1


            if robot_segment_num > total_segments:
                raise ValueError(f"[Compute Obstacle Loc] The robot is not in any segment: the distance from the robot to any segment is larger than {to_seg_dist_threshold}.")

        logger_th_server.debug(f"[Compute Obstacle Loc] robot_segment_num : {robot_segment_num}") 

        cur_segment_distances.append(norm(robot_coord - coords[robot_segment_num]))

        for segment_ID in range(robot_segment_num+1, total_segments+1):
            key1 = plan[segment_ID-1]+"-"+plan[segment_ID]
            key2 = plan[segment_ID]+"-"+plan[segment_ID-1]
            key = None       
            if key1 in test_map.segment_distances:
                key = key1
            elif key2 in test_map.segment_distances:
                key = key2
            else:
                raise ValueError(f"[Compute Obstacle Loc] The segment, {key1}, indicated in the current plan, {plan}, is not the test map.")
            cur_segment_distances.append(test_map.segment_distances[key])

    distance_robot_to_current_target = 0 
    for dist in cur_segment_distances:
        distance_robot_to_current_target += dist

    if distance_robot_to_current_target < (obstacle_robot_safe_distance_threshold+obstacle_target_safe_distance_threshold):
        raise ValueError(f"[Compute Obstacle Loc] The distance from the robot {robot_coord} to the current target ({plan[-1]}:{coords[-1]}) is {distance_robot_to_current_target} (<{obstacle_robot_safe_distance_threshold+obstacle_target_safe_distance_threshold}) that is too close to place an obstacle in-between.")

    distance_obstacle_to_robot = distance_robot_to_current_target * ratio
    if distance_obstacle_to_robot < obstacle_robot_safe_distance_threshold:
        distance_obstacle_to_robot = obstacle_robot_safe_distance_threshold

    # the left point might be the robot or a waypoint
    distance_obstacle_to_left_point = distance_obstacle_to_robot
    # Calculate the coordinates of the obstacles
    ob_x, ob_y = 0, 0
    obstacle_segment_num = robot_segment_num
    for d in cur_segment_distances:
        if distance_obstacle_to_left_point > d:
            distance_obstacle_to_left_point -= d
            obstacle_segment_num += 1

    # The starting and ending points of the segment
    # for computing the coordinates of the obstacle
    if obstacle_segment_num == robot_segment_num:
        starting_point_coord = robot_coord
    else:
        starting_point_coord = coords[obstacle_segment_num-1]
    ending_point_coord = coords[obstacle_segment_num]

    dist_start_to_end = norm(starting_point_coord - ending_point_coord)

    # Get the safe starting and ending points by moving the original
    # starting and ending points <wapoint_safe_radius> towards to the obstacle
    safe_start_x, safe_start_y = compute_coord_in_line(
        starting_point_coord,
        ending_point_coord,
        obstacle_robot_safe_distance_threshold,
        dist_start_to_end)
    safe_start_point =  np.array([safe_start_x, safe_start_y])

    distance_obstacle_to_left_point  -= obstacle_robot_safe_distance_threshold 

    # the ending point is the target
    if plan[-1] == plan[obstacle_segment_num]:
        if dist_start_to_end < (obstacle_robot_safe_distance_threshold+obstacle_target_safe_distance_threshold):
            raise ValueError(f"[Compute Obstacle Loc] The coming waypoint is the target, while the length of the segment where the obstacle will be placed is {dist_star_to_end} (<{obstacle_robot_safe_distance_threshold+obstacle_target_safe_distance_threshold}) that is too close to place an obstacle in-between.")
        safe_end_x, safe_end_y = compute_coord_in_line(
            starting_point_coord,
            ending_point_coord,
            dist_start_to_end - obstacle_target_safe_distance_threshold,
            dist_start_to_end)
        safe_end_point =  np.array([safe_end_x, safe_end_y])
        dist_start_to_end -= (obstacle_robot_safe_distance_threshold+obstacle_target_safe_distance_threshold)
    else:
        if dist_start_to_end < obstacle_robot_safe_distance_threshold:
            raise ValueError(f"[Compute Obstacle Loc] The length of the segment where the obstacle will be placed is {dist_start_to_end} (<{obstacle_robot_safe_distance_threshold}) that is too close such that the robot will get stuck if the obstacle is placed on the segment.")
        safe_end_point = ending_point_coord
        dist_start_to_end -= obstacle_robot_safe_distance_threshold


    if distance_obstacle_to_left_point < 0:
        logger_th_server.info(f"[Compute Obstacle Loc] The distance between the intended obstacle and the robot {robot_coord} is smaller than the predefined safe distance threshold, {obstacle_robot_safe_distance_threshold}. Set the distance to be {obstacle_robot_safe_distance_threshold}.")
        distance_obstacle_to_left_point = 0
    elif distance_obstacle_to_left_point > dist_start_to_end:
        logger_th_server.info(f"[Compute Obstacle Loc] The distance between the intended obstacle and the target {coords[obstacle_segment_num]} is smaller than the predefined safe distance threshold, {obstacle_target_safe_distance_threshold}. Set the distance to be {obstacle_target_safe_distance_threshold}.")
        distance_obstacle_to_left_point = dist_start_to_end

    logger_th_server.debug(f"[Compute Obstacle Loc] obstacle_segment_num: {obstacle_segment_num}")
    logger_th_server.debug(f"[Compute Obstacle Loc] ending_point_coord: {ending_point_coord}")
    logger_th_server.debug(f"[Compute Obstacle Loc] starting_point_coord: {starting_point_coord}")

    ob_x, ob_y = compute_coord_in_line(
        safe_start_point,
        safe_end_point,
        distance_obstacle_to_left_point,
        dist_start_to_end)

    logger_th_server.debug(f"[Compute Obstacle Loc] obstacle location: ({ob_x}, {ob_y})")

    return {"x":ob_x, "y":ob_y}


def obstacle_perturbation(perturbation, logger):
    global ta_endpoints
    global cur_mov_plan
    global placedObstacleID

    global can_perturb
    global mission_done
    global cur_target_done
    global robot_status

    global robot_status_ready
    global robot_status_use
    global robot_status

    global time_interval_observation

    p_type = perturbation['type']
    ratio  = perturbation['ratio']

    logger.info(f"[Obstacle Perturbation] ({p_type}, {ratio}) Starts")

    perturbation_result = False

    can_perturb_check_counter = 0
    robot_status_ready_check_counter = 0
    robot_dist_check_counter = 0
    while not perturbation_result:

        if mission_done.is_set():
            logger.error(f"[Obstacle Perturbation] mission_done is set when observing the robot's location. ({p_type}, {ratio}).", exc_info=True)
            break
        elif cur_target_done.is_set():
            logger.error(f"[Obstacle Perturbation] cur_target_done is set when observing the robot's location. ({p_type}, {ratio}).", exc_info=True)
            break
        elif not can_perturb.is_set():
            if (can_perturb_check_counter % 10) == 0:
                logger.info(f"[Obstacle Perturbation] Charging or adaptation happens when observing the robot's location. ({p_type}, {ratio}).")
            can_perturb_check_counter += 1
            robot_status_use.clear()
            time.sleep(time_interval_observation)
            continue
            logger.info(f"[Obstacle Perturbation] Can perturb now.")

        #robot_status = observe_req("obstacle_perturbation", ta_endpoints["robot_status"], logger)
        logger.debug(f"[Obstacle Perturbation] robot_status: ready - {robot_status_ready.is_set()}, use - {robot_status_use.is_set()}")

        if not robot_status_ready.is_set():
            if (robot_status_ready_check_counter % 10) == 0:
                logger.debug(f"[Obstacle Perturbation] robot_status is not ready.")
            robot_status_ready_check_counter += 1

            time.sleep(time_interval_observation)
            continue
        logger.info(f"[Obstacle Perturbation] robot_status is ready")

        # use robot_status
        robot_status_use.set()

        if robot_status != False:
            x = robot_status['x']
            y = robot_status['y']
            battery = robot_status['battery']
            sim_time = robot_status['sim-time'] 

            cur_loc = {'x':x, 'y':y}
            closet_waypoint = test_map.coords_to_waypoint(cur_loc)
            if closet_waypoint["dist"] <= 1:
                if (robot_dist_check_counter % 10) == 0:
                    logger.info(f"[Obstacle Perturbation] The distance of the robot {cur_loc} to the waypoint {closet_waypoint['id']} is {closet_waypoint['dist']}. It is too close such that makes the inference of which segment the robot locates very difficulty. So, wait for 1 secnod and check again.")
                robot_dist_check_counter += 1

                robot_status_use.clear()
                time.sleep(time_interval_observation)
                continue 

            if mission_done.is_set():
                logger.error(f"[Obstacle Perturbation] mission_done is set when calculating obstacle location for the obstacle perturbation, ({p_type}, {ratio})", exc_info=True)
                break
            elif cur_target_done.is_set():
                logger.error(f"[Obstacle Perturbation] cur_target_done is set when calculating obstacle location for the obstacle perturbation, ({p_type}, {ratio})", exc_info=True)
                break
            elif not can_perturb.is_set():
                if (can_perturb_check_counter % 10) == 0:
                    logger.info(f"[Obstacle Perturbation] Charing or adaptation happens when calculating obstacle location for the obstacle perturbation, ({p_type}, {ratio})")
                can_perturb_check_counter += 1

                robot_status_use.clear()
                time.sleep(time_interval_observation)
                continue
            else:
                if len(cur_mov_plan["plan"]) == 0:
                    logger.error(f"[Obstacle Perturbation] The current plan {cur_mov_plan} is empty. Stopping the test.", exc_info=True)
                    break
                elif (len(cur_mov_plan["plan"]) == 1):
                    logger.error(f"[Obstacle Perturbation] The current plan {cur_mov_plan} has only one target. Placeing an effective obstacle will trap the robot", exc_info=True)
                    break
                elif (len(cur_mov_plan["plan"]) == 2) and (("l1" in cur_mov_plan["plan"]) or ("l8" in cur_mov_plan["plan"])):
                    logger.error(f"[Obstacle Perturbation] The current plan {cur_mov_plan} has two targets but one of them is 'l1' or 'l8'. Placeing an effective obstacle will trap the robot", exc_info=True)
                    break
                else:
                    # Obstacles placed in the segments, l1-l2 and l7-l8, will trap the robot.
                    # So, do not consider them
                    mov_plan = {}
                    mov_plan["plan"] = list(filter(lambda target: (target != "l1") and (target != "l8"), cur_mov_plan["plan"]))
                    mov_plan["sentByTAStatus"] = cur_mov_plan["sentByTAStatus"]

                    try:
                        logger.info(f"[Obstacle Perturbation]  ({p_type}, {ratio}) starts to calculating obstacle location.")
                        obstacle_coord = compute_obstacle_location(x, y, ratio, mov_plan)
                    except Exception as e:
                        logger.error(f"[Obstacle Perturbation] fail to comptue the location of the obstacle to place. {e}", exc_info=True)
                        break

                logger.info(f"[Obstacle Perturbation]  ({p_type}, {ratio}) start to placing an obstacle at ({obstacle_coord['x']}, {obstacle_coord['y']}).")    
                if mission_done.is_set():
                    logger.error(f"[Obstacle Perturbation] mission_done is set when sending a request to place obstacle for obstacle perturbation, ({p_type}, {ratio}).", exc_info=True)
                    break
                elif cur_target_done.is_set():
                    logger.error(f"[Obstacle Perturbation] cur_target_done is set when sending a request to place obstacle for obstacle perturbation, ({p_type}, {ratio}).", exc_info=True)
                    break
                elif not can_perturb.is_set():
                    if (can_perturb_check_counter % 10) == 0:
                        logger.info(f"[Obstacle Perturbation] Charging or adaptation happens when sending a request to place obstacle for obstacle perturbation, ({p_type}, {ratio}).")
                    can_perturb_check_counter += 1

                    robot_status_use.clear()
                    time.sleep(time_interval_observation)
                    continue
                else:
                    logger.info(f"[Obstacle Perturbation] starts to place the obstacle, {obstacle_coord}.")
                    obstacle_placement_result = place_obstacle_req('obstacle_perturbation', ta_endpoints["place_obstacle"], logger, obstacle_coord)
                    if obstacle_placement_result == False:
                        logger.error(f"[Obstacle Perturbation] ({p_type}, {ratio}) succeeds. The current plan is {cur_mov_plan}", exc_info=True)
                        break
                    else:
                        logger.info(f"[Obstacle Perturbation] ({p_type}, {ratio}) succeeds. The current plan is {cur_mov_plan}")                
                        perturbation_result = True

        else: # perturbation fails because of the failure of /observe request to the TA
            logger.error(f"[Obstacle Perturbation] ({p_type}, {ratio}) fails because the /observe request fails")
            break

    robot_status_use.clear()
    
    return perturbation_result # The battery perturbation is made successfully



def run_mission(ta_url, logger):

    global placedObstacleID

    global ta_alive
    global can_perturb
    global stop_th
    global mission_done
    global cur_target_done
    global robot_status_ready
    global robot_status_use

    global num_targets
    global case_level
    global targets
    global mission_result
    global cur_target_ID
    global perturbation_seqs
 
    ta_alive.wait()

    # Start the mission
    endpoint = ta_endpoints["start_mission"]
    req_result = start_mission_req('run_mission', endpoint, logger)
    if req_result == False: # request fails
        logger.error(f"Fail to start the mission. /start request to the TA is not successful.", exc_info=True)
    else: # mission is started successfully
        mission_done.clear()

        logger.debug(f"[run_mission] mission starts. robot_status: ready - {robot_status_ready.is_set()}, use - {robot_status_use.is_set()}")
        # setup battery monitoring
        t_battery_check = threading.Thread(
                name='check_robot_status',
                target=check_robot_status,
                args=(logger,))
        t_battery_check.start()

        # Perturbations
        if case_level == 'a':
            try:
                for target_ID in range(1, num_targets+1):
                    cur_target_done.clear()
                    cur_target_ID = target_ID
                    mission_result['num_targets_tried'] += 1
                    mission_result[f"Target{target_ID}"]["is_tried"] = True

                    logger.info(f"[Target] Starts moving to Target {target_ID}: {targets[target_ID-1]}.")
                    # Waiting for TH to set the event, cur_target_done.
                    # TH will set it when TA sends the 'at-waypoint' status message
                    # that indicates that the current target is reached
                    cur_target_done.wait()
                    if mission_done.is_set() and (target_ID != num_targets):
                        logger.info("[Mission Done] Mission is done but not all targets are reached.")
                        break
                    logger.info(f"[Target] Reach Target {target_ID}: {targets[target_ID-1]}.")
            except Exception as e:
                logger.error(f"[Mission Failure] [Case {case_level}] {e}", exc_info=True)
        else:
            # For case 'b':
            #   No adaptation but has charging option.
            # For case 'c' and 'd':
            #   Planner does not run adaptation in the beginning of the
            #   mission when the 'live' status message is sent by TA.
            #   TH will clear the event, can_perturb, when receiving the
            #   'adapt-started' status message from TA and reset it when
            #   receiving the 'adapt-done' status message from TA.
            # So, set the event, can_perturb, at this point.

            time_interval_pertubation = 2

            try:
                for target_ID in range(1, num_targets+1):
                    cur_target_ID = target_ID
                    logger.info(f"[Target {target_ID} ({targets[target_ID-1]})] starts ")
                    cur_target_done.clear()
                    is_adapting.clear()
                    can_perturb.set()
                    robot_status_ready.clear()
                    robot_status_use.clear()

                    mission_result['num_targets_tried'] += 1
                    mission_result[f"Target{target_ID}"]['is_tried'] = True

                    perturbation_seq = perturbation_seqs[f"Target{target_ID}"]
                    for perturb_ID in range(len(perturbation_seq)):
                        perturb_type = perturbation_seq[perturb_ID]['type']
                        if (not mission_done.is_set()) and (not cur_target_done.is_set()) and (perturbation_seq[perturb_ID]['ratio'] != 0):
                            logger.info(f"[Target {target_ID} ({targets[target_ID-1]})] [Perturbation {1+perturb_ID} ({perturb_type})] starts.")
                            result = do_perturbation(perturbation_seq[perturb_ID], logger)

                            mission_result['perturbation_stat']['num_perturbations_tried'] += 1
                            mission_result[f"Target{target_ID}"]['num_perturbations_tried'] += 1

                            if result:
                                mission_result['perturbation_stat']['num_successful_perturbations'] += 1
                                mission_result[f"Target{target_ID}"]['num_successful_perturbations'] += 1
                                mission_result[f"Target{target_ID}"]['perturbations'][perturb_ID]["status"] = "Success"
                                if "easy" in perturb_type:
                                    mission_result['perturbation_stat']['num_successful_easy_perturbations'] += 1
                                elif "medium" in perturb_type:
                                    mission_result['perturbation_stat']['num_successful_medium_perturbations'] += 1
                                else: # hard perturbation
                                    mission_result['perturbation_stat']['num_successful_hard_perturbations'] += 1

                                logger.info(f"[Target {target_ID} ({targets[target_ID-1]})] [Perturbation {1+perturb_ID} ({perturb_type})] success.")
                            else:
                                mission_result[f"Target{target_ID}"]['perturbations'][perturb_ID]["status"] = "Failure"
                                logger.info(f"[Target {target_ID} ({targets[target_ID-1]})] [Perturbation {1+perturb_ID} ({perturb_type})] failure.")

                            time.sleep(time_interval_pertubation)
                        else:
                            if perturbation_seq[perturb_ID]['ratio'] == 0:
                                not_try_reason = "0 Severity"
                                mission_result[f"Target{target_ID}"]['perturbations'][perturb_ID]["status"] = f"Not Tried - {not_try_reason}"
                                logger.info(f"[Target {target_ID} ({targets[target_ID-1]})] [Perturbation {1+perturb_ID} ({perturb_type})] Not tried - {not_try_reason}.")
                            else:
                                not_try_reason = ""
                                if mission_done.is_set():
                                    not_try_reason = "Mission Done"
                                    cur_target_done.set()
                                elif cur_target_done.is_set():
                                    not_try_reason = "Current Target Done"
                                else:
                                    not_try_reason = "Unknown"

                                for not_tried_perturb_ID in range(perturb_ID, len(perturbation_seq)):
                                    perturb_type = perturbation_seq[not_tried_perturb_ID]['type']
                                    mission_result[f"Target{target_ID}"]['perturbations'][not_tried_perturb_ID]["status"] = f"Not Tried - {not_try_reason}"

                                    logger.info(f"[Target {target_ID} ({targets[target_ID-1]})] [Perturbation {1+not_tried_perturb_ID} ({perturb_type})] Not tried - {not_try_reason}.")
                                break 

                    logger.info(f"[Target {target_ID} ({targets[target_ID-1]})] Perturbations Done")

                    cur_target_done.wait()
                    if mission_done.is_set():
                        if (target_ID != num_targets):
                            logger.info(f"[Mission Done] while doing perturbation for target {target_ID}, {targets[target_ID-1]}.")
                        break

                    # Remove the placed obstacle for the current target
                    if placedObstacleID != None:
                        # remove it
                        result  = remove_obstacle_req('run_mission', ta_endpoints["remove_obstacle"], logger, placedObstacleID) 
                        if result:
                            placedObstacleID = None
                        else:
                            logger.error(f"[Obstacle Perturbation] Target {target_ID}, {targets[target_ID-1]}: failed to remove the obstacle, {placedObstacleID}. Stop the test.", exc_info=True)
                            break
            except Exception as e:
                logger.error(f"[Mission Failure] [Case {case_level}] {e}", exc_info=True)

        # Wait for TA's '/done' request
        mission_done.wait()


    logger.info("Mission is done!")

    # Trigger event to save logs to S3 bucket and shutting down the TH.
    stop_th.set()

class ServerThread(threading.Thread):

    def __init__(self, app, hostname, port):
        threading.Thread.__init__(self)
        self.srv = make_server(hostname, port, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        self.srv.serve_forever()

    def shutdown(self):
        self.srv.shutdown()

def start_server(host, port, logger):
    global server
    global app

    logger.info('TH server is starting')

    server = ServerThread(app, host, port)
    server.run()


def stop_server(logger):
    global server
    global stop_th
    global mission_result
    global test_ID
    global log_dir
    global mission_result

    stop_th.wait()

    try:
        # dump the mission result into the log fold
        mission_result_filepath = os.path.join(log_dir, f"mission_result_{test_ID}.json")
        with open(mission_result_filepath, "w") as fp:
            json.dump(mission_result, fp, indent=4)
    except Exception as e:
        logger.error(e, exc_info=True)

    # save TH log to S3 bucket
    ld=log_dir #"/logs/"

    res = subprocess.call([
        "aws", "s3", "cp", ld,
        s3_bucket_url + "/" + test_ID + "/",
        "--recursive"])
    if not res == 0:
        logger.error(f"Failed to save TH logs to S3 bucket at {s3_bucket_url}/{test_ID}", exc_info=True)
    else:
        logger.info(f"Successfully saved TH logs to S3 bucket at {s3_bucket_url}/{test_ID}")

    server.shutdown()
    logger.info('server is shutting down')
 
def check_robot_status(logger):
    '''
        1. Monitor the battery charing event in the robot.
        2. The monitoring should be started when the mission
           is started and shutdown when the mission is done.
    '''
    global mission_done
    global can_perturb
    global is_adapting
    global last_target_done

    global robot_status_ready
    global robot_status_use
    global robot_status

    global ta_endpoints
    global robot_status

    global time_interval_observation

    encountered_error = False

    # Initialize robot status when the mission starts
    try:
        robot_status = observe_req("check_robot_battery", ta_endpoints["robot_status"], logger)
    except Exception as e:
        logger.error(f"[Robot Status] failed to initialize robot_status: {e}. Stop monitoring and wait for the mission signal from the TA.", exc_info=True)
        return

    robot_battery = 0

    if robot_status == False:
        encountered_error = True
    else:
        logger.info(f"[Robot Status] initial status: {robot_status}")
        robot_battery = robot_status['battery']

        time_stamp=time.strftime("%Y-%m-%d_%H-%M-%S", time.gmtime())
        dt = datetime.datetime.strptime(time_stamp, "%Y-%m-%d_%H-%M-%S")
        time_stamp_ms = int(time.mktime(dt.timetuple()) * 1000) # millium seconds

        mission_result['mission_start']['wall_clock']   = time_stamp_ms
        mission_result['mission_start']['sim_time']     = robot_status['sim-time']

        logger.info(f"[Robot Status] periodical observation starts")

        robot_status_use_check_counter  = 0
        robot_observation_counter       = 0
        not_charging_check_counter      = 0

        try:
            # Periodically observe the robot's battery
            while (not mission_done.is_set()) and (not last_target_done.is_set()):
                #logger.debug(f"[Robot Status] before sleeping - mission_done: {mission_done.is_set()}, last_target_done: {last_target_done.is_set()}")

                #time.sleep(time_interval_observation)

                #logger.debug(f"[Robot Status] after sleeping - mission_done: {mission_done.is_set()}, last_target_done: {last_target_done.is_set()}")

                #if (mission_done.is_set() or last_target_done.is_set()):
                #    break

                #logger.debug(f"[Robot Status] ready - {robot_status_ready.is_set()}, use - {robot_status_use.is_set()}")
                if robot_status_use.is_set():
                    if (robot_status_use_check_counter % 10) == 0:
                        logger.debug(f"[Robot Status] robot_status is in use. Do not observe new one for now.")
                    robot_status_use_check_counter += 1
                    time.sleep(time_interval_observation)
                    continue
                else:       
                    # It's time to observe a new robot_status
                    if (robot_status_use_check_counter % 10) == 0:
                        logger.debug(f"[Robot Status] robot_status is not in use. Observe a new one.")
                    robot_status_use_check_counter += 1

                    robot_status_ready.clear()
                    robot_status = observe_req("check_robot_battery",ta_endpoints["robot_status"], logger, is_periodical=True)
                    robot_status_ready.set()

                    if robot_status == False:
                        encountered_error = True
                        break
                    else:
                        if (robot_observation_counter % 10) == 0:
                            logger.info(f"[Robot Status] {robot_status}")
                        robot_observation_counter += 1

                        cur_battery = robot_status['battery']
                        battery_change = cur_battery - robot_battery
                        if battery_change > 0:
                            logger.info(f"[Robot Status] Charging: battery is increased from {robot_battery} to {cur_battery}")

                        robot_battery = cur_battery

                        # In C and D cases, when adaptation happends
                        # can_perturb is cleared to avoid perturbations.
                        # Inside an adaptation, no need to check battery
                        # for perturbation permission.
                        # In B case, there is no adapation. But charging
                        # could happens. So, we need to monitor charging event.
                        if not is_adapting.set():
                            if battery_change > 0: # charging now
                                logger.info(f"[Robot Status] Charing now, can not perturb.")
                                can_perturb.clear()
                            else: # not charging
                                if (not_charging_check_counter % 10) == 0:
                                    logger.debug(f"[Robot Status] Not Charing now.")
                                can_perturb.set()
                        not_charging_check_counter += 1

                # Control the /observe request frequence
                time.sleep(time_interval_observation)

        except Exception as e:
            logger.error(f"[Robot Status] observation failure: {e}", exc_info=True)


    if encountered_error:
        logger.error(f"[Robot Status] failed to observe the robot's status. Wait for mission_done signal to stop the test.", exc_info=True)

    if mission_done.is_set() or last_target_done.is_set():
        logger.info(f"[Robot Status] stopped because mission_done is set.")
        robot_status_ready.clear()
        robot_status_use.clear()

def reset_events_when_mission_done(logger):
    global mission_done
    global cur_target_done
    global last_target_done
    global can_perturb

    mission_done.wait()

    cur_target_done.set()
    last_target_done.set()
    can_perturb.clear()

    logger.info(f"[Mission Done] cur_target_done and last_target_done are set while can_perturb is cleared.")




if __name__=='__main__':
    
    t_run_mission = threading.Thread(
            name='run_mission', 
            target=run_mission,
            args=(ta_url, logger_th_server))
    # Stop the thread of running 'run_mission' when stop_th is set
    # because TA sends a status with a non-recoverable error message.
    t_run_mission.daemon = True
    t_run_mission.start()
      
    t_stop_th = threading.Thread(
            name='stop_th',
            target=stop_server,
            args=(logger_th_server,))
    t_stop_th.start()



    start_server(th_host, th_port, logger_th_server)
