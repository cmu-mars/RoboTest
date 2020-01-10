from threading import Lock
import subprocess
import time
import os
import rospy
import threading

RAINBOW_PATH = os.path.expanduser('~/das/rainbow-brass')
LD_PATH = os.path.expanduser('~/das/prism-4.3.1-linux64/lib')

class Command(object):
    def __init__(self, cmd):
        self.cmd = cmd
        self.process = None

    def run(self, timeout):
        def target():
            print(self.cmd)
            self.process = subprocess.Popen(self.cmd)
            self.process.communicate()

        thread = threading.Thread(target=target)
        thread.start()

        thread.join(timeout)
        if thread.is_alive():
            self.process.terminate()
            thread.join()
        return self.process.returncode


class RainbowInterface:
	# Class to manage interaction with Rainbow

    def __init__(self):
        self.processStarted = False
        self.lock = Lock()
        self.target = None

    def getTarget (self, challenge_problem):
        self.target=None
        if challenge_problem == "cp1":
            self.target="brass-p3-cp1"
        elif challenge_problem == "cp3":
            self.target="brass-p2-cp3"
        return self.target

    def startRainbow(self):
        with self.lock:
            if self.processStarted:
                rospy.logerr("Trying to start Rainbow when Rainbow is already running.")
            self.processStarted = True

        if (self.target is None):
            return True
        rospy.loginfo("Starting Rainbow (DAS)...")
        command = Command([RAINBOW_PATH+"/brass.sh", "-w", RAINBOW_PATH, "-s", self.target, os.path.expanduser("~/logs/rainbow-start.log")])
        ret = command.run(timeout=60)
        rospy.loginfo("Rainbow started, exit=%s"%str(ret))
        return ret == 0

    def launchRainbow(self, challenge_problem, log):
        """
        Starts Rainbow process. Needs to (a) start in background, (b) wait some time until it is up

        """

        print ("Configuring rainbow for %s"%challenge_problem)
        os.environ["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH"] + ":%s" %LD_PATH
        print ("LD_LIBRARY_PATH=%s" %os.environ["LD_LIBRARY_PATH"])
        self.target = self.getTarget(challenge_problem)

        rainbow_launch_process=[RAINBOW_PATH+"/run-oracle.sh", "-h", "-w", RAINBOW_PATH, self.target]
        if "RAINBOW_DEBUG_MODE" in os.environ.keys():
            if int(os.environ["RAINBOW_DEBUG_MODE"]) == 1:
                rainbow_launch_process=[RAINBOW_PATH+"/run-oracle.sh", "-d", "-h", "-w", RAINBOW_PATH, self.target]
                print('Rainbow will launch in debug mode, and wait for a debugger. If you do not have a debugger to attach, you are gonna see connection exceptions')
        if (self.target is not None):
            time.sleep(10)
            print("Starting %s" %' '.join(rainbow_launch_process))
            subprocess.Popen(rainbow_launch_process, stdout=log, env=os.environ)
            time.sleep(40)


    def stopRainbow(self):
        rospy.loginfo("Stopping Rainbow (DAS)...")
        ret = subprocess.call ([RAINBOW_PATH+"/brass.sh","-q", "-w", RAINBOW_PATH, self.target])
        with self.lock:
            self.processStarted = False
