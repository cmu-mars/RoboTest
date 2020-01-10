#!/usr/bin/env python3

import sys
import connexion
import logging
import traceback
import os
import json
from multiprocessing import Process, Queue
import rospy
import actionlib
import threading

from std_msgs.msg import Float64
from move_base_msgs.msg import MoveBaseAction
from rosgraph_msgs.msg import Clock

from swagger_client.rest import ApiException
from swagger_client import DefaultApi
from swagger_client.models.inline_response_200 import InlineResponse200
from swagger_client.models.errorparams import Errorparams
from swagger_client.models.statusparams import Statusparams

import swagger_server.config as config
import swagger_server.comms as comms
from swagger_server.util import *
from swagger_server.encoder import JSONEncoder

from learner.learn import Learn
from robotcontrol.bot_controller import BotController
from rainbow_interface import RainbowInterface
from robotcontrol.launch_utils import launch_cp1_base, init

import swagger_server.resources as resources
from robotcontrol.instructions_db import InstructionDB

config_list_file = os.path.expanduser('~/cp1/config_list.json')
config_list_file_true = os.path.expanduser('~/cp1/config_list_true.json')
instructions_db_file = os.path.expanduser("~/catkin_ws/src/cp1_base/instructions/instructions-all.json")


if __name__ == '__main__':
    # Parameter parsing, to set up TH
    if len(sys.argv) != 2:
        print("No URI TH passed in!")
        sys.exit(1)

    th_uri = sys.argv[1]

    # Set up TA server and logging
    app = connexion.App(__name__, specification_dir='./swagger/')
    app.app.json_encoder = JSONEncoder
    app.add_api('swagger.yaml', arguments={'title': 'CP1'}, strict_validation=True)

    # capture the logger
    logger = logging.getLogger('werkzeug')
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(os.path.expanduser('~/logs/TA_access.log'))
    logger.addHandler(handler)

    # share logger with endpoints
    config.logger = logger

    def log_request_info():
        logger.debug('Headers: %s', connexion.request.headers)
        logger.debug('Body: %s', connexion.request.get_data())

    app.app.before_request(log_request_info)

    # build the TH API object
    thApi = DefaultApi()
    thApi.api_client.configuration.host = th_uri
    config.thApi = thApi

    def fail_hard(s):
        logger.debug(s)
        comms.save_ps("error-failhard")

        ## if we at least have the UUID, then try to sequester.
        if config.uuid and config.th_connected:
            comms.sequester()

        if config.th_connected:
            err = Errorparams(error="other-error", message=s)
            result = thApi.error_post(err)
        raise Exception(s)

    ## record the resources to log
    resources.report_system_resources(logger)
    resources.report_resource_limits(logger)

    # start the sequence diagram: post to ready to get configuration data
    try:
        logger.debug("posting to /ready")
        ready_resp = thApi.ready_post()
        config.th_connected = True
        logger.debug("received response from /ready: %s" % ready_resp)
    except Exception as e:
        # this isn't a call to fail_hard because the TH isn't
        # responding at all; we have to hope that LL notices the log
        # output and that this happens only very rarely if at all
        logger.debug("failed to connect with th")
        logger.debug(traceback.format_exc())
        config.th_connected = False
        ready_file_name = sys.argv[1]
        # Adding test ready info
        with open(os.path.expanduser(ready_file_name)) as ready:
            data = json.load(ready)
            ready_resp = InlineResponse200(
                level=data["level"], start_loc=data["start-loc"],
                target_locs=data["target-locs"],
                power_model=data["power-model"],
                discharge_budget=data["discharge-budget"])
            logger.info("started TA in disconnected mode")
        # raise e

    ## if we get a message from ready, that means we're in the LL
    ## environment and should set up log sequestration
    if config.th_connected:
        test_ID = os.environ.get('TEST_ID')
        config.s3_bucket_url = os.environ.get('S3_BUCKET_CP1_PATH')
        config.uuid = test_ID

        if (not config.s3_bucket_url) or (len(config.s3_bucket_url) == 0):
            fail_hard("S3 bucket URL undefined; cannot sequester logs")

        if (not config.uuid) or (len(config.uuid) == 0):
            fail_hard("test ID undefined; cannot sequester logs")


        '''
        ecs_meta = os.environ.get('ECS_CONTAINER_METADATA_FILE')

        if not ecs_meta:
            fail_hard('ECS_CONTAINER_METADATA_FILE not defined; cannot sequester logs')

        config.uuid = (subprocess.check_output("cat $ECS_CONTAINER_METADATA_FILE | jq -r '.TaskARN' | cut -d '/' -f2")).strip()

        if (not config.uuid) or (len(config.uuid) == 0):
            fail_hard("uuid undefined; cannot sequester logs")
        '''


    config.ready_response = ready_resp

    # dynamic checks on ready response
    if not ready_resp.target_locs:
        fail_hard("malformed response from ready: target_locs must not be the empty list")

    if ready_resp.start_loc == ready_resp.target_locs[0]:
        fail_hard("malformed response from ready: start-loc must not be the same as the first item of target-locs")

    if not check_adj(ready_resp.target_locs):
        fail_hard("malformed response from ready: target-locs contains adjacent equal elements")

    # once the response is checked, write it to ~/ready
    logger.debug("writing checked /ready message to ~/ready")
    with open(os.path.expanduser('~/ready'), 'w') as ready_file:
        json.dump(dict((k.replace("_", "-"), v) for k, v in ready_resp.to_dict().items()), ready_file)

    config.level = ready_resp.level

    with open(os.path.expanduser('~/ready'), 'r') as ready_content:
        ready_json = json.load(ready_content)
    print(ready_json)
    model_learner = Learn()
    config.learner = model_learner

    try:
        model_learner.get_true_model()
        # Provide the true default config to bot controller for case A and case B
        # In case C, the true default config will be provided in after learning.
        model_learner.dump_true_default_config()

        with open(config_list_file_true, 'r') as confg_file:
            print("**True Default Config**")
            config_data = json.load(confg_file)
            print(config_data)

    except Exception as e:
        logger.debug("parsing raised an exception; notifying the TH and then crashing")
        comms.save_ps("parsing_error")
        if config.th_connected:
            ## copy out logs before posting error
            if config.uuid and config.th_connected:
                comms.sequester()
            thApi.error_post(Errorparams(error="parsing-error", message="exception raised: %s" % e))
        else:
            rospy.logerr("parsing-error")
        raise e

    if (ready_resp.level == "c") or (ready_resp.level == "d"):
        logger.debug("offline-learning-started")
        if config.th_connected:
            comms.send_status("__main__", "offline-learning-started", sendxy=False, sendtime=False)

        try:
            result = model_learner.start_learning()
        except Exception as e:
            logger.debug("learning raised an exception; notifying the TH and then crashing")
            comms.save_ps("learning_error")
            if config.th_connected:

                ## copy out logs before posting error
                if config.uuid and config.th_connected:
                    comms.sequester()

                thApi.error_post(Errorparams(error="learning-error", message="exception raised: %s" % e))
            else:
                rospy.logerr("learning-error")
            raise e

        logger.debug("offline-learning-done")
        if config.th_connected:
            comms.send_status("__main__", "offline-learning-done", sendxy=False, sendtime=False)

        if ready_resp.level == "c":
            model_learner.dump_learned_model()

        model_learner.update_config_files()
        # let's print the list of configurations the learner founds for debugging
        with open(config_list_file, 'r') as confg_file:
            print("**Predicted**")
            config_data = json.load(confg_file)
            print(config_data)

        with open(config_list_file_true, 'r') as confg_file:
            print("**True**")
            config_data = json.load(confg_file)
            print(config_data)

      


    # roslaunch
    # Init me as a node
    logger.debug("initializing cp1_ta ros node")
    # rospy.init_node("cp1_ta")

    p = Process(target=launch_cp1_base, args=('default',))
    p.start()
    init("cp1_ta")

    logger.debug("waiting for move_base (emulates watching for odom_received)")
    move_base = actionlib.SimpleActionClient("move_base", MoveBaseAction)

    move_base_started = False
    ind = 0
    while not move_base_started and ind < 12:
        ind += 1
        move_base_started = move_base.wait_for_server(rospy.Duration.from_sec(10))
        rospy.loginfo("waiting for the action server")

    if not move_base_started:
        fail_hard("fatal error: navigation stack has failed to start")

    # build controller object
    bot_cont = BotController()

    # start tracking battery charge
    bot_cont.gazebo.track_battery_charge()
    bot_cont.level = ready_resp.level

    # subscribe to rostopics
    def energy_cb(msg):
        """call back to update the global battery state from the ros topic"""
        config.battery = int(msg.data)
        if msg.data <= 0:
            if config.th_connected:
                comms.send_done("energy call back", "out of juice", "out-of-battery")
            else:
                rospy.logerr("out-of-battery")

    sub_mwh = rospy.Subscriber("/mobile_base/commands/charge_level_mwh", Float64, energy_cb)

    # Subscribe to simulator clock
    def clock_cb(msg):
        #print("%s, %s" %(msg.clock.secs,rospy.get_time()))
        config.sim_time = msg.clock.secs

    sub_clock = rospy.Subscriber("/clock", Clock, clock_cb)

    config.bot_cont = bot_cont

    # check that things are actually waypoint names
    if not bot_cont.map_server.is_waypoint(ready_resp.start_loc):
        fail_hard("name of start location is not a waypoint: %s" % ready_resp.start_loc)

    for name in ready_resp.target_locs:
        if not bot_cont.map_server.is_waypoint(name):
            fail_hard("name of target location is not a waypoint: %s" % name)

    # set the intial plan
    config.instruction_db = InstructionDB(instructions_db_file)
    config.plan = config.instruction_db.get_path(ready_resp.start_loc, ready_resp.target_locs[0])
    config.tasks = ready_resp.target_locs

    # put the robot in the right place
    start_coords = bot_cont.map_server.waypoint_to_coords(ready_resp.start_loc)
    bot_cont.gazebo.set_bot_position(start_coords['x'], start_coords['y'], 0)

    # start up rainbow if we're adapting, otherwise send the live message directly
    if ready_resp.level == "c" or ready_resp.level == "d":
        try:
            logger.debug("Starting Rainbow")
            rainbow_log = open(os.path.expanduser("~/logs/rainbow.log"), 'w')
            rainbow = RainbowInterface()
            rainbow.launchRainbow("cp1", rainbow_log)
            config.rainbow = rainbow
            ok = rainbow.startRainbow()
            if not ok:
                fail_hard("did not connect to rainbow in a timely fashion")
        except Exception as e:
            fail_hard("failed to connection to rainbow: %s" % e)
    elif config.th_connected:
        def worker():
            rospy.sleep(5)
            comms.send_status("__main__ in level %s" % ready_resp.level, "live", sendtime=False)
        t = threading.Thread(target=worker)
        t.start()

    logger.debug("Starting TA REST interface")
    print("Starting TA REST interface")

    # app.debug = True
    app.run(host='0.0.0.0', port=5000)
