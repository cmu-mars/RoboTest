import sys
import os
import random
import time
import datetime
import json
import copy

from mapserver import MapServer
from test_spec import TestSpec, testRanges, generate_list_of_perturbation_sequences, perturbation_severities

def usage():
    print("====================================================================================")
    print("python generate_test_set.py <map file> <test spec fold> <# of samples per region>")
    print("====================================================================================")


if len(sys.argv) != 4:
    usage()
    exit(1)

cp1_map_fp      = sys.argv[1]
test_spec_fold  = sys.argv[2]
num_samples_per_region = int(sys.argv[3])

map_server      = MapServer(cp1_map_fp)
waypoints       = list(map_server.get_waypoints()) # node-id of each waypoint
# exclude l11 and l12 from the list of waypoints 
waypoints.remove('l11')
waypoints.remove('l12')


def create_test_spec(separate_store, test_spec_fold, num_targets, power_model_ID, budget, levels, perturbations):
    '''
        separate_store: if True, store each case's test spec in test_spec_fold/case_level. 'case_level' is a value from 'levels' list
                        assume this subdirectory exists.
    '''
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
    perturbation_severity = perturbations["severity"]

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

        if perturbation_severity != None: 
            if level != 'a': # case a has no perturbation
                test_spec_fn = "{}_M{}_B{}_{}T_{}P.json".format(
                        level,
                        power_model_ID,
                        budget,
                        num_targets,
                        perturbation_severity)
            else:
                test_spec_fn = "{}_M{}_B{}_{}T.json".format(
                                        level,
                                        power_model_ID,
                                        budget,
                                        num_targets)
        else: # For complicated test design
            test_spec_fn = "{}_M{}_B{}_{}T_{}OP{}E{}M{}H_{}BP{}E{}M{}H.json".format(
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


        if separate_store:
            subfold = os.path.join(test_spec_fold, level)
            test_spec_fp = os.path.join(subfold, test_spec_fn)
        else:
            test_spec_fp = os.path.join(test_spec_fold, test_spec_fn)
        test_spec.writeSpecToFile(test_spec_fp)

# Test Space Split
#Suggested budget space
budget_space = [ 10, 50, 100, 500, 1000, 5000, 10000]
power_model_space = [
        list(range(0, 25)),
        list(range(25, 75)),
        list(range(75, 99))]
target_space = [
        [1, 2, 3],
        [4, 5, 6, 7],
        [8, 9, 10]]
perturbation_difficulty_space = ["Easy", "Medium", "Hard"]

# if it is desired to put all test specs of one case in one fold,
# please ensure the sub-dierctory 'test_spec_fold/<case_level>' is created by running this script.
levels = ['a', 'b', 'c', 'd']

# set up directory for storing test specification files
for level in levels:
    directory = os.path.join(test_spec_fold, level)
    if not os.path.exists(directory):
        os.makedirs(directory)    

# draw a list of 2-tuples: (power model ID, num of targets)
# Make each tuple's power model ID is different to ensure
# each tuple is different.
def draw_n_tuples(num_samples_per_region, power_model_range, num_targets_range):
    result = [[], []]
    for _ in range(num_samples_per_region):
        num_targets = random.choice(num_targets_range)
        result[1].append(num_targets)
        while True:
            pm_ID = random.choice(power_model_range)
            if pm_ID not in result[0]: # a new power model ID
                result[0].append(pm_ID)
                break
    return result
    

# A test squad for case a, b, c and d.
test_squads = []
# The following code pick ONE test sample from each of the splited range.
# Suggest to draw 3-5 test samples from each splited range.
for budget in budget_space:
    for pm_range in power_model_space:
        for num_targets_range in target_space:
            pm_targets_list = draw_n_tuples(num_samples_per_region, pm_range, num_targets_range)
            for sample_Idx in range(num_samples_per_region):
                pm_ID = pm_targets_list[0][sample_Idx]
                num_targets = pm_targets_list[1][sample_Idx]

                num_perturbation_difficulties = len(perturbation_difficulty_space)
                for perturbation_difficulty_idx in range(num_perturbation_difficulties):
                    perturbation_severity   = perturbation_difficulty_space[perturbation_difficulty_idx]
                    test = {}
                    test['levels']          = levels
                    test['num_targets']     = num_targets
                    test['power_model_ID']  = pm_ID
                    test['budget']          = budget
                    obstacle_perturbations  = [0] * num_perturbation_difficulties
                    obstacle_perturbations[perturbation_difficulty_idx] = 1 * (1+num_targets//4) # at most one battery perturbtion per task
                    battery_perturbations   = [0] * num_perturbation_difficulties
                    battery_perturbations[perturbation_difficulty_idx]  = 3 * (1+num_targets//4) # at most three battery perturbation per task
                    
                    test['perturbations']   = {
                            "severity"      : perturbation_severity,
                            "obstacles"     : obstacle_perturbations,
                            "battery_sets"  : battery_perturbations}
                    test_squads.append(test)

separate_store = True
# Create test spec for each test
for test in test_squads:
    create_test_spec(separate_store, test_spec_fold, **test)

