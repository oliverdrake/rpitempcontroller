import os
from setuptools import setup

setup(
    name = "rpitempcontroller",
    version = "0.1",
    author = "Oliver Drake",
    author_email = "oliver@drake.ch",
    description = "Control multiple fermenters from a raspberry pi",
    license = "BSD",
    keywords = "raspberry, pi, homebrew",
    url = "https://github.com/oliverdrake/rpitempcontroller",
    packages=['tempcontrol'],
    long_description="",
    entry_points={
        'console_scripts': ['tempcontroller = tempcontrol.cmd:main',],
    }
)