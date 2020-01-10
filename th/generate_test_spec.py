import sys
import os
import random
import time
import datetime
import json
import copy

from mapserver import MapServer
from test_spec import TestSpec, testRanges, generate_list_of_perturbation_sequences

cp1_map_fp      = sys.argv[1]
test_spec_fold  = sys.argv[2]
map_server      = MapServer(cp1_map_fp)
waypoints       = list(map_server.get_waypoints()) # node-id of each waypoint
# exclude l11 and l12 from the list of waypoints 
for w in waypoints:
    if (w == "l11") or ( w == "l12"):
        waypoints.remove(w)

def create_test_spec(test_spec_fold, num_targets, power_model_ID, budget, levels, perturbations):
    global waypoints
    global map_server

    # Start location and target locations
    start_loc = random.choice(waypoints)
    # Waypoints could repeat in the list of targets
    # as long as they are not consective in the list.
    target_loc_list = []
    prev_loc = start_loc
    for _ in range(num_targets):
        candidate_target = prev_loc
        while candidate_target == prev_loc:
            candidate_target = random.choice(waypoints)
        target_loc_list.append(candidate_target)
        prev_loc = candidate_target


    # Perturbations
    num_obstacles_easy, num_obstacles_medium, num_obstacles_hard = perturbations['obstacles']
    num_obstacles = num_obstacles_easy + num_obstacles_medium + num_obstacles_hard
    obstacles = {
            "op_easy": num_obstacles_easy,
            "op_medium": num_obstacles_medium,
            "op_hard": num_obstacles_hard}

    num_battery_sets_easy, num_battery_sets_medium, num_battery_sets_hard = perturbations['battery_sets']
    num_battery_sets = num_battery_sets_easy + num_battery_sets_medium + num_battery_sets_hard
    battery_sets = {
            "bp_easy": num_battery_sets_easy,
            "bp_medium": num_battery_sets_medium,
            "bp_hard": num_battery_sets_hard}

    perturb_seqs = generate_list_of_perturbation_sequences(num_targets, obstacles, battery_sets)

    for level in levels:
        test_spec = TestSpec(
                map_server,
                level,
                start_loc,
                target_loc_list,
                power_model_ID,
                budget,
                obstacles,
                battery_sets,
                perturb_seqs)


        time_stamp=time.strftime("%Y-%m-%d_%H-%M-%S", time.gmtime())
        dt = datetime.datetime.strptime(time_stamp, "%Y-%m-%d_%H-%M-%S")
        time_stamp_secs = int(time.mktime(dt.timetuple()) * 1000)

        test_spec_fn = "TestID{}_{}_M{}_B{}_{}T_{}OP{}E{}M{}H_{}BP{}E{}M{}H.json".format(
                time_stamp_secs,
                level,
                power_model_ID,
                budget,
                num_targets,
                num_obstacles,
                num_obstacles_easy,
                num_obstacles_medium,
                num_obstacles_hard,
                num_battery_sets,
                num_battery_sets_easy,
                num_battery_sets_medium,
                num_battery_sets_hard)

        test_spec_fp = os.path.join(test_spec_fold, test_spec_fn)
        test_spec.writeSpecToFile(test_spec_fp)

tests = []
test={}
test['power_model_ID']  = 10
test['budget']          = 2019
test['levels']           = ["a", "b", "c", "d"]

# For a given number of targets, create five sample tests 
for num_targets in [1,2,3]:
    test['num_targets'] = num_targets

    # No perturbations
    test = copy.deepcopy(test)
    test['perturbations']   = {
            "obstacles": [0, 0, 0],
            "battery_sets": [0, 0, 0]}
    tests.append(test)

    # Only Battery perturbations
    test = copy.deepcopy(test)
    test['perturbations']   = {
            "obstacles": [0, 0, 0],
            "battery_sets": [1, 1, 1]}
    tests.append(test)

    # Only Obstacle perturbations
    test = copy.deepcopy(test)
    test['perturbations']   = {
            "obstacles": [0, 1, 0],
            "battery_sets": [0, 0, 0]}
    tests.append(test)

    # 1 Battery perturbation and 1 Obstacle perturbation
    test = copy.deepcopy(test)
    test['perturbations']   = {
            "obstacles": [0, 0, 1],
            "battery_sets": [0, 1, 0]}
    tests.append(test)

    # 4 Battery perturbation and 1 Obstacle perturbation
    test = copy.deepcopy(test)
    test['perturbations']   = {
            "obstacles": [],
            "battery_sets": [2, 1, 1]}
    if num_targets == 3:
        test['perturbations']["obstacles"] = [1,1,1]
    elif num_targets == 2:
        test['perturbations']["obstacles"] = [1,0,1]
    else: # 1
        test['perturbations']["obstacles"] = [0,1,0]
    tests.append(test)


#with open("check.json", "w") as fp:
#    json.dump(tests, fp, indent=4)

# Create test spec for each test
for test in tests:
    create_test_spec(test_spec_fold, **test)

