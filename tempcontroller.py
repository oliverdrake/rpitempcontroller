#!/usr/bin/env python
"""
Custom script for my specific fermentation setup: one fridge that's
big enough to hold 2 fermenters - each fermenter has it's own
heatpad but they share the fridge driver for cooling.
Temp sensors are DS18B20s, read using the rpi w1 gpio kernel driver.
"""
import time
import logging
import logging.config
import RPi.GPIO as GPIO

from tempcontrol import (Fermenter, Fridge, OUTPUTS, update_fermenters,
                         update_heaters, update_fridge)
from tempcontrol.w1_gpio import poll_sensors

logging.config.dictConfig({
    'version': 1,
    'root': {
        'level': 'DEBUG',
        'handlers': ['file', ],
    },
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'detailed',
            'filename': '/var/log/tempcontroller.log',
            'mode': 'a',
            'maxBytes': 1000000,
            'backupCount': 5,
        },
    },
    'formatters': {
        'detailed': {
            'format': '%(asctime)s %(module)-17s line:%(lineno)-4d ' \
            '%(levelname)-8s %(message)s',
        },
    },
})
log = logging.getLogger("tempcontroller")


def setup_fermenters():
    """ Keyed by temp sensor id """
    return {
        1: Fermenter("fermenter1", setpoint=20.5, heater_id=1, hysterisis=0.3),
        2: Fermenter("fermenter2", setpoint=None, heater_id=2),
    }

if __name__ == "__main__":
    log.info("Starting temp controller")

    # Outputs:
    GPIO.setmode(GPIO.BCM)
    for pin_number in OUTPUTS:
        GPIO.setup(pin_number, GPIO.OUT)

    fridge = Fridge()
    fermenters = setup_fermenters()

    def temp_reading_callback(timestamp, serial, temp):
        update_fermenters(fermenters, temp, serial)
        update_heaters(fermenters)
        update_fridge(fermenters, fridge)

    try:
        while True:
            poll_sensors(temp_reading_callback)
            time.sleep(10)
    finally:
        for pin_number in OUTPUTS:
            GPIO.output(pin_number, 0)
        log.info("Temp controller finished")
