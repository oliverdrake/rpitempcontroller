rpitempcontroller
=================

Python Daemon that runs on a raspberry pi - can control two fermenters (heat + cool) via GPIO. 
Temperatures are read using DS18B20 one-wire temperature sensors using the w1-gpio kernel module.
Currently hard-wired according to my setup, planning to make this more generic in the future.
