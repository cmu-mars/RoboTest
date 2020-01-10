#! /bin/bash

TH_CONTAINER_NAME=cp1_th
TA_CONTAINER_NAME=cp1_ta
TH_ALIVE= # not alive initially


# Check if TH is started
while [ "${TH_ALIVE}" == "" ]
do
    echo -e "The TH is not started. Wait for 3 seconds"
    sleep 3
    TH_ALIVE=$(docker ps -a | grep ${TH_CONTAINER_NAME})
done

echo "The TH is started."
TH_ALIVE="true"

# Check if TH is down.
while [ "${TH_ALIVE}" == "true" ]
do
    echo -e "The TH is alive. Wait for 3 seconds"
    sleep 3
    TH_ALIVE=$(docker inspect -f '{{.State.Running}}' ${TH_CONTAINER_NAME})
done



echo -e "The TH is down, so shut down the TA"
docker container stop ${TA_CONTAINER_NAME}

# Remove CP1 TH and TA docker containers such that
# the next test could have a clean start
#echo -e "Remove CP1 TH and TA docker containers"
#docker container rm ${TA_CONTAINER_NAME}
#docker container rm ${TH_CONTAINER_NAME}

DANGLING_IMAGES=$(docker images -f "dangling=true" -q)
if [ "${DANGLING_IMAGES}" == "" ]
then
    echo "No dangling docker images."
else
    echo "Has dangling docker images. Removing them now."
    docker rmi ${DANGLING_IMAGES}
fi
