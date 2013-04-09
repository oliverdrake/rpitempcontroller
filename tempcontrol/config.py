"""
Poll the django server regularly using the REST API.
"""
import httplib
from urlparse import urljoin
from functools import partial

import drest
from tempcontrol import Fermenter, Fridge


def connect_to_rest_service(address):
    return drest.TastyPieAPI("http://%s:%d/api/v1/" % address)


def load_config(api, our_name):
    server_config = get_tempcontrolserver(api, our_name)
    fermenter_configs = [get_fermenter(api, uri)
                         for uri in server_config["fermenters"]]
    fermenters = _load_fermenters(api, *fermenter_configs)
    fridge = _load_cooler(api)
    output_pins = [f.gpio_pin for f in fermenters.values()]
    _setup_gpio(fridge.gpio_pin, *output_pins)
    return fermenters, fridge


def _load_cooler(api):
    """ Only supporting one fridge atm """
    response = api.coolers.get(1)
    assert response.status == httplib.OK
    config = response.data
    return Fridge(config["gpio_pin"])


def _load_fermenters(api, *configs):
    fermenters = {}
    for config in configs:
        profile_uri = config["profile"]
        if profile_uri:
            profile = get_fermentation_profile(api, profile_uri)
            setpoint, hysterisis = profile["setpoint"], profile["hysterisis"]
        else:
            setpoint, hysterisis = None, None
        heater = get_heater(api, config["heater"])
        temp_probe = get_temp_probe(api, config["probe"])
        fermenter = Fermenter(name=config["name"], setpoint=setpoint,
                              gpio_pin=heater["gpio_pin"],
                              hysterisis=hysterisis)
        fermenters[temp_probe["serial"]] = fermenter
    return fermenters        


def get_tempcontrolserver(api, our_name):
    response = api.tempcontrolservers.get(params=dict(name=our_name))
    assert response.status == httplib.OK
    objects = response.data["objects"]
    assert len(objects) == 1
    return objects[0]


def get_by_uri(api, uri, resource_name):
    response = getattr(api, resource_name).get_by_uri(uri)
    assert response.status == httplib.OK
    return response.data

get_fermenter = partial(get_by_uri, resource_name="fermenters")
get_heater = partial(get_by_uri, resource_name="heaters")
get_cooler = partial(get_by_uri, resource_name="coolers")
get_temp_probe = partial(get_by_uri, resource_name="tempprobes")
get_fermentation_profile = partial(get_by_uri,
                                   resource_name="fermentationprofiles")


def _setup_gpio(*output_pins):
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    for pin_number in output_pins:
        GPIO.setup(pin_number, GPIO.OUT)