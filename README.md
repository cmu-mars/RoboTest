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
1. Save logs to AWS S3 bucket
    ``` shell
    export AWS_ACCESS_KEY=<...> AWS_SECRET_ACCESS_KEY=<...>
    cd th
    CUR_EVAL_ID=<...> S3_PATH=<...> ./test_run.sh | tee stdout.log
    ```



