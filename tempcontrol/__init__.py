import time
import logging
import socket
import RPi.GPIO as GPIO

HEAT_1_GPIO_PIN = 22
HEAT_2_GPIO_PIN = 23
COOL_GPIO_PIN = 24
OUTPUTS = (HEAT_1_GPIO_PIN, HEAT_2_GPIO_PIN, COOL_GPIO_PIN)

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger("tempcontrol")

GRAPHITE_ADDRESS = ("192.168.0.207", 2003)
GRAPHITE_PATH = "fermentation."
LOG_TO_GRAPHITE = True

# Sensors 1 + 2 should be tied to fermenters that are hooked up
# to heaters 1 + 2 respectively. Sensor 3 can be used for general
# measurement.
TEMP_SENSORS = {
    "28-000003ea31f4": 1,
    "28-000003ea2bb0": 2,
    "28-000003ea1f5b": 3,
}

# Map heater ids to GPIO pins:
HEAT_PIN_MAPPING = {
    1: HEAT_1_GPIO_PIN,
    2: HEAT_2_GPIO_PIN,
}


class Fermenter(object):
    """
    Store + manage the state of a fermenter - doesn't actually 
    drive fridges or heaters.
    """
    IDLE = 1
    HEATING = 2
    COOLING = 3
    def __init__(self, name, setpoint, heater_id, hysterisis=0.5):
        assert heater_id in HEAT_PIN_MAPPING
        self.name = name
        self.setpoint = setpoint
        self.hysterisis = hysterisis
        self.heater_id = heater_id
        self.temp = None
        self._state = self.IDLE
        logger_name = "tempcontrol.Fermenter.%s" % name
        self.log = logging.getLogger(logger_name)

    @property
    def state(self):
        IDLE, HEATING, COOLING = self.IDLE, self.HEATING, self.COOLING
        if self.temp is None or self.setpoint is None:
            self._state = IDLE
        elif self.temp < (self.setpoint - self.hysterisis):
            self._state = HEATING
        elif self.temp < self.setpoint:
            if self._state == COOLING:
                self._state = IDLE
        elif self.temp >= self.setpoint and \
                self.temp <= (self.setpoint + self.hysterisis):
            if self._state == HEATING:
                self._state = IDLE
        elif self.temp > (self.setpoint + self.hysterisis):
            self._state = COOLING
        else:
            # Shouldn't be possible...
            raise RuntimeError("%2.2f, %2.2f %d" % (self.temp, 
                self.setpoint, self._state))
        return self._state


class Fridge(object):
    """
    Manage the state machine for the fridge + drive io pins
    appropriately. There's a compressor delay that must expire
    before calling turn_on() will actually turn the fridge on,
    this is to protect the compressor from burning out.
    """
    OFF = 1
    WAITING = 2
    ON = 3
    WAIT_TIME = 60  # (seconds) to protect the compressor

    def __init__(self):
        self._state = self.OFF
        self._wait_start = None
        self.log = logging.getLogger("tempcontrol.Fridge")

    @property
    def state(self):
        return self._state

    def turn_on(self):
        if self._state == self.OFF:
            assert self._wait_start is None
            self._wait_start = time.time()
            self.log.debug("Waiting %d seconds" % self.WAIT_TIME)
            self._state = self.WAITING
        elif self._state == self.WAITING:
            assert self._wait_start is not None
            if (time.time() - self._wait_start) > self.WAIT_TIME:
                self.log.debug("Turning on")
                self._state = self.ON
                GPIO.output(COOL_GPIO_PIN, 1)

    def turn_off(self):
        if self._state != self.OFF:
            self.log.debug("Turning off")
            self._state = self.OFF
            GPIO.output(COOL_GPIO_PIN, 0)


def update_fermenters(fermenters, temp, temp_serial):
    """
    Take in a DS18B20 temperature reading and update the corresponding
    fermenter - will simply return if the serial is not recognized.
    """
    if temp_serial not in TEMP_SENSORS:
        return
    sensor_id = TEMP_SENSORS[temp_serial]
    if sensor_id not in [1, 2]:
        return
    fermenter = fermenters[sensor_id]
    fermenter.temp = temp
    if LOG_TO_GRAPHITE and fermenter.setpoint is not None:
        path = GRAPHITE_PATH + fermenter.name
        metrics = ((path + ".temp", fermenter.temp, time.time()),
                   (path + ".setpoint", fermenter.setpoint, time.time()),
                   (path + ".heating",
                    float(fermenter.state is fermenter.HEATING),
                    time.time()),
                   (path + ".cooling",
                    float(fermenter.state is fermenter.COOLING),
                    time.time()))
        log_to_graphite(*metrics)


def update_fridge(fermenters, fridge):
    """
    Turn fridge on if any of the fermenters need it - only turn
    the fridge off if none of the fermenters need it.
    """
    states = [fermenter.state for fermenter in fermenters.values()]
    if Fermenter.COOLING in states:
        fridge.turn_on()
    else:
        fridge.turn_off()


def update_heaters(fermenters):
    """
    Turn heaters on/off for each fermenter depending upon the
    fermenter's state.
    """
    for fermenter in fermenters.values():
        gpio_pin = HEAT_PIN_MAPPING[fermenter.heater_id]
        if fermenter.state == Fermenter.HEATING:
            GPIO.output(gpio_pin, 1)
        else:
            GPIO.output(gpio_pin, 0)


def log_to_graphite(*metrics):
    log = logging.getLogger("log_to_graphite")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(GRAPHITE_ADDRESS)
        str_metrics = ["%s %2.2f %d" % metric for metric in metrics]
        sock.sendall("\n".join(str_metrics))
    except socket.error:
        log.warning("Could not send metrics to: %s:%d" % GRAPHITE_ADDRESS)
