import connexion
import asyncio
import concurrent.futures
from multiprocessing import Process, pool
from threading import Thread
import rospy
import json
import ast

from swagger_server.models.battery_params import BatteryParams  # noqa: E501
from swagger_server.models.inline_response200 import InlineResponse200  # noqa: E501
from swagger_server.models.inline_response2001 import InlineResponse2001  # noqa: E501
from swagger_server.models.inline_response2002 import InlineResponse2002  # noqa: E501
from swagger_server.models.inline_response2003 import InlineResponse2003  # noqa: E501
from swagger_server.models.inline_response400 import InlineResponse400  # noqa: E501
from swagger_server.models.inline_response4001 import InlineResponse4001  # noqa: E501
from swagger_server.models.inline_response4002 import InlineResponse4002  # noqa: E501
from swagger_server.models.inline_response4003 import InlineResponse4003  # noqa: E501
from swagger_server.models.internal_status_response200 import InternalStatusResponse200
from swagger_server.models.place_params import PlaceParams  # noqa: E501
from swagger_server.models.remove_params import RemoveParams  # noqa: E501
from swagger_server.models.cp1_internal_status import CP1InternalStatus as CP1IS
from swagger_server import util
from swagger_client.models.errorparams import Errorparams
from swagger_client.models.done_tasksfinished import DoneTasksfinished
import swagger_server.config as config
import swagger_server.comms as comms


def internal_status_post(CP1InternalStatus):  # noqa: E501
    """internal_status_post

    reports any internal status (including the error that may occured) from the backend that might be sent to the TA for internal bookeeping or forwarding to the TH # noqa: E501

    :param CP1InternalStatus:
    :type CP1InternalStatus: dict | bytes

    :rtype: None
    """
    config.logger.debug("Call to internal-status")
    success = True
    try:
        cp1_internal_status = CP1InternalStatus
        if connexion.request.is_json:
            config.logger.debug("Attempting from_dict")
            cp1_internal_status = CP1IS.from_dict(connexion.request.get_json())  # noqa: E501

        config.logger.debug("TA internal status end point hit with status %s and message %s"
                            % (cp1_internal_status.status, cp1_internal_status.message))

        if cp1_internal_status.status == "learning-started":
            config.logger.debug("internal got a deprecated status which is being ignored")
        elif cp1_internal_status.status == "learning-done":
            config.logger.debug("internal got a deprecated status which is being ignored")
        elif cp1_internal_status.status == "adapt-started":
            comms.send_status("internal", "adapt-started")
        elif cp1_internal_status.status == "adapt-done":
            comms.send_status("internal", "adapt-done")
        elif cp1_internal_status.status == "charging-started":
            comms.send_status("internal", "charging-started")
        elif cp1_internal_status.status == "charging-done":
            comms.send_status("internal", "charging-done")
        elif cp1_internal_status.status == "parsing-error":
            config.logger.debug("internal got a deprecated status which is being ignored")
        elif cp1_internal_status.status == "learning-error":
            config.logger.debug("internal got a deprecated status which is being ignored")
        elif cp1_internal_status.status == "other-error":
            config.logger.debug("sending error to the TH because of message %s" % cp1_internal_status.message)

            # copy out logs before posting error
            if config.uuid and config.th_connected:
                comms.sequester()

            resp = config.thApi.error_post(Errorparams(error="other-error", message=cp1_internal_status.message))

        # these are the literal constants that come from rainbow. the
        # constants above are from the API definition; there's some
        # overlap and this is a little messy
        elif cp1_internal_status.status == "RAINBOW_READY":
            comms.send_status("internal, rainbow ready in level %s" % config.ready_response.level, "live", sendxy=False)
        elif cp1_internal_status.status == "MISSION_SUCCEEDED":
            config.logger.debug("internal got a rainbow mission message which is being ignored")
        elif cp1_internal_status.status == "MISSION_FAILED":
            config.logger.debug("internal got a rainbow mission message which is being ignored")
        elif cp1_internal_status.status == "ADAPTING":
            comms.send_status("internal", "adapt-started")
        elif cp1_internal_status.status == "ADAPTED":
            comms.send_status("internal", "adapt-done")
        elif cp1_internal_status.status == "ADAPTED_FAILED":
            comms.send_status("internal, adapted_failed", "adapt-done")
        elif cp1_internal_status.status == "PLAN":
            config.plan = [ x.strip() for x in ast.literal_eval(cp1_internal_status.message) ]
            if not cp1_internal_status.sim_time == -1:
                config.logger.debug("[WARN] ta got an internal plan status with sim_time %s, which is out of spec" % cp1_internal_status.sim_time)
        elif cp1_internal_status.status == "learning-requested":
            success = invoke_online_learning()
    except Exception as e:
        config.logger.debug("Internal status got an exception: %s" % e)
    ret = InternalStatusResponse200(success)
    config.logger.debug("%s " %ret)
    return ret


def observe_get():
    """
    observe_get
    observe some of the current state of the robot for visualization and invariant checking for perturbation end points. n.b. this information is to be used strictly in a passive way; it is not to be used for evaluation of the test at all.

    :rtype: InlineResponse2003
    """

    config.logger.debug("observe_get was called")
    x, y, ig1, ig2 = config.bot_cont.gazebo.get_bot_state()

    ret = InlineResponse2003()
    ret.x = x
    ret.y = y
    ret.battery = config.battery
    ret.sim_time = config.sim_time

    return ret


def perturb_battery_post(Parameters=None):
    """
    perturb_battery_post
    set the level of the battery in a currently running test. consistent with the monotonicity requirement for the power model, this cannot be more than the current amount of charge in the battery.
    :param Parameters:
    :type Parameters: dict | bytes

    :rtype: InlineResponse2002
    """

    config.logger.debug("perturb_battery_post was called")
    if connexion.request.is_json:
        Parameters = BatteryParams.from_dict(connexion.request.get_json())  # noqa: E501

    charge = Parameters.charge / (1000 * config.bot_cont.robot_battery.battery_voltage)
    result = config.bot_cont.gazebo.set_charge(charge)
    if result:
        return InlineResponse2002(sim_time=config.sim_time)
    else:
        return InlineResponse4002(message="setting the battery failed"), 400


def perturb_place_obstacle_post(Parameters=None):
    """
    perturb_place_obstacle_post
    if the test is running, then place an instance of the obstacle on the map
    :param Parameters:
    :type Parameters: dict | bytes

    :rtype: InlineResponse200
    """

    config.logger.debug("perturb_place_obstacle_post was called")
    if connexion.request.is_json:
        Parameters = PlaceParams.from_dict(connexion.request.get_json())  # noqa: E501

    result = config.bot_cont.gazebo.place_obstacle(Parameters.x, Parameters.y)
    if result:
        return InlineResponse200(obstacleid=result, sim_time=config.sim_time)
    else:
        # todo: we can't really distinguish between reasons for
        # failure here so the API is a little bit too big
        return InlineResponse4001(cause="other-error", message="obstacle placement failed")


def perturb_remove_obstacle_post(Parameters=None):
    """
    perturb_remove_obstacle_post
    if the test is running, remove a previously placed obstacle from the map
    :param Parameters:
    :type Parameters: dict | bytes

    :rtype: InlineResponse2001
    """

    config.logger.debug("perturb_remove_obstacle_post was called")
    if connexion.request.is_json:
        Parameters = RemoveParams.from_dict(connexion.request.get_json())  # noqa: E501

    result = config.bot_cont.gazebo.remove_obstacle(Parameters.obstacleid)
    if result:
        return InlineResponse2001(sim_time=config.sim_time)
    else:
        return InlineResponse4001(cause="bad-obstacle_id",
                                  message="asked to remove an obstacle with a name we didn't issue")


def start_post():
    """
    start_post
    start the turtlebot on the mission

    :rtype: None
    """
    if not config.started:
        config.started = True

        def at_waypoint_cb(name_of_waypoint):
            config.logger.debug("at_waypoint callback called with %s" % name_of_waypoint)
            x, y, ig1, ig2 = config.bot_cont.gazebo.get_bot_state()
            config.tasks_finished.append(DoneTasksfinished(x=x,
                                                           y=y,
                                                           sim_time=config.sim_time,
                                                           name=name_of_waypoint))
            # get the next default plan
            ct = config.tasks[0]
            config.tasks = config.tasks[1:] 
            if ct != name_of_waypoint:
                config.logger.debug("Task list in config and reported waypoint differ! %s vs %s" %(ct,name_of_waypoint))
            config.logger.debug("Task list is %s" %config.tasks)
            if len(config.tasks) > 0:
                config.plan = config.instruction_db.get_path(name_of_waypoint,config.tasks[0])
            if config.th_connected:
                comms.send_status("at-waypoint callback", "at-waypoint")
            else:
                rospy.loginfo("at-waypoint")
                rospy.loginfo(config.tasks_finished[-1])

        def active_cb():
            config.logger.debug("received notification that goal is active")

        def totally_done_cb(number_of_tasks_accomplished, locs):
            config.logger.debug("mission sequencer indicated that the robot is at goal")
            config.logger.debug("mission sequencer believes that the robot accomplished {0} tasks".format(number_of_tasks_accomplished))

            config.started = False
            if config.th_connected:
                comms.send_done("totally_done callback",
                                "mission sequencer indicated that the robot is at goal",
                                "at-goal")
            else:
                rospy.loginfo("Accomplished {0} tasks".format(number_of_tasks_accomplished))

        def done_cb(status, result):
            config.logger.debug("done cb was used from instruction graph")

        # Added multi-threading instead of multi-processing
        # because the subprocess could not connect to ig_process

        if config.level == "a" or config.level == "b":
            t = Thread(target=config.bot_cont.go_instructions_multiple_tasks_reactive,
                       args=(config.ready_response.start_loc,
                             config.ready_response.target_locs,
                             active_cb,
                             done_cb,
                             at_waypoint_cb,
                             totally_done_cb,
                             ))
        elif config.level == "c" or config.level == "d":
            t = Thread(target=config.bot_cont.go_instructions_multiple_tasks_adaptive,
                       args=(config.ready_response.start_loc,
                             config.ready_response.target_locs,
                             active_cb,
                             done_cb,
                             at_waypoint_cb,
                             totally_done_cb
                             ))

        # setting the battery to full charge before starting the mission
        rospy.loginfo("setting the initial charge right before starting the mission")
        full_charge = config.bot_cont.robot_battery.capacity
        print(full_charge)
        config.bot_cont.gazebo.set_charge(full_charge)

        startTime=config.sim_time
        # now everything is ready to start the mission
        t.start()
    else:
        return InlineResponse4003("/start called more than once")


def invoke_online_learning():
    """
    Invokes online learning. If there is no budget, or online learning is not 
    applicable in this test case, the return False. Otherwise start on-line
    learning in the background and return True (before learning has finished).
    THis lets the caller know that it should wait for a new model to become
    available
    """
    config.logger.debug("Invoking online learning")

    if config.learner.has_budget():
        thread_online_learning = Thread(name='online_learning', target=online_learning)

        thread_online_learning.start()

        return True
    else:
        return False

def online_learning():
    '''
        This funciton is called aynchoniously by invoke_online_learning()
    '''
    global config
    global comms

    config.logger.debug("online-learning-started")
    if config.th_connected:
        comms.send_status("default_controller", "online-learning-started", sendxy=True, sendtime=True)

    try:
        config.learner.start_online_learning()
    except Exception as e:
        config.logger.debug("online learning raised an exception; notifying the TH and then crashing")
        comms.save_ps("learning_error")
        if config.th_connected:

            ## copy out logs before posting error
            if config.uuid and config.th_connected:
                comms.sequester()

            config.thApi.error_post(Errorparams(error="learning-error", message="exception raised: %s" % e))
        else:
            rospy.logerr("learning-error")
        raise e

    config.logger.debug("online-learning-done")
    if config.th_connected:
        comms.send_status("default_controller", "online-learning-done", sendxy=True, sendtime=True)

    config.learner.update_config_files()

    # let's print the list of configurations the learner founds for debugging
    with open(config.learner.config_list_file, 'r') as confg_file:
        print("**Predicted**")
        config_data = json.load(confg_file)
        print(config_data)

    with open(config.learner.config_list_file_true, 'r') as confg_file:
        print("**True**")
        config_data = json.load(confg_file)
        print(config_data)
 
