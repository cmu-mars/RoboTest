# RoboTest
The test infrastructure contains test assitant and test harness.

## Building the system under test
1. Pull down cmumars/cp1_base

2. Build `cmumars/p3-cp1_rb`:

    ``` shell
    cd rainbow-planner
    docker build -t cmumars/p3-cp1_rb .
    ```
## Building test assistant and test harness
1. Build `cmumars/cp1_ta`:

    ``` shell
    cd ta
    docker build -t cmumars/cp1_ta .
    ```

2. Build `cmumars/cp1_th`:

    ``` shell
    cd th
    docker build -t cmumars/cp1_th .
    ```

## Create a test set 
1. Create test spectifications by using 'th/generate_test_set.py' and have them placed in the directory, 'th/tests'


## Run these tests
1. Run in cloud and save logs to AWS S3 bucket
    ``` shell
    cd th
    CUR_EVAL_ID=<...> SAVE_LOG_LOCALLY=False S3_PATH=<...> AWS_ACCESS_KEY=<...> AWS_SECRET_ACCESS_KEY=<...> ./test_run.sh | tee stdout.log
    ```

2. Run a controlled machine and save logs locally there
    ``` shell
    cd th
    CUR_EVAL_ID=<...> SAVE_LOG_LOCALLY=True ./test_run.sh | tee stdout.log
    ```

