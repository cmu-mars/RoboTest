#!/bin/bash

TARGET=brass-cp1
WD="."

MODE=start
while getopts :sqw: opt; do
  case $opt in
    s)
	  MODE=start
	  ;;
	q)
	  MODE=quit
	  ;;
  w)
    WD=$OPTARG
   esac
done
shift $((OPTIND-1))

if [[ "$#" -ge 1 ]]; then
  TARGET=$1
  shift
else
  echo "Warning: target not passed as a parameter, using $TARGET as default"
fi

cd $WD

# Check if rainbow.properties file exists
TARGET_DIR="targets/$TARGET"
if [ ! -d "$TARGET_DIR" ]; then
    echo "Error: target directory $TARGET_DIR" does not exist.
    exit 1
fi


if [ "$(uname)" == "Darwin" ]; then
  delim=":"
elif [ "$(expr substr $(uname -s) 1 5)" == "Linux" ]; then
  delim=":"
elif [ "$(expr substr $(uname -o) 1 6)" == "Cygwin" ]; then
  delim=";"
fi

if [[ "$MODE" == "start" ]]; then
  java -classpath "${delim}lib/*" -Drainbow.target=$TARGET org.sa.rainbow.gui.RainbowCommand start
elif [[ "$MODE" == "quit" ]]; then
  java -classpath "${delim}lib/*" -Drainbow.target=$TARGET org.sa.rainbow.gui.RainbowCommand quit
fi


 
