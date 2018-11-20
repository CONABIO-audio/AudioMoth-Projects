#!/usr/bin/env python

import struct
import json
import os
import argparse
from subprocess import Popen, PIPE
import time as dtime



CMD = 'usbhidtool'
OS = 'linux'

VID = "0x10c4"
PID = "0x0002"

AM_USBAPP_GET = "0x05"
AM_SUBAPP_SET = "0x06"
AM_USBAPP_GET_TIME_SCHEDULE = "0x09"
AM_USBAPP_SET_TIME_SCHEDULE = "0x10"

AM_FIRMWARE_VERSION_LENGTH = 3
AM_FIRMWARE_DESCRIPTION_LENGTH = 32
AM_UNIQUE_ID_LENGTH = 8
AM_TIME_LENGTH = 4
AM_BATTERY_STATE_LENGTH = 1

CONFIG_PATH = './config.json'
CONFIGURATIONS_PATH = './configurations.json'
TIME_SCHEDULE_PATH = './time_schedule.json'

DEFAULT_CONFIG = {}
CONFIGURATIONS = {}
TIME_SCHEDULE = {}

FLAGS = None


def load_config():
    with open(CONFIG_PATH, 'r') as jsonfile:
        config = json.load(jsonfile)
    return config

def load_time_schedule():
    with open(TIME_SCHEDULE_PATH, 'r') as jsonfile:
        config = json.load(jsonfile)
    return config

def load_configurations():
    with open(CONFIGURATIONS_PATH, 'r') as jsonfile:
        configs = json.load(jsonfile)
    return configs


def get_part(arr, size, start):
    return arr[start: start + size], start + size


def hex_arr_to_int(arr, be=False):
    string = ''.join(map(lambda x: chr(int(x, 16)), arr))

    length = len(string)
    if length == 1:
        fmt = 'B'
    elif length == 2:
        fmt = 'H'
    elif length == 4:
        fmt = 'L'
    elif length == 8:
        fmt = 'Q'

    if be:
        fmt = '>' + fmt
    else:
        fmt = '<' + fmt

    value = struct.unpack(fmt, string)[0]
    return value

def hex_arr_to_float(arr, be=True):
    string = ''.join(map(lambda x: chr(int(x, 16)), arr))
    value = struct.unpack('f', string)[0]
    return value


def hex_arr_to_bool(arr, be=False):
    string = ''.join(map(lambda x: chr(int(x, 16)), arr))
    value = struct.unpack('?', string)[0]
    return value


def struct_field(dic, key, fmt):
    value = dic[key]
    return struct_value(value,fmt)

def struct_value(value,fmt):
    value_str = struct.pack(fmt,value)
    return ['0x{:02x}'.format(ord(x)) for x in value_str[::-1]]


def struct_config(config):
    result = [AM_SUBAPP_SET]
    result += struct_field(config, 'time', '>L')
    result += struct_field(config, 'gain', 'B')
    result += struct_field(config, 'clockDivider', 'B')
    result += struct_field(config, 'acquisitionCycles', 'B')
    result += struct_field(config, 'oversampleRate', 'B')
    result += struct_field(config, 'sampleRate', '>L')
    result += struct_field(config, 'sampleRateDivider', 'B')

    result += struct_field(config, 'sleepDuration', '>H')
    result += struct_field(config, 'recordDuration', '>H')
    result += struct_field(config, 'enableLED', '?')
    result += struct_field(config, 'activeStartStopPeriods', 'B')

    result += struct_field(config, 'timezone', 'B')
    result += struct_field(config, 'useFilter', '?')
    result += struct_field(config, 'goertzelFreq', '>L')
    result += struct_field(config, 'goertzelThresh', '>f')
    result += struct_field(config, 'goertzelFactor', '>f')

    return result

def struct_time_schedule(config):
    result = [AM_USBAPP_SET_TIME_SCHEDULE]
    periods = config["startStopPeriods"]
    for p in periods:
        result += struct_value(p["startMinutes"],'>H')
        result += struct_value(p["stopMinutes"],'>H')
    return result

def parse_config(packet):
    packet = packet.strip().split()
    start = 1
    time, start = get_part(packet, 4, start)
    gain, start = get_part(packet, 1, start)
    clockDivider, start = get_part(packet, 1, start)
    acquisitionCycles, start = get_part(packet, 1, start)
    oversampleRate, start = get_part(packet, 1, start)
    sampleRate, start = get_part(packet, 4, start)
    sampleRateDivider, start = get_part(packet, 1, start)
    sleepDuration, start = get_part(packet, 2, start)
    recordDuration, start = get_part(packet, 2, start)
    enableLED, start = get_part(packet, 1, start)
    activeStartStopPeriods, start = get_part(packet, 1, start)
    timezone, start = get_part(packet, 1, start)
    useFilter, start = get_part(packet, 1, start)
    goertzelFreq, start = get_part(packet, 4, start)
    goertzelThresh, start = get_part(packet, 4, start)
    goertzelFactor, start = get_part(packet, 4, start)

    time = hex_arr_to_int(time)
    gain = hex_arr_to_int(gain)
    clockDivider = hex_arr_to_int(clockDivider)
    acquisitionCycles = hex_arr_to_int(acquisitionCycles)
    oversampleRate = hex_arr_to_int(oversampleRate)
    sampleRate = hex_arr_to_int(sampleRate)
    sampleRateDivider = hex_arr_to_int(sampleRateDivider)
    sleepDuration = hex_arr_to_int(sleepDuration)
    recordDuration = hex_arr_to_int(recordDuration)
    enableLED = hex_arr_to_bool(enableLED)
    activeStartStopPeriods = hex_arr_to_int(activeStartStopPeriods)
    timezone = hex_arr_to_int(timezone)
    useFilter = hex_arr_to_bool(useFilter)


    goertzelFreq = hex_arr_to_int(goertzelFreq)
    goertzelFactor = hex_arr_to_float(goertzelFactor)
    goertzelThresh = hex_arr_to_float(goertzelThresh)


    results = {
        'time' : time,
        'gain': gain,
        'clockDivider': clockDivider,
        'acquisitionCycles': acquisitionCycles,
        'oversampleRate': oversampleRate,
        'sampleRate': sampleRate,
        'sampleRateDivider': sampleRateDivider,
        'sleepDuration' : sleepDuration,
        'recordDuration' : recordDuration,
        'enableLED': enableLED,
        'activeStartStopPeriods' : activeStartStopPeriods,
        'timezone' : timezone,
        'useFilter' : useFilter,
        'goertzelFreq': goertzelFreq,
        'goertzelThresh': goertzelThresh,
        'goertzelFactor': goertzelFactor
    }

    return results

def parse_time_schedule(packet):
    packet = packet.strip().split()
    start = 1
    timeSchedule = []
    for i in range(5):
        timePeriod = {}
        arrtime, start = get_part(packet, 2, start)
        timePeriod["startMinutes"] = hex_arr_to_int(arrtime)
        arrtime, start = get_part(packet, 2, start)
        timePeriod["stopMinutes"] = hex_arr_to_int(arrtime)
        timeSchedule.append(timePeriod)

    return timeSchedule

def get_AM_packet():
    cmd = os.path.join('bin', OS, CMD)
    packet = Popen([cmd, VID, PID, AM_USBAPP_GET], stdout=PIPE).stdout.read()

    packet = packet.strip().split()

    start = 1
    am_time, start = get_part(packet, AM_TIME_LENGTH, start)
    unique_id, start = get_part(packet, AM_UNIQUE_ID_LENGTH, start)
    battery_state, start = get_part(packet, AM_BATTERY_STATE_LENGTH, start)
    version, start = get_part(packet, AM_FIRMWARE_VERSION_LENGTH, start)
    description, start = get_part(packet, AM_FIRMWARE_DESCRIPTION_LENGTH, start)

    am_time = hex_arr_to_int(am_time)
    unique_id = hex_arr_to_int(unique_id)
    battery_state = hex_arr_to_int(battery_state)

    description = (
        ''
        .join(map(
            lambda x: chr(int(x, 16)),
            description))
        .strip(chr(0)))

    version = '.'.join(tuple(map(lambda x: str(int(x, 16)), version)))

    result = {
        'time': dtime.asctime(dtime.gmtime(am_time)),
        'id': unique_id,
        'battery_state': battery_state,
        'version': version,
        'description': description
    }

    return result

def retrieve_time_schedule():
    cmd = os.path.join('bin', OS, CMD)
    packet = Popen([cmd, VID, PID, AM_USBAPP_GET_TIME_SCHEDULE], stdout=PIPE).stdout.read()
    return parse_time_schedule(packet)

def set_time_schedule(configs):
    packet = struct_time_schedule(configs)
    cmd = os.path.join('bin', OS, CMD)
    p = Popen([cmd, VID, PID] + packet, stdout=PIPE)
    returned_packet = parse_time_schedule(p.stdout.read())
    return returned_packet

def set_AM_configs(configs=None):
    if configs is None:
        configs = {}

    true_configs = DEFAULT_CONFIG.copy()
    true_configs.update(configs)

    if FLAGS.set_time:
        true_configs["time"] = int(dtime.time())


    packet = struct_config(true_configs)
    cmd = os.path.join('bin', OS, CMD)
    p = Popen([cmd, VID, PID] + packet, stdout=PIPE)

    returned_packet = parse_config(p.stdout.read())
    return returned_packet


def get_configs(options):
    configs = {}

    options = vars(options)

    # Recorder configurations
    sampleRate = options.get('samplerate', None)
    if sampleRate is not None:
        rec_config = CONFIGURATIONS[str(sampleRate)]
        configs.update(rec_config)

    # Goertzel configurations
    keys = ['useFilter','goertzelFreq', 'goertzelThresh', 'goertzelFactor']
    goertzel = {
        key: options[key]
        for key in keys
        if options[key] is not None}

    configs.update(goertzel)

    # Other configurations
    keys = ['time', 'gain', 'enableLED', 'sleepDuration', 'recordDuration', 'timezone']
    other = {
        key: options[key]
        for key in keys
        if options[key] is not None}

    configs.update(other)
    return configs


def parse_args():
    parser = argparse.ArgumentParser('Configure Audiomoth detector')

    parser.add_argument(
        'action',
        type=str,
        choices=['set', 'get'])

    parser.add_argument(
        '--vid',
        type=str,
        default=VID)

    parser.add_argument(
        '--pid',
        type=str,
        default=PID)

    parser.add_argument(
        '--os',
        type=str,
        choices=['macOS', 'linux', 'windows', 'windows32'],
        default=OS)

    parser.add_argument(
        '--set_time',
        type=bool,
        default=True)

    parser.add_argument(
        '--time_schedule',
        type=str,
        default=TIME_SCHEDULE_PATH)

    parser.add_argument(
        '--config',
        type=str,
        default=CONFIG_PATH)

    parser.add_argument(
        '--configurations_file',
        type=str,
        default=CONFIGURATIONS_PATH)

    parser.add_argument(
        '--time',
        type=int)

    parser.add_argument(
        '--gain',
        type=int,
        choices=[1, 2, 3, 4])

    parser.add_argument(
        '--samplerate',
        type=int,
        choices=[
            8000,
            16000,
            32000,
            256000,
            48000,
            96000,
            192000,
            384000])

    parser.add_argument(
        '--sleepDuration',
        type=int)

    parser.add_argument(
        '--recordDuration',
        type=int)

    parser.add_argument(
        '--enableLED',
        type=bool)

    parser.add_argument(
        '--timezone',
        type=int)

    parser.add_argument(
        '--useFilter',
        type=bool)

    parser.add_argument(
        '--goertzelFreq',
        type=int)

    parser.add_argument(
        '--goertzelThresh',
        type=float)

    parser.add_argument(
        '--goertzelFactor',
        type=float)

    return parser.parse_args()


def print_dict(obj):
    for key, value in obj.iteritems():
        print('\t[*] {:^20}: {}'.format(key, value))


if __name__ == '__main__':
    FLAGS = parse_args()

    VID = FLAGS.vid
    PID = FLAGS.pid
    OS = FLAGS.os

    CONFIG_PATH = FLAGS.config
    CONFIGURATIONS_PATH = FLAGS.configurations_file

    DEFAULT_CONFIG = load_config()
    CONFIGURATIONS = load_configurations()
    TIME_SCHEDULE = load_time_schedule()

    if FLAGS.action == 'get':
        result = get_AM_packet()
        print('AudioMoth info:')
        print_dict(result)
        result = retrieve_time_schedule()
        print(result)
    else:
        configs = get_configs(FLAGS)
        results = set_AM_configs(configs=configs)
        print(results)
        results = set_time_schedule(TIME_SCHEDULE)
        print(results)
