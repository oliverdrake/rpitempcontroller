"""
Read DS18B20 temperature sensors using the w1-gpio bit banging
kernel driver (bundled with Occidentalis).
"""
import os
import threading
import collections
import time
import re
import logging

BASE_DIR = "/sys/bus/w1/devices/"
TEMPERATURE_READ_BUFFER_SIZE = 200
TIMEOUT = 20
log = logging.getLogger("tempcontrol.w1_gpio")

def poll_sensors(callback):
    """
    Look for any DS18B20 temperature sensors and call callback once
    for each sensor found with (timestamp, serial, temperature).
    If there is a CRC failure in the kernel driver, callback will
    not be called.
    """
    # Currently scanning the devices directory and creating new
    # sensor objects on every loop - not very efficient...
    # w1_slave seems like it either needs to be opened every time
    # you want a new reading, or you need to seek(0).
    dir_names = _look_for_devices(BASE_DIR)
    sensors = []
    for serial in dir_names:
        filename = os.path.join(BASE_DIR, serial, "w1_slave")
        reading = read_temperature(filename)
        if reading is not None:
            callback(time.time(), serial, reading)


def read_temperature(filename):
    with open(filename, 'r') as f:
        driver_output = f.read()
    return _parse_driver_output(driver_output)


def _look_for_devices(base_dir=BASE_DIR):
    """
    Look for DS18B20 devices as provided by the w1-gpio kernel
    driver.

    :param base_dir: defaults to /sys/bus/w1/devices
    """
    return [f for f in os.listdir(base_dir) if f.startswith("28")]


def _parse_driver_output(driver_output):
    """
    Driver output in a file named w1_slave is of the form:
    a4 01 4b 46 7f ff 0c 10 da : crc=da YES
    a4 01 4b 46 7f ff 0c 10 da t=26250
    The first row tells us whether there was a CRC error, if
    not we can assume the reading on the second row (milli
    degrees C) is correct.

    :return: Temperature reading if CRC check passed, 
        None otherwise.
    """
    RE = "(NO|YES)\s.*t=((-|)\d+)"
    match = re.search(RE, driver_output)
    if match:
        if match.group(1) == "NO":
            log.warning("One-wire CRC failure")
        else:
            return float(match.group(2)) / 1000.0
    else:
        log.warning("Invalid driver output: %s" % driver_output)
    return None
