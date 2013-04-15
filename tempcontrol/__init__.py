import time
import logging
import socket

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger("tempcontrol")

GRAPHITE_ADDRESS = ("127.0.0.1", 2003)
GRAPHITE_PATH = "fermentation."
LOG_TO_GRAPHITE = True


class Fermenter(object):
    """
    Store + manage the state of a fermenter - doesn't actually 
    drive fridges or heaters.
    """
    IDLE = 1
    HEATING = 2
    COOLING = 3
    def __init__(self, name, setpoint, gpio_pin, hysterisis=0.5):
        self.name = name
        self.setpoint = setpoint
        self.hysterisis = hysterisis
        self.gpio_pin = gpio_pin
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

    def __repr__(self):
        return "<%s(name:%s, set:%s, gpio:%d)>" % (self.__class__.__name__,
                                                   self.name, self.setpoint,
                                                   self.gpio_pin)


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

    def __init__(self, gpio_pin):
        self.gpio_pin = gpio_pin
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
                _gpio_output(self.gpio_pin, 1)

    def turn_off(self):
        if self._state != self.OFF:
            self.log.debug("Turning off")
            self._state = self.OFF
            _gpio_output(self.gpio_pin, 0)

    def __repr__(self):
        return "<%s(pin:%d)>" % (self.__class__.__name__, self.gpio_pin)


def update_fermenters(fermenters, temp, temp_serial):
    """
    Take in a DS18B20 temperature reading and update the corresponding
    fermenter - will simply return if the serial is not recognized.
    """
    if temp_serial not in fermenters:
        return
    fermenter = fermenters[temp_serial]
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
    Only supporting one fridge at the moment - assuming both fermenters
    are sharing it.
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
        gpio_pin = fermenter.gpio_pin
        if fermenter.state == Fermenter.HEATING:
            _gpio_output(gpio_pin, 1)
        else:
            _gpio_output(gpio_pin, 0)


def log_to_graphite(*metrics):
    log = logging.getLogger("log_to_graphite")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(GRAPHITE_ADDRESS)
        str_metrics = ["%s %2.2f %d" % metric for metric in metrics]
        sock.sendall("\n".join(str_metrics) + "\n")
    except socket.error:
        log.warning("Could not send metrics to: %s:%d" % GRAPHITE_ADDRESS)


def _gpio_output(pin, value):
    """ Wrapping Rpi.GPIO to make unit testing easier """
    assert value in [1, 0]
    import RPi.GPIO as GPIO
    return GPIO.output(pin, value)
