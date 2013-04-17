import os
from functools import partial

from fabric.api import env, run, require, sudo, put
from fabric.contrib.files import exists
from fabtools.python import (virtualenv, install_pip, is_pip_installed,
                             install, install_requirements)

env.install_location = "/usr/lib/rpitempcontroller"
join_local = partial(os.path.join, os.path.dirname(__file__))


def garagepi():
    env.user = "pi"
    env.password = "raspberry"
    env.host_string = "192.168.0.207"


def deploy():
    require("install_location")
    sudo("mkdir -p %(install_location)s" % env)
    if not is_pip_installed():
        install_pip()
    install("virtualenv", use_sudo=True)
    put(join_local("pip-requirements.txt"), "/tmp/pip-requirements.txt")
    with _virtualenv():
        install_requirements("/tmp/pip-requirements.txt", use_sudo=True)
        sudo("pip install -e git+https://github.com/oliverdrake/rpitempcontroller.git#egg=tempcontrol")


def _virtualenv():
    require("install_location")
    path = os.path.join(env.install_location, "ve")
    if not exists(path):
        sudo("virtualenv %s" % path)
    return virtualenv(path)

