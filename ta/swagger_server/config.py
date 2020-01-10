# response from /ready
ready_response = None

# connection to the API
thApi = None

# current battery level, updated by call back to the ros topic
# The default value 0 is used by status message before the robot is alive
battery = 0

# has the /start endpoint been hit once? this lets us fail on multiple
# starts
started = False

# logger from main
logger = None

# bot controller
bot_cont = None

# level
level = None

# waypoints for done message
tasks_finished = []

# for testing without th
th_connected = False

## for log sequestration
uuid = None
s3_bucket_url = None

# to facilitate online DQN learning
learner = None

# Rainbow
rainbow = None

plan = ""

# The default value is used by status message before the robot is alive
sim_time = 0
