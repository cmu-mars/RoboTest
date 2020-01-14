#! /bin/bash

# Environemnt variables passed in when running this script
#   AWS_ACCESS_KEY_ID
#   AWS_SECRET_ACCESS_KEY
#   S3_PATH: exclude the '/' character at the end such that logs could go to the correct location
#   TEST_ID: not needed for running for a list of tests
#   CUR_EVAL_ID: used to create a fold to store the entire logs for the evaluation

function remove_container_when_down() {
    local CONTAINER_NAME=$1
    local CONTAINER_ALIVE="true" # Assume it is available
    local left_time=60
    # Check if the container is down.
    while [ "${CONTAINER_ALIVE}" == "true" ]
    do
        echo -e "The ${CONTAINER_NAME} is alive. Wait for 5 seconds"
        sleep 5
        CONTAINER_ALIVE=$(docker inspect -f '{{.State.Running}}' ${CONTAINER_NAME})
        left_time=$((left_time - 5))
        if [ "${left_time}" -le 0 ]
        then
            echo -e "Waiting too long for ${CONTAINER_NAME} to shutdown. Kill it now."
            docker kill ${CONTAINER_NAME}
            break
        fi
    done

    echo -e "The ${CONTAINER_NAME} is down. Remove it."
    docker rm --force ${CONTAINER_NAME}
}

function monitor_th_shutdown(){
    local STD_LOG=$1
    local TH_SHUTDOWN_SIGNAL="server is shutting down"

    # monitor if the TH server in cp1_th is going to shutdown
    while :
    do
        if grep -q "${TH_SHUTDOWN_SIGNAL}" "${STD_LOG}"
        then
            echo -e "[Force to stop cp1_th container if the TH server shuts down itself for more than 120 seconds.]"
            break
        fi

        sleep 1
    done

    # count down 90 seconds and then force cp1_th to shutdown
    left_time=90
    while [ "${left_time}" -gt 0 ]
    do
      echo -e "\tCounting down: ${left_time} seconds"
      local CONTAINER_ALIVE=$(docker inspect -f '{{.State.Running}}' "cp1_th")
      if ! [ "${CONTAINER_ALIVE}" ]
      then
        return 0
      fi
      sleep 15
      left_time=$((left_time - 15))
    done

    # sthudown cp1_th
    echo -e "\tThe TH server is shutting for 120 seconds. It probably gets stuck. So force cp1_th container to stop."
    docker kill cp1_th
    docker kill cp1_ta
}

function monitor_ta_shutdown() {
    local TA_CONTAINER_NAME=cp1_ta
    local TH_CONTAINER_NAME=cp1_th

    local TA_ALIVE=
    # Check if TH is started
    while [ "${TA_ALIVE}" == "" ]
    do
        echo -e "The TA is not started. Wait for 3 seconds"
        sleep 3
        TA_ALIVE=$(docker ps -a | grep ${TA_CONTAINER_NAME})
    done

    echo "The TA is started."
    TA_ALIVE="true"

    # Check if TA is down.
    while [ "${TA_ALIVE}" == "true" ]
    do
        sleep 30
        TA_ALIVE=$(docker inspect -f '{{.State.Running}}' ${TA_CONTAINER_NAME})
    done

    echo -e "The TA is down, so shut down the TH if it does not goes down in 90 seconds"
    # count down 90 seconds and then force cp1_th to shutdown
    local left_time=90
    while [ "${left_time}" -gt 0 ]
    do
      echo -e "\tCounting down: ${left_time} seconds"
      local TH_ALIVE=$(docker inspect -f '{{.State.Running}}' "cp1_th")
      if ! [ "${TH_ALIVE}" ]
      then
        return 0
      fi
      sleep 15
      left_time=$((left_time - 15))
    done

    echo -e "Wating too long for ${TH_CONTAINER_NAME} to shutdown. So, kill it."
    docker kill ${TH_CONTAINER_NAME}
}


# Ensure the environmental variable S3_PATH not ending with '/'
S3_PATH=$(echo ${S3_PATH} | sed -e 's|/$||')
echo -e "S3_PATH is ${S3_PATH}"

# Create a fold in S3 to hold the result of this evaluation.
EXPERIMENT_DIR="experiment"
CUR_EVAL_DIR="${EXPERIMENT_DIR}/${CUR_EVAL_ID}"
MISSION_RESULTS_DIR="${CUR_EVAL_DIR}/mission_results"
mkdir -p "${CUR_EVAL_DIR}"
mkdir -p "${MISSION_RESULTS_DIR}"
echo "Evaluation" > "${CUR_EVAL_DIR}/ReadMe"
echo "Collection of Mission Results" > "${MISSION_RESULTS_DIR}/ReadMe"
aws s3 cp "${EXPERIMENT_DIR}/" ${S3_PATH} --recursive

# Download finished_tests file if it exists in S3 bucket.
# Any test ID listed in finished_tests file will be skipped.
FINISHED_TESTS_FN=finished_tests.txt
FINISHED_TESTS_FP=${CUR_EVAL_DIR}/${FINISHED_TESTS_FN}
aws s3 ls ${S3_PATH}/${CUR_EVAL_ID}/${FINISHED_TESTS_FN}
if [[ $? == 0 ]];
then
    echo "${FINISHED_TESTS_FN} exists in S3 bucket. Download it."
    aws s3 cp "${S3_PATH}/${CUR_EVAL_ID}/${FINISHED_TESTS_FN}" "${FINISHED_TESTS_FP}"
else
    echo "${FINISHED_TESTS_FN} does not exist. This is a brand new evaluation. Create the file."
    > ${FINISHED_TESTS_FP}
fi

# Obtain the list of test IDs
TEST_SPECS_DIR="tests"
declare TESTS_LIST=($(ls "${TEST_SPECS_DIR}" | sed -e 's|\.json||'))
TEST_RUN=$(($(cat ${FINISHED_TESTS_FP} | wc -l)+1))
for TEST_ID in "${TESTS_LIST[@]}"
do
    echo -e "\n[Checking if the test ${TEST_ID} has been run before]"
    if grep -Fxq "${TEST_ID}" "${FINISHED_TESTS_FP}"
    then
        echo -e "[Skipping the test ${TEST_ID}]"
        continue
    fi

    echo -e "[Running the test ${TEST_RUN}: ${TEST_ID}]"

    rm -f "./cp1/used_budget"
    echo "0" > "./cp1/used_budget"

    # Create a fold in S3 bucket for the current test
    TEST_SPEC=${TEST_ID}.json
    CUR_TEST_RESULT_DIR="${CUR_EVAL_DIR}/${TEST_RUN}/${TEST_ID}"
    mkdir -p "${CUR_TEST_RESULT_DIR}"
    cp "./${TEST_SPECS_DIR}/${TEST_SPEC}" "${CUR_TEST_RESULT_DIR}" 
    aws s3 cp "${CUR_EVAL_DIR}/${TEST_RUN}/" "${S3_PATH}/${CUR_EVAL_ID}/" --recursive
    
    # Run with the current test
    STD_LOG_FP="${CUR_TEST_RESULT_DIR}/stdout.log"
    > ${STD_LOG_FP}

    # Start a process to monitor the shutdown of the TH server
    monitor_th_shutdown "${STD_LOG_FP}" &
    th_monitoring_process_PID=$(echo "$!")
    echo -e "Start the process ${th_monitoring_process_PID} to monitor if the TH server is shuting down."

    monitor_ta_shutdown &
    ta_monitoring_process_PID=$(echo "$!")
    echo -e "Start the process ${ta_monitoring_process_PID} to monitor if the TA container is shuting down."

    S3_PATH=${S3_PATH}/${CUR_EVAL_ID} TEST_ID=${TEST_ID} TEST_SPEC=${TEST_SPEC} TH_LOG_LEVEL=${TH_LOG_LEVEL} TH_PORT=8081 TA_PORT=8080 docker-compose -f docker-compose-th.yml up | tee ${STD_LOG_FP}

    # The TA container is down, so kill the monitoring process
    echo -e "Kill the monitoring process ${ta_monitoring_process_PID}."
    kill -9 "${ta_monitoring_process_PID}"
    sleep 5 # wait for the monitoring process to be killed

    # The TH server is down, so kill the monitoring process
    echo -e "Kill the monitoring process ${th_monitoring_process_PID}."
    kill -9 "${th_monitoring_process_PID}"
    sleep 5 # wait for the monitoring process to be killed

    echo -e "[The mission is done.]"
    echo -e "[Upload the stdout.log for the test ${TEST_ID} to S3 bucket]"
    aws s3 cp ${STD_LOG_FP} "${S3_PATH}/${CUR_EVAL_ID}/${TEST_ID}/"

    echo -e "[Copy mission result file and used_budget file]"
    cp "./th_log/mission_result_${TEST_ID}.json" "${MISSION_RESULTS_DIR}"
    cp "./cp1/used_budget" "${MISSION_RESULTS_DIR}/used_budget_${TEST_ID}.txt"

    echo -e "[The test ${TEST_ID} is finished. Update ${FINISHED_TESTS_FP} file both locally and remotely in S3 bucket.]"
    echo "${TEST_ID}" >> "${FINISHED_TESTS_FP}"
    aws s3 cp "${FINISHED_TESTS_FP}" "${S3_PATH}/${CUR_EVAL_ID}/"

    # Cleanup
    echo -e "[The mission is done! Remove the CP1 TH and TA containers when they are shut down.]"
    remove_container_when_down cp1_ta 
    remove_container_when_down cp1_th

    # Save a local copy
    mv "./roslogs" "${CUR_TEST_RESULT_DIR}"
    mv "./logs" "${CUR_TEST_RESULT_DIR}" 
    mv "./th_log" "${CUR_TEST_RESULT_DIR}"

    # Set up for the next test
    mkdir -p "./roslogs"
    touch "./roslogs/.VERSION"
    mkdir -p "./logs"
    mkdir -p "./logs/prism"
    touch "./logs/prism/.VERSION"
    mkdir -p "./th_log"
    touch "./th_log/.VERSION"

    TEST_RUN=$((TEST_RUN+1))
done

#echo -e "\n[Analyze mission results]"
#python mission_result_analysis.py "${TEST_SPECS_DIR}" "${CUR_EVAL_DIR}"

#echo  -e "\n[Send evaluation result to S3 Bucket]"
#aws s3 cp "${CUR_EVAL_DIR}/collection_of_mission_result.json" "${S3_PATH}/${CUR_EVAL_ID}/"
#aws s3 cp "${CUR_EVAL_DIR}/evaluation_result.txt" "${S3_PATH}/${CUR_EVAL_ID}/"
#aws s3 cp "${CUR_EVAL_DIR}/mission_result_file_check.txt" "${S3_PATH}/${CUR_EVAL_ID}/"
aws s3 cp "${MISSION_RESULTS_DIR}/" "${S3_PATH}/${CUR_EVAL_ID}/mission_results/" --recursive
