import time
import os
import mock
import socket
from nose.tools import (assert_equal, assert_false, assert_not_equal,
                        assert_in)

from tempcontrol import (Fridge, update_fridge,
                         Fermenter, update_fermenters,
                         update_heaters, log_to_graphite,
                         TEMP_SENSORS, HEAT_PIN_MAPPING)
from tempcontrol.w1_gpio import poll_sensors


TEMP_SENSOR_SERIALS = {
    1: "28-000003ea31f4",
    2: "28-000003ea2bb0",
}


def test_Fermenter_state():
    setpoint = 20.0
    fermenter = Fermenter("uut", setpoint, 1, hysterisis=0.2)
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
    fermenter = Fermenter("uut", setpoint=None, heater_id=1)
    fermenter.temp = 5
    assert_equal(fermenter.state, Fermenter.IDLE)


@mock.patch("tempcontrol._gpio_output")
def test_Fridge_off_waiting_off(output):
    fridge = Fridge()
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
        fridge = Fridge()
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
    fridge = Fridge()
    fridge.turn_on()
    time_.return_value += Fridge.WAIT_TIME + 1
    fridge.turn_on()
    output.assert_called_with(24, 1)
    fridge.turn_off()
    output.assert_called_with(24, 0)


def test_update_fermenters():
    fermenters = {
        1: Fermenter(name="one", setpoint=14, heater_id=1),
        2: Fermenter(name="two", setpoint=15, heater_id=2)
    }
    temp = 13
    for sensorid, serial in TEMP_SENSOR_SERIALS.items():
        update_fermenters(fermenters, temp, serial)
        fermenter = fermenters[sensorid]
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
            pin = HEAT_PIN_MAPPING[fermenter.heater_id]
            state = 1 if fermenter.state == HEATING else 0
            call = mock.call(pin, state)
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
    socket_().sendall.assert_called_with("%s %2.2f %d\n" % (metric_name,
        value, int(timestamp)))


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
