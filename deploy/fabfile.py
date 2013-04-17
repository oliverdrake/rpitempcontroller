import os
from functools import partial

from fabric.api import env, run, require, sudo, put
from fabric.context_managers import settings
from fabric.contrib.files import exists, upload_template
from fabtools.python import (virtualenv, install_pip, is_pip_installed,
                             install, install_requirements)

env.install_location = "/usr/lib/rpitempcontroller"
env.config_file = "/etc/rpitempcontroller.conf"
env.init_script = "/etc/init.d/tempcontroller"
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
    put("tempcontroller-config.default", env.config_file, use_sudo=True,
        mirror_local_mode=True)
    with settings(python_bin_dir=os.path.join(_virtualenv_location(), "bin")):
        upload_template("init-script.in", env.init_script, mode=0754,
                        use_jinja=True, context=env, use_sudo=True,
                        backup=False)
    sudo("chown root:root %(init_script)s" % env)


def _virtualenv_location():
    return os.path.join(env.install_location, "ve")

def _virtualenv():
    require("install_location")
    path = _virtualenv_location()
    if not exists(path):
        sudo("virtualenv %s" % path)
    return virtualenv(path)

