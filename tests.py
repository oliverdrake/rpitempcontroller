import time
import os
import mock
import socket
import httplib
from nose.tools import (assert_equal, assert_false, assert_not_equal,
                        assert_in)

from tempcontrol import (Fridge, update_fridge, Fermenter, update_fermenters,
                         update_heaters, log_to_graphite)
from tempcontrol.w1_gpio import poll_sensors
from tempcontrol.config import (connect_to_rest_service, load_config,
                                _load_cooler, _load_fermenters)


def test_Fermenter_state():
    setpoint = 20.0
    fermenter = Fermenter("uut", setpoint, 22, hysterisis=0.2)
    assert_equal(fermenter.temp, None)
    assert_equal(fermenter.state, Fermenter.IDLE)
    for temp, expected_state in ((19, Fermenter.HEATING),
                                 (19.79, Fermenter.HEATING),
                                 (19.99, Fermenter.HEATING),
                                 (20.00, Fermenter.IDLE),
                                 (20.20, Fermenter.IDLE),
                                 (20.21, Fermenter.COOLING),
                                 (20.00, Fermenter.COOLING),
                                 (19.99, Fermenter.IDLE)):
        fermenter.temp = temp
        err_msg = "temp: %2.2f, setpoint: %2.2f, state: %d, expected: %d" % \
            (temp, setpoint, fermenter.state, expected_state)
        assert_equal(fermenter.state, expected_state, err_msg)


def test_Fermenter_setpoint_None():
    fermenter = Fermenter("uut", setpoint=None, gpio_pin=22)
    fermenter.temp = 5
    assert_equal(fermenter.state, Fermenter.IDLE)


@mock.patch("tempcontrol._gpio_output")
def test_Fridge_off_waiting_off(output):
    fridge = Fridge(24)
    assert_equal(fridge.state, Fridge.OFF)
    fridge.turn_on()
    assert_equal(fridge.state, Fridge.WAITING)
    fridge.turn_off()
    assert_equal(fridge.state, Fridge.OFF)
    output.assert_called_with(24, 0)


@mock.patch("tempcontrol._gpio_output")
@mock.patch("time.time")
def test_Fridge_off_waiting_on(time_, output):
    time_.return_value = 0
    for i in range(2):
        output.reset_mock()
        fridge = Fridge(24)
        assert_equal(fridge.state, Fridge.OFF)
        fridge.turn_on()
        assert_equal(fridge.state, Fridge.WAITING)
        time_.return_value += float(Fridge.WAIT_TIME) / 2
        fridge.turn_on()
        assert_equal(fridge.state, Fridge.WAITING)
        assert_false(output.called)
        time_.return_value += Fridge.WAIT_TIME + 1
        fridge.turn_on()
        assert_equal(fridge.state, Fridge.ON)
        output.assert_called_once_with(24, 1)


@mock.patch("tempcontrol._gpio_output")
@mock.patch("time.time")
def test_Fridge_on_off(time_, output):
    time_.return_value = 0
    fridge = Fridge(24)
    fridge.turn_on()
    time_.return_value += Fridge.WAIT_TIME + 1
    fridge.turn_on()
    output.assert_called_with(24, 1)
    fridge.turn_off()
    output.assert_called_with(24, 0)


def test_update_fermenters():
    fermenters = {
        "28-000003ea31f4": Fermenter(name="one", setpoint=14, gpio_pin=22),
        "28-000003ea2bb0": Fermenter(name="two", setpoint=15, gpio_pin=23)
    }
    temp = 13
    for serial in ["28-000003ea31f4", "28-000003ea2bb0"]:
        update_fermenters(fermenters, temp, serial)
        fermenter = fermenters[serial]
        assert_equal(fermenter.temp, temp)


def test_update_fermenters_3ea1f5b_ignored():
    fermenters = {1: mock.Mock(), 2: mock.Mock()}
    update_fermenters(fermenters, 12, "28-000003ea1f5b")
    for fermenter in fermenters.values():
        assert_not_equal(fermenter.temp, 12)


def test_update_fermenters_unknown_serial_ignored():
    fermenters = {1: mock.Mock(), 2: mock.Mock()}
    update_fermenters(fermenters, 12, "28-000001234567")
    for fermenter in fermenters.values():
        assert_not_equal(fermenter.temp, 12)


@mock.patch("tempcontrol._gpio_output")
def test_update_heaters(output):
    HEATING, IDLE = Fermenter.HEATING, Fermenter.IDLE
    COOLING = Fermenter.COOLING
    for f1state, f2state in ((IDLE, HEATING),
                             (HEATING, IDLE),
                             (COOLING, HEATING)):
        output.reset_mock()
        fermenter1 = mock.Mock()
        fermenter2 = mock.Mock()
        fermenter1.state = f1state
        fermenter1.heater_id = 1
        fermenter2.state = f2state
        fermenter2.heater_id = 2
        fermenters = {1: fermenter1, 2: fermenter2}
        update_heaters(fermenters)
        for fermenter in fermenters.values():
            state = 1 if fermenter.state == HEATING else 0
            call = mock.call(fermenter.gpio_pin, state)
            assert_in(call, output.mock_calls)


@mock.patch("tempcontrol._gpio_output")
def test_update_fridge(output):
    HEATING, IDLE = Fermenter.HEATING, Fermenter.IDLE
    COOLING = Fermenter.COOLING
    for f1state, f2state in ((IDLE, COOLING),
                             (HEATING, IDLE),
                             (COOLING, COOLING),
                             (IDLE, COOLING)):
        output.reset_mock()
        fermenter1 = mock.Mock()
        fermenter2 = mock.Mock()
        fermenter1.state = f1state
        fermenter1.heater_id = 1
        fermenter2.state = f2state
        fermenter2.heater_id = 2
        fermenters = {1: fermenter1, 2: fermenter2}
        fridge = mock.Mock()
        update_fridge(fermenters, fridge)
        if COOLING in [f1state, f2state]:
            fridge.turn_on.assert_called_with()
        else:
            fridge.turn_off.assert_called_with()


@mock.patch("socket.socket")
def test_log_to_graphite(socket_):
    timestamp = time.time()
    metric_name = "test.metric.path"
    value = 23.4
    log_to_graphite((metric_name, value, timestamp))
    message = "%s %2.2f %d\n" % (metric_name, value, int(timestamp))
    socket_().sendall.assert_called_with(message)


@mock.patch("socket.socket")
def test_log_to_graphite_supresses_connection_error(socket_):
    socket_().connect.side_effect = socket.error
    try:
        log_to_graphite(time.time(), "", 2)
    except socket.error:
        assert False, "socket error not supressed"


@mock.patch("time.time")
@mock.patch("__builtin__.open")
@mock.patch("os.listdir")
def test_poll_sensors(listdir, open_, time_):
    listdir.return_value = ["28-1", "28-2", "28-3"]
    open_().__enter__().read.return_value = """
    a4 01 4b 46 7f ff 0c 10 da : crc=da YES
    a4 01 4b 46 7f ff 0c 10 da t=26250"""
    callback = mock.Mock()
    poll_sensors(callback)
    for serial in listdir():
        call = mock.call("/sys/bus/w1/devices/%s/w1_slave" % serial, 'r')
        assert_in(call, open_.mock_calls)
        call = mock.call(time_(), serial, 26.250)
        assert_in(call, callback.mock_calls)


@mock.patch("time.time")
@mock.patch("__builtin__.open")
@mock.patch("os.listdir")
def test_poll_sensors_crc_failure(listdir, open_, time_):
    listdir.return_value = ["28-1", "28-2", "28-3"]
    open_().__enter__().read.return_value = """
    a4 01 4b 46 7f ff 0c 10 da : crc=da NO
    a4 01 4b 46 7f ff 0c 10 da t=26250"""
    callback = mock.Mock()
    poll_sensors(callback)
    assert_false(callback.called)


@mock.patch("time.time")
@mock.patch("__builtin__.open")
@mock.patch("os.listdir")
def test_poll_sensors_invalid_driver_output(listdir, open_, time_):
    listdir.return_value = ["28-1", ]
    open_().__enter__().read.return_value = "invalid driver output"
    callback = mock.Mock()
    poll_sensors(callback)
    assert_false(callback.called)


@mock.patch("drest.TastyPieAPI")
def test_connect_to_rest_service(TastyPieAPI):
    api = connect_to_rest_service("http://1.2.3.4:8080")
    TastyPieAPI.assert_called_with("http://1.2.3.4:8080")
    assert_equal(api, TastyPieAPI())


def _mock_api(status, resource_name, objects=None, method="get"):
    api = mock.Mock()
    response = mock.Mock()
    response.status = httplib.OK
    if objects:
        response.data = {
            "objects": objects,
        }
    resource = getattr(api, resource_name)
    getattr(resource, method).return_value = response
    return api


def test__load_cooler():
    api = mock.Mock()
    response = mock.Mock()
    response.status = httplib.OK
    response.data = {"gpio_pin": 15}
    api.coolers.get.return_value = response
    fridge = _load_cooler(api)
    api.coolers.get.assert_called_with(1)
    assert_equal(fridge.gpio_pin, 15)


@mock.patch("tempcontrol.config.get_temp_probe")
@mock.patch("tempcontrol.config.get_fermentation_profile")
@mock.patch("tempcontrol.config.get_heater")
def test__load_fermenters(get_heater, get_fermentation_profile,
                          get_temp_probe):
    api = mock.Mock()
    configs = [{
        "profile": "http://profile",
        "heater": "http://heater1",
        "probe": "http://probe1",
        "name": "Fermenter1",
    }]
    fermenters = _load_fermenters(api, *configs)
    get_heater.assert_called_with(api, "http://heater1")
    get_fermentation_profile.assert_called_with(api, "http://profile")
    get_temp_probe.assert_called_with(api, "http://probe1")
    assert len(fermenters) == 1
    assert_equal(fermenters.keys(), [get_temp_probe()["serial"]])
    fermenter = fermenters[get_temp_probe()["serial"]]
    assert_equal(fermenter.name, "Fermenter1")


@mock.patch("tempcontrol.config._setup_gpio")
@mock.patch("tempcontrol.config.get_fermenter")
@mock.patch("tempcontrol.config._load_cooler")
@mock.patch("tempcontrol.config._load_fermenters")
def test_load_config(_load_fermenters, _load_cooler, get_fermenter,
                     _setup_gpio):
    api = mock.Mock()
    response = mock.Mock()
    response.status = httplib.OK
    response.data = {
        "objects": [{
            "fermenters": ["http://fermenter1"],
        }]
    }
    api.tempcontrolservers.get.return_value = response
    fermenters, fridge = load_config(api, "testserver")
    get_fermenter.assert_called_with(api, "http://fermenter1")
    _load_fermenters.assert_called_with(api, get_fermenter())
    _load_cooler.assert_called_with(api)
    pins = [f.gpio_pin for f in fermenters.values()]
    _setup_gpio.assert_called_with(fridge.gpio_pin, *pins)
    assert_equal(fermenters, _load_fermenters())
    assert_equal(fridge, _load_cooler())


class AlmostAlwaysTrue(object):
    """ https://gist.github.com/daltonmatos/3280885 """
    def __init__(self, total_iterations=1):
        self.total_iterations = total_iterations
        self.current_iteration = 0
 
    def __nonzero__(self):
        if self.current_iteration < self.total_iterations:
            self.current_iteration += 1
            return bool(1)
        return bool(0)
