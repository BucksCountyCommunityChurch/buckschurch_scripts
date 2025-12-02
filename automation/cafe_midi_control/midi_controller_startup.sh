#!/bin/sh

APP_DIR=/app
SCRIPTS_REPO=$APP_DIR/buckschurch_scripts
MIDI_PATH=$SCRIPTS_REPO/automation/cafe_midi_control


#echo ---- Refreshing the Git repo ----
#cd $SCRIPTS_REPO
#git pull

echo ---- Setting up the Virtual Environment ----
if ! [ -e $APP_DIR/venv ] ; then
        cd $APP_DIR
        python -m venv venv
fi

echo ---- Loading the Virtual Environment ----
. $APP_DIR/venv/bin/activate

#echo ---- Getting the required python packages ----
#if [ -e $MIDI_PATH/requirements.txt ] ; then
#        pip install -r $MIDI_PATH/requirements.txt
#fi

echo ---- Running the controller ----
cd $MIDI_PATH
python midi_listener.py -c $MIDI_PATH/listener_config.yaml
