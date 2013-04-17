import argparse
import logging
import time

from tempcontrol.config import (connect_to_rest_service, load_config, teardown,
                                read_config_file)
from tempcontrol.w1_gpio import poll_sensors
from tempcontrol import update_fermenters, update_fridge, update_heaters

def main():
    """ Main entry point """
    log = logging.getLogger("tempcontrol.cmd.main")
    parser = argparse.ArgumentParser(description='Control one or more '
                                     'fermenters')
    parser.add_argument('config_file', metavar='config_file', type=str,
                        help='path to config file',
                        default='/etc/rpitempcontroller.conf')
    args = parser.parse_args()
    log.info("temp control server main")

    our_name, url = read_config_file(args.config_file)

    log.info("django server url: %s" % url)
    log.info("server (our) name: %s" % our_name)

    def load_config_():
        api = connect_to_rest_service(url)
        return load_config(api, our_name)
    main_loop(load_config_)


def main_loop(load_config):
    """
    Run the main loop for this daemon.

    :param load_config: Callable that returns a fermenters dict and
        a new fridge object. Will be called regularly to keep our daemon
        up to date.
    """
    log = logging.getLogger("tempcontrol.cmd.main_loop")
    log.info("Starting main loop")
    while True:
        log.debug("Updating config")
        fermenters, fridge = load_config()

        def temp_reading_callback(timestamp, serial, temp):
            update_fermenters(fermenters, temp, serial)
            update_heaters(fermenters)
            update_fridge(fermenters, fridge)
        try:
            poll_sensors(temp_reading_callback)
            time.sleep(30)
        finally:
            log.info("Tearing down")
            teardown(fermenters, fridge)
            log.info("Teardown complete")
    log.info("Main loop finished")

