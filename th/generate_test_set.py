import sys
import os
import random
import time
import datetime
import json
import copy
import numpy as np

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


# If there is change, create_subfolds() and get_subfold_name() should be changed accordingly
def create_subfolds(test_spec_fold, budgets, perturbation_severities, power_model_complexities, target_num_levels, case_levels, draw_IDs):
    for draw_ID in draw_IDs:
        draw_fp = os.path.join(test_spec_fold, "Draw"+str(draw_ID))
        if not os.path.exists(draw_fp):
            os.makedirs(draw_fp)
        for budget in budgets:
            budget_fp = os.path.join(draw_fp, "B"+str(budget))
            if not os.path.exists(budget_fp):
                os.makedirs(budget_fp)
            for perturbation_severity in perturbation_severities:
                perturbation_fp = os.path.join(budget_fp, perturbation_severity+"_perturbation")
                if not os.path.exists(perturbation_fp):
                    os.makedirs(perturbation_fp)

def get_subfold_name(test_spec_fold, budget, perturbation_severity, power_model_complexity, target_num_level, case_level, draw_ID):
    fp = os.path.join(test_spec_fold, "Draw"+str(draw_ID))
    fp = os.path.join(fp, "B"+str(budget))
    fp = os.path.join(fp, perturbation_severity+"_perturbation")
    return fp



def find_level(ID, space):
    if ID in space[0]:
        return "Easy"
    elif ID in space[1]:
        return "Medium"
    else:
        return "Hard"



def create_test_spec(separate_store, test_spec_fold, num_targets, power_model_ID, budget, levels, perturbations, draw_ID):
    '''
        levels: list of case levels, [a, b, c, d]
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

    for case_level in levels:
        test_spec = TestSpec(
                map_server,
                case_level,
                start_loc,
                target_loc_list,
                power_model_ID,
                budget,
                obstacles,
                battery_sets,
                perturb_seqs)

        power_model_complexity = find_level(power_model_ID, power_model_space) 
        target_num_level = find_level(num_targets, target_space)
        test_spec_fn = "B{}_{}P_{}M{}_{}T{}_{}.json".format(
                budget,
                perturbation_severity,
                power_model_complexity,
                power_model_ID,
                target_num_level,
                num_targets,
                case_level)

        if separate_store:
            subfold_path = get_subfold_name(test_spec_fold, budget, perturbation_severity, power_model_complexity, target_num_level, case_level, draw_ID)
            test_spec_fp = os.path.join(subfold_path, test_spec_fn)
        else:
            test_spec_fp = os.path.join(test_spec_fold, test_spec_fn)
        test_spec.writeSpecToFile(test_spec_fp)

# Test Space Split
#Suggested budget space
#budget_space = [ 10, 50, 100, 500, 1000, 5000, 10000]
budget_space = [10, 25, 50, 100, 150, 200, 250]
#power_model_space = [
#        list(range(0, 25)),
#        list(range(25, 75)),
#        list(range(75, 99))]
power_model_space = [
        np.load("easy_power_model_IDs.npy").astype(np.int).tolist(),
        np.load("medium_power_model_IDs.npy").astype(np.int).tolist(),
        np.load("difficult_power_model_IDs.npy").astype(np.int).tolist(),
        ]
target_space = [
        [1, 2, 3],
        [4, 5, 6, 7],
        [8, 9, 10]]
perturbation_difficulty_space = ["Easy", "Medium", "Hard"]

# case levels
levels = ['a', 'b', 'c', 'd']

# draw a list of 2-tuples: (power model ID, num of targets)
# Make each tuple's power model ID is different to ensure
# each tuple is different.
def draw_n_tuples(num_samples_per_region, power_model_range, num_targets_range):
    result = [[], []]
    result[0] = np.random.choice(power_model_range, num_samples_per_region, replace=False)
    result[1] = np.random.choice(num_targets_range, num_samples_per_region)
    '''
    for _ in range(num_samples_per_region):
        num_targets = random.choice(num_targets_range)
        result[1].append(num_targets)
        while True:
            pm_ID = random.choice(power_model_range)
            if pm_ID not in result[0]: # a new power model ID
                result[0].append(pm_ID)
                break
    '''
    return result
    
# IDs of selected power models
selected_PM_IDs = np.zeros((3, num_samples_per_region))
# A test squad for case a, b, c and d.
test_squads = []
# The following code pick ONE test sample from each of the splited range.
# Suggest to draw 3-5 test samples from each splited range.
for budget in budget_space:
    for pm_range_ID in range(len(power_model_space)):
        pm_range = power_model_space[pm_range_ID]
        for num_targets_range in target_space:
            pm_targets_list = draw_n_tuples(num_samples_per_region, pm_range, num_targets_range)
            selected_PM_IDs[pm_range_ID] = pm_targets_list[0]
            for draw_ID in range(num_samples_per_region):
                pm_ID = pm_targets_list[0][draw_ID]
                num_targets = pm_targets_list[1][draw_ID]

                num_perturbation_difficulties = len(perturbation_difficulty_space)
                for perturbation_difficulty_idx in range(num_perturbation_difficulties):
                    perturbation_severity   = perturbation_difficulty_space[perturbation_difficulty_idx]
                    test = {}
                    test['draw_ID']        = draw_ID + 1 # make it as 1-based
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
if separate_store:
    # set up directory for storing test specification files
    draw_IDs = list(range(1, 1+num_samples_per_region))
    power_model_complexities = ["Easy", "Medium", "Hard"]
    target_num_levels = ["Easy", "Medium", "Hard"]
    create_subfolds(test_spec_fold, budget_space, perturbation_difficulty_space, power_model_complexities, target_num_levels, levels, draw_IDs)


# selected_PM_IDs: (3, num_samples_per_region)
# selected_PM_IDs[0]: easy power models
# selected_PM_IDs[1]: medium power models
# selected_PM_IDs[2]: hard power models
np.save(os.path.join(test_spec_fold, "selected_PM_IDs.npy"), selected_PM_IDs.astype(int))
selected_PM_IDs = selected_PM_IDs.astype(int)
print("Selected Power Models:")
print("Easy Models: {}".format(selected_PM_IDs[0]))
print("Medium Models: {}".format(selected_PM_IDs[1]))
print("Hard Models: {}".format(selected_PM_IDs[2]))

# Create test spec for each test
for test in test_squads:
    create_test_spec(separate_store, test_spec_fold, **test)

