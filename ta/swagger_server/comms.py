import rospy
import subprocess
import os
import signal
import datetime
import sys
import traceback

from swagger_client.models.errorparams import Errorparams
from swagger_client.models.doneparams import Doneparams
from swagger_client.models.statusparams import Statusparams
import swagger_server.config as config


def sequester():
    if config.th_connected and config.uuid is not None:
        logdirs = ["/home/mars/cp1/",
                   "/home/mars/logs/"
                   ]

        err = False
        for ld in logdirs:
            config.logger.debug("Calling aws s3 cp %s %s/%s/ --recursive",ld,config.s3_bucket_url, config.uuid)
            res = subprocess.call(["aws", "s3", "cp", ld,
                                   config.s3_bucket_url + "/" + config.uuid + "/",
                                   "--recursive"])
            if not res == 0:
                err = True

        # if any of the directories can't be copied, this test should be invalidated
        if err:
            config.thApi.error_post(Errorparams(error="other-error",
                                         message="failed to sequester logs"))


def save_ps(src):
    with open(os.path.expanduser("~/logs/ps_%s_%s.log") % (src, datetime.datetime.now()), "w") as outfile:
        subprocess.call(["ps", "aux"], stdout=outfile)


def send_status(src, code, sendxy=True, sendtime=True):
    # optional in the API def and only send them if the robot's
    # been started, also sending time is optional
    try:
        x = -1.0
        y = -1.0
        if sendxy:
            x, y, ig1, ig2 = config.bot_cont.gazebo.get_bot_state()

        config.logger.debug("sending status %s from %s" % (code, src))
        dd = Statusparams(status=code,
                              x=x,
                              y=y,
                              charge=config.battery,
                              sim_time=config.sim_time,
                              plan=config.plan)
        if not sendtime:
            dd.charge = 0
            dd.sim_time = 0;
       
        rospy.loginfo(dd)
        config.logger.debug("Status message is %s" % dd)
        response = config.thApi.status_post(dd)

        config.logger.debug("response from TH to status: %s" % response)

    except Exception as e:
        config.logger.error("Got an error %s when sending status" % e)
        traceback.print_exc()

def kill_robot():
    for line in os.popen("ps ax | grep ros | grep -v grep"):
        fields = line.split()
        pid = fields[0]
        config.logger.info("Killing %s" %line)
        os.kill(int(pid),signal.SIGKILL)

def send_done(src, msg, outcome):
    try:
        save_ps("done")
        x, y, ig1, ig2 = config.bot_cont.gazebo.get_bot_state()

        # Shut down rainbow and the robot
        if config.rainbow is not None:
            config.logger.info("Stopping Rainbow")
            config.rainbow.stopRainbow()

        config.logger.info("Stopping robot")
        kill_robot()
        # right before posting, copy out all the logs
        sequester()
        

        config.logger.debug("sending done from %s" % src)

        response = config.thApi.done_post(Doneparams(x=x,
                                                     y=y,
                                                     charge=config.battery,
                                                     sim_time=config.sim_time,
                                                     tasks_finished=config.tasks_finished,
                                                     outcome=outcome,
                                                     message=msg))
        config.logger.debug("response from TH to done: %s" % response)

    except Exception as e:
        config.logger.error("Got an error %s when sending status" % e)
    config.logger.debug("Quitting TA and Robot - Bye")
    for line in os.popen("ps ax | grep swagger_server | grep -v grep"):
        fields = line.split()
        pid = fields[0]
        config.logger.info("Killing %s" %line)
        os.kill(int(pid),signal.SIGKILL)
