import json
import random

testRanges = {
        "nTargets"      : (1, 10),
        "powerModelID"  : (0, 99),
        "nObstacles"    : (0, 10),
        "nBatterySets"  : (0, 30),
        "budget"        : (2, 1048576)}

perturbation_types = {
        "obstacle"  : ["op_easy", "op_medium", "op_hard"],
        "battery"   : ["bp_easy", "bp_medium", "bp_hard"]}

perturbation_severities = {
        "easy"      : [0, 0.1, 0.2],
        "medium"    : [0.3, 0.4, 0.5],
        "hard"      : [0.6, 0.7, 0.8]}

op_severities = {
        "op_easy"   : perturbation_severities["easy"],
        "op_medium" : perturbation_severities["medium"],
        "op_hard"   : perturbation_severities["hard"]}

def getRatioForOP(severity):
    return random.choice(op_severities[severity])


bp_severities = {
        "bp_easy"   : perturbation_severities["easy"],
        "bp_medium" : perturbation_severities["medium"],
        "bp_hard"   : perturbation_severities["hard"]}

def getRatioForBP(severity):
    return random.choice(bp_severities[severity])


def generate_list_of_perturbation_sequences(nTargets, obstacles, batterySets):
    if len(obstacles) != 3:
        raise ValueError("obstacles should be a dict of 3 elements, each of which represents the number of obstacel perturbations in the correpsonding severity level, easy, medium or hard.")

    if len(batterySets) != 3:
        raise ValueError("batterySets should be a dict of 3 elements, each of which represents the number of battery perturbations in the correpsonding severity level, easy, medium or hard.")


    nObstacles = 0
    obstaclePerturbations = []
    for key in obstacles:
        nObstacles += obstacles[key]
        for _ in range(obstacles[key]):
            obstaclePerturbations.append(key)

    if nObstacles > nTargets:
        raise ValueError("The number of obstacles is larger than the number of targets.")

    nBatterySets = 0 
    batteryPerturbations = []
    for key in batterySets:
        nBatterySets += batterySets[key]
        for _ in range(batterySets[key]):
            batteryPerturbations.append(key)


    perturbSeqs    = {}
    targetIDs           = []
    # initialize pertubation list for each target
    for num in range(1, nTargets+1):
        targetID = f"Target{num}"
        perturbSeqs[targetID] = []
        targetIDs.append(targetID)

    # distribute obstacle perturbations
    random.shuffle(obstaclePerturbations)
    tempTargetIDs = targetIDs.copy()
    for p in obstaclePerturbations:
        targetID= random.choice(tempTargetIDs)
        actualPerturbation = {"type": p, "ratio": getRatioForOP(p)}
        perturbSeqs[targetID].append(actualPerturbation)
        tempTargetIDs.remove(targetID)

    # distribute battery perturbations
    random.shuffle(batteryPerturbations)
    tempTargetIDs = targetIDs.copy()
    numBatteryPerturbationsPerTarget = {}
    for targetID in tempTargetIDs:
        numBatteryPerturbationsPerTarget[targetID] = 0
    for p in batteryPerturbations:
        while True:
            targetID= random.choice(tempTargetIDs)
            if numBatteryPerturbationsPerTarget[targetID] < 3:
                actualPerturbation = {"type": p, "ratio": getRatioForBP(p)}
                perturbSeqs[targetID].append(actualPerturbation)
                numBatteryPerturbationsPerTarget[targetID] += 1
                break
            else:
                tempTargetIDs.remove(targetID)

    

    '''
    # distribute battery perturbations
    random.shuffle(batteryPerturbations)
    curLeftBatterySets = nBatterySets
    start = 0 
    for num in range(1, nTargets):
        targetID = f"Target{num}"
        if curLeftBatterySets > 0:
            selectedNumOfBatterySets = random.randint(0, curLeftBatterySets)
            for b in batteryPerturbations[start:start+selectedNumOfBatterySets]:
                actualPerturbation = {"type": b, "ratio": getRatioForBP(b)}
                perturbSeqs[targetID].append(actualPerturbation)

            start = start + selectedNumOfBatterySets
            curLeftBatterySets -= selectedNumOfBatterySets
    # battery perturbations for the last target
    for b in batteryPerturbations[start:]:
        actualPerturbation = {"type": b, "ratio": getRatioForBP(b)}
        perturbSeqs[f"Target{nTargets}"].append(actualPerturbation)
    '''


    # shuffle the sequence of perturbations for each target
    for num in range(1, nTargets+1):
        targetID = f"Target{num}"
        random.shuffle(perturbSeqs[targetID])

    return perturbSeqs




class TestSpec():
    def __init__(self, testMap, level, startLoc, targetLocList, powerModelID, budget, obstacles, batterySets, perturbSeqs):

        if not testMap.is_waypoint(startLoc):
            raise ValueError("The start location ({}) is not in the list of waypoints.".format(startLoc))

        if len(targetLocList) == 0:
            raise ValueError("The list of target locations is empty!")

        for targetLoc in targetLocList:
            if not testMap.is_waypoint(targetLoc):
                raise ValueError("The target location, {}, is not the list of waypoints.".format(targetLoc))

        # It is meaningless if the first target location is set to be the start location.
        if targetLocList[0] == startLoc:
            raise ValueError("The first target location is set to be the start location.")

        if len(obstacles) != 3:
            raise ValueError("obstacles should be a dict of 3 elements, each of which represents the number of obstacel perturbations in the correpsonding severity level, easy, medium or hard.")

        if len(batterySets) != 3:
            raise ValueError("batterySets should be a dict of 3 elements, each of which represents the number of battery perturbations in the correpsonding severity level, easy, medium or hard.")

        nObstacles = 0
        obstacle_perturbations = []
        for key in obstacles:
            nObstacles += obstacles[key]

        nBatterySets = 0
        battery_perturbations = []
        for key in batterySets:
            nBatterySets += batterySets[key]


        self.testMap        = testMap
        self.nTargets       = len(targetLocList)
        self.startLoc       = startLoc
        self.targetLocList  = targetLocList
        self.powerModelID   = powerModelID
        self.nObstacles     = nObstacles
        self.obstacles      = obstacles
        self.nBatterySets   = nBatterySets
        self.batterySets    = batterySets
        self.budget         = budget
        self.level          = level

        self.rangeValidityCheck()
        if self.level != 'a': # case 'a' has perturbations
            self.perturbSeqs    = perturbSeqs
        else:
            self.perturbSeqs    = {} 


    def writeSpecToFile(self, filepath):
        spec = {"test_configuration": {}, "perturbation":{}}
        spec["test_configuration"]["level"]             = self.level
        spec["test_configuration"]["start-loc"]         = self.startLoc
        spec["test_configuration"]["target-locs"]       = self.targetLocList
        spec["test_configuration"]["power-model"]       = self.powerModelID
        spec["test_configuration"]["discharge-budget"]  = self.budget
        if self.level != 'a':
            spec["perturbation"]["nPerturbations"]  = self.nObstacles + self.nBatterySets
            spec["perturbation"]["Obstacles"]       = self.obstacles
            spec["perturbation"]["BatterySets"]     = self.batterySets
            spec["perturbation"]["perturbSeqs"]     = self.perturbSeqs

        with open(filepath, "w") as fp:
            json.dump(spec, fp, indent=4)    

    def isInRange(self, num, testRange):
        '''
            num: an integer
            testRange: a tuple of two elements, (lowerBound, upperBound)
        '''
        if num >= testRange[0] and num <= testRange[1]:
            return True
        else:
            return False

    def rangeValidityCheck(self):
        if not isinstance(self.nTargets, int) or not self.isInRange(self.nTargets, testRanges["nTargets"]):
            raise ValueError("The given value ({}) of 'nTargets' is either not an integer or not in the range [{}, {}]".format(
                self.nTargets, testRanges["nTargets"][0], testRanges["nTargets"][1]))
        elif not isinstance(self.powerModelID, int) or not self.isInRange(self.powerModelID, testRanges["powerModelID"]):
            raise ValueError("The given value ({}) of 'powerModelID' is either not an integer or not in the range [{}, {}]".format(
                self.powerModelID, testRanges["powerModelID"][0], testRanges["powerModelID"][1]))
        elif not isinstance(self.nObstacles, int) or not self.isInRange(self.nObstacles, (0, self.nTargets)): # at most one obstacel should be placed per target. Otherwise, the robot will fail to find alternative route.
            raise ValueError("The given value ({}) of 'nObstacles' is either not an integer or not in the range [{}, {}]".format(
                self.nObstacles, testRanges["nObstacles"][0], testRanges["nObstacles"][1]))
        elif not isinstance(self.nBatterySets, int) or not self.isInRange(self.nBatterySets, testRanges["nBatterySets"]):
            raise ValueError("The given value ({}) of 'nBatterySets' is either not an integer or not in the range [{}, {}]".format(
                self.nBatterySets, testRanges["nBatterySets"][0], testRanges["nBatterySets"][1]))
        elif not isinstance(self.budget, int) or not self.isInRange(self.budget, testRanges["budget"]):
            raise ValueError("The given value ({}) of 'budget' is either not an integer or not in the range [{}, {}]".format(
                self.budget, testRanges["budget"][0], testRanges["budget"][1]))

    #   ToDo
    #   Add some unit tests 
