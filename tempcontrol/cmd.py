import argparse
import logging

from config import connect_to_rest_service, load_config

def main():
    """ Main entry point """
    log = logging.getLogger("tempcontrol.cmd.main")
    parser = argparse.ArgumentParser(description='Control one or more '
                                     'fermenters')
    parser.add_argument('django_server_url', metavar='url', type=str,
                        help='URL of a running django config server')
    parser.add_argument('server_name', metavar='server_name', type=str,
                        help='Our name')
    args = parser.parse_args()
    log.info("temp control server main")
    log.info("django server url: %s" % args.django_server_url)
    log.info("server (our) name: %s" % args.server_name)

    def load_config_():
        api = connect_to_rest_service(args.django_server_url)
        return load_config(api, args.server_name)
    main_loop(load_config_)


def main_loop(load_config):
    """
    Run the main loop for this daemon.

    :param load_config: Callable that returns a fermenters dict and
        a new fridge object. Will be called regularly to keep our daemon
        up to date.
    """
    log = logging.getLogger("tempcontrol.cmd.main_loop")
    while True:
        log.info("Starting main loop")
        log.debug("Updating config")
        fermenters, fridge = load_config()
