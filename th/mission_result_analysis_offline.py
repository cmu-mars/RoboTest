import os
import sys
import copy
import json
import re
import logging

# input paramters
# eval_dir
eval_dir        = sys.argv[1]
test_IDs = [o for o in os.listdir(eval_dir) if os.path.isdir(os.path.join(eval_dir,o))]

mission_result_file_check_fp        = os.path.join(eval_dir, "mission_result_file_check.txt")
collection_of_mission_result_fp     = os.path.join(eval_dir, "collection_of_mission_result.json")
evaluation_result_fp                = os.path.join(eval_dir, "evaluation_result.txt")

with open(mission_result_file_check_fp, "w") as mcfp, open(collection_of_mission_result_fp, "w") as cmrfp, open(evaluation_result_fp, "w") as erfp:
    collection_of_mission_result_json = {}
    evaluation_result_per_case = {
            "nTests"            : 0,
            "budget"            : 0,
            "usedBudget"        : 0,
            "nTargetsTried"     : 0,
            "nTargetsReached"   : 0,
            "simTimeCost"       : 0,
            "perturbation_stat" : {
                "num_perturbations_tried"           : 0,
                "num_successful_perturbations"      : 0,
                "num_successful_easy_perturbations" : 0,
                "num_successful_medium_perturbations" : 0,
                "num_successful_hard_perturbations" : 0}
            }
    evaluation_result = {
            "a" : copy.deepcopy(evaluation_result_per_case),
            "b" : copy.deepcopy(evaluation_result_per_case),
            "c" : copy.deepcopy(evaluation_result_per_case),
            "d" : copy.deepcopy(evaluation_result_per_case)                                       
            }

    try:
        for test_ID in test_IDs:
            cur_mission_result_filename = "mission_result_"+test_ID+".json"
            cur_mission_result_fp = os.path.join(eval_dir, test_ID+"/"+cur_mission_result_filename)
            if os.path.exists(cur_mission_result_fp):
                mcfp.write(cur_mission_result_fp+":\t1\n")
                with open(cur_mission_result_fp) as json_file:
                    usedBudget = 0
                    used_budget_FP = os.path.join(eval_dir, test_ID+"/used_budget")
                    if os.path.exists(used_budget_FP):
                        with open(used_budget_FP) as ubfp:
                            line = ubfp.readline()
                            usedBudget = int(line.rstrip())

                    data = json.load(json_file)
                    level = data["test_configuration"]['level']
                    evaluation_result[level]["usedBudget"] += usedBudget                       

                    collection_of_mission_result_json[test_ID] = data
                    evaluation_result[level]["simTimeCost"] += data["mission_done"]['sim_time'] - data["mission_start"]['sim_time'] 
                    evaluation_result[level]["budget"] += data["test_configuration"]["discharge-budget"]
                    evaluation_result[level]["nTargetsTried"] += data["num_targets_tried"] 
                    evaluation_result[level]["nTargetsReached"] += data["num_targets_reached"] 
                    evaluation_result[level]['nTests'] += 1

                    if "perturbation_stat" in data:
                        perturbation_result = data["perturbation_stat"]
                        evaluation_result[level]["perturbation_stat"]["num_perturbations_tried"] += perturbation_result["num_perturbations_tried"]
                        evaluation_result[level]["perturbation_stat"]["num_successful_perturbations"] += perturbation_result["num_successful_perturbations"]
                        evaluation_result[level]["perturbation_stat"]["num_successful_easy_perturbations"] += perturbation_result["num_successful_easy_perturbations"]
                        evaluation_result[level]["perturbation_stat"]["num_successful_medium_perturbations"] += perturbation_result["num_successful_medium_perturbations"]
                        evaluation_result[level]["perturbation_stat"]["num_successful_hard_perturbations"] += perturbation_result["num_successful_hard_perturbations"]


            else:
                mcfp.write(cur_mission_result_fp+":\t0\n")
    except Exception as e:
        logging.error("Error happened when processing the result of each mission: {}".format(e), exc_info=True)

    # End Process all missions' result and dump into a json file
    json.dump(collection_of_mission_result_json, cmrfp, indent=4)

    erfp_header_format = "Case\tnTests\tbudget\tusedBudget\tnTargetsTried\tnTargetsReached\tsimTimeCost(s)\tnPTried\tnSP\tnSEP\tnSMP\tSHP\n"
    erfp_content_format = "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n"
    erfp.write(erfp_header_format)
    for level,value in evaluation_result.items():
        nTests = value["nTests"]
        tempNTests = nTests
        if tempNTests == 0:
            tempNTests = 1 # avoid divided by zero
        evaluation_result[level]["budget"] = value["budget"] / tempNTests
        evaluation_result[level]["usedBudget"] = value["usedBudget"] / tempNTests
        evaluation_result[level]["nTargetsTried"] = value["nTargetsTried"] / tempNTests
        evaluation_result[level]["nTargetsReached"] = value["nTargetsReached"] / tempNTests
        evaluation_result[level]["simTimeCost"] = value["simTimeCost"] / tempNTests

        evaluation_result[level]["perturbation_stat"]["num_perturbations_tried"] = value["perturbation_stat"]["num_perturbations_tried"]
        evaluation_result[level]["perturbation_stat"]["num_successful_perturbations"] = value["perturbation_stat"]["num_successful_perturbations"]
        evaluation_result[level]["perturbation_stat"]["num_successful_easy_perturbations"] = value["perturbation_stat"]["num_successful_easy_perturbations"]
        evaluation_result[level]["perturbation_stat"]["num_successful_medium_perturbations"] = value["perturbation_stat"]["num_successful_medium_perturbations"]
        evaluation_result[level]["perturbation_stat"]["num_successful_hard_perturbations"] = value["perturbation_stat"]["num_successful_hard_perturbations"]


        erfp.write(erfp_content_format.format(
            level,
            nTests,
            evaluation_result[level]["budget"],
            evaluation_result[level]["usedBudget"],
            evaluation_result[level]["nTargetsTried"],
            evaluation_result[level]["nTargetsReached"],
            evaluation_result[level]["simTimeCost"],
            evaluation_result[level]["perturbation_stat"]["num_perturbations_tried"],
            evaluation_result[level]["perturbation_stat"]["num_successful_perturbations"],
            evaluation_result[level]["perturbation_stat"]["num_successful_easy_perturbations"],
            evaluation_result[level]["perturbation_stat"]["num_successful_medium_perturbations"],
            evaluation_result[level]["perturbation_stat"]["num_successful_hard_perturbations"]
            ))
