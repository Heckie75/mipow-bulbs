#!/usr/bin/python3
import asyncio
import json
import os
import re
import struct
import sys
import time
from asyncio.exceptions import TimeoutError
from datetime import datetime, timedelta

from bleak import (AdvertisementData, BleakClient, BleakError, BleakScanner,
                   BLEDevice)

_REG_255 = r"(1?[0-9]?[0-9]|2[0-4][0-9]|25[0-5])"
_REG_1439 = r"[0-9]{1,3}|1[0-3][0-9]{2}|14[0-3][0-9]"
_REG_23COL59 = r"[01]?[0-9]:[0-5][0-9]|2[0-3]:[0-5][0-9]"

_MAX_BLE_CONNECTIONS = 8


class MyLogger():

    LEVELS = {
        "DEBUG": 0,
        "INFO": 1,
        "WARN": 2,
        "ERROR": 3
    }

    NAMES = ["DEBUG", "INFO", "WARN", "ERROR"]

    def __init__(self, level: int) -> None:
        self.level = level

    def error(self, s):

        self.log(MyLogger.LEVELS["ERROR"], s)

    def warning(self, s):

        self.log(MyLogger.LEVELS["WARN"], s)

    def info(self, s):

        self.log(MyLogger.LEVELS["INFO"], s)

    def debug(self, s):

        self.log(MyLogger.LEVELS["DEBUG"], s)

    def log(self, level, s):

        if level >= self.level:
            print(f"{MyLogger.NAMES[level]}\t{s}", file=sys.stderr)

    @staticmethod
    def hexstr(ba: bytearray) -> str:

        return " ".join([("0" + hex(b).replace("0x", ""))[-2:] for b in ba])


LOGGER = MyLogger(level=MyLogger.LEVELS["WARN"])


class MipowBulbException(Exception):

    def __init__(self, message) -> None:

        self.message = message


class Color():

    def __init__(self, white: int = 0, red: int = 0, green: int = 0, blue: int = 0) -> None:

        self.white: int = white
        self.red: int = red
        self.green: int = green
        self.blue: int = blue

    @staticmethod
    def fromBytes(ba: bytearray) -> 'Color':

        return Color(white=ba[0], red=ba[1], green=ba[2], blue=ba[3])

    def toBytes(self) -> bytearray:

        return bytearray([self.white & 0xff, self.red & 0xff, self.green & 0xff, self.blue & 0xff])

    def isOff(self) -> bool:

        return self.white == 0 and self.red == 0 and self.green == 0 and self.blue == 0

    def color_str(self) -> str:

        return "off" if self.isOff() else f"WRGB({self.white},{self.red},{self.green},{self.blue})"

    def dim(self, factor: float) -> 'Color':

        white = int(min(255, self.white * factor))
        red = int(min(255, self.red * factor))
        green = int(min(255, self.green * factor))
        blue = int(min(255, self.blue * factor))
        return Color(white=white, red=red, green=green, blue=blue)

    def __str__(self) -> str:

        return f"Color(white={self.white}, red={self.red}, green={self.green}, blue={self.blue})"

    def to_dict(self) -> dict:

        return {
            "white": self.white,
            "red": self.red,
            "green": self.green,
            "blue": self.blue,
            "color_str": self.color_str()
        }


class Effect():

    TYPE_FLASH = 0x00
    TYPE_PULSE = 0x01
    TYPE_DISCO = 0x02
    TYPE_RAINBOW = 0x03
    TYPE_CANDLE = 0x04
    TYPE_OFF = 0xff

    TYPES = ["flash", "pulse", "disco", "rainbow", "candle", "off"]

    def __init__(self, color: Color = Color(), type_: int = 0xff, repetitions: int = 0, delay: int = 0, pause: int = 0) -> None:

        self.color: Color = color
        self.type: int = type_
        self.repetitions: int = repetitions
        self.delay: int = delay
        self.pause: int = pause

    @staticmethod
    def fromBytes(ba: bytearray) -> 'Effect':

        return Effect(color=Color.fromBytes(ba=ba[0:4]), type_=ba[4], repetitions=ba[5], delay=ba[6], pause=ba[7])

    def toBytes(self) -> bytearray:

        ba = bytearray(self.color.toBytes())
        ba.extend([self.type & 0xff, self.repetitions & 0xff,
                   self.delay & 0xff, self.pause & 0xff])
        return ba

    def type_str(self):

        return Effect.TYPES[5] if self.type > Effect.TYPE_CANDLE else Effect.TYPES[self.type]

    def __str__(self) -> str:

        return f"Effect(type={self.type_str()}, color={str(self.color)}, repetitions={self.repetitions}, delay={self.delay}, pause={self.pause})"

    def to_dict(self) -> dict:

        return {
            "color": self.color.to_dict() if self.color else None,
            "type": self.type,
            "type_str": self.type_str(),
            "repetitions": self.repetitions,
            "delay": self.delay,
            "pause": self.pause
        }


class Timer():

    TYPE_WAKEUP = 0x00
    TYPE_DOZE = 0x02
    TYPE_OFF = 0x04

    TYPES = ["wakeup", "doze", "off"]

    def __init__(self, id: int, type_: int = 2, hour: int = 0xff, minute: int = 0xff, runtime: int = 0, color: Color = Color(), now: datetime = None) -> None:

        self.id: int = id
        self.type: int = type_
        self.hour: int = hour
        self.minute: int = minute
        self.runtime: int = runtime
        self.color: Color = color
        self.now = now

    def type_str(self):

        if self.type == Timer.TYPE_WAKEUP:
            return Timer.TYPES[0]
        elif self.type == Timer.TYPE_DOZE:
            return Timer.TYPES[1]
        else:
            return Timer.TYPES[2]

    def time_str(self) -> str:

        return f"{self.hour:02}:{self.minute:02}" if self.hour is not None and self.hour != 0xff and self.minute is not None and self.minute != 0xff else "--:--"

    def runtime_str(self) -> str:

        return f"{self.runtime // 60:02}:{self.runtime % 60:02}"

    def toBytes(self, reset: bool = False) -> bytearray:

        now = self.now if self.now else datetime.now()

        bs = [self.id & 0x03, self.type & 0xff, now.second, now.minute,
              now.hour, 0xff if reset else 0x00, self.minute & 0xff, self.hour & 0xff]
        bs.extend(self.color.toBytes())
        bs.append(self.runtime & 0xff)

        return bytearray(bs)

    @staticmethod
    def fromBytes(id: int, schedule: bytearray, effect: bytearray) -> 'Timer':

        return Timer(id=id, type_=schedule[0], hour=schedule[1],
                     minute=schedule[2], runtime=effect[4], color=Color.fromBytes(ba=effect[:4]))

    def __str__(self) -> str:

        return f"Timer(id={self.id}, type={self.type}, hour={self.hour}, minute={self.minute}, runtime={self.runtime}, color={str(self.color)}, now={self.now.strftime('%H:%M') if self.now else ''})"

    def to_dict(self) -> dict:

        return {
            "id": self.id,
            "type": self.type,
            "type_str": self.type_str(),
            "hour": self.hour,
            "minute": self.minute,
            "time_str": self.time_str(),
            "runtime": self.runtime,
            "runtime_str": self.runtime_str(),
            "color": self.color.to_dict()
        }


class Timers():

    def __init__(self, hour: int, minute: int) -> None:

        self.timers: 'list[Timer]' = [None, None, None, None]
        self.hour: int = hour
        self.minute: int = minute

    @staticmethod
    def fromBytes(schedule: bytearray, effect: bytearray) -> 'Timers':

        timers = Timers(hour=schedule[12], minute=schedule[13])
        for i in range(4):
            timer = Timer.fromBytes(
                id=i, schedule=schedule[i * 3: i * 3 + 4], effect=effect[i * 5:i * 5 + 6])
            timers.timers[i] = timer

        return timers

    def time_str(self) -> str:

        return f"{self.hour:02}:{self.minute:02}" if self.hour is not None and self.hour != 0xff and self.minute is not None and self.minute != 0xff else "--:--"

    def __str__(self) -> str:

        timers_str = [str(t) for t in self.timers if t is not None]
        return f"Timers(hour={self.hour}, minute={self.minute}, timers=[{', '.join(timers_str)}])"

    def to_dict(self) -> dict:

        return {
            "hour": self.hour,
            "minute": self.minute,
            "time_str": self.time_str(),
            "timers": [t.to_dict() for t in self.timers if t is not None]
        }


class Security():

    def __init__(self, active: bool = False, hour: int = 0, minute: int = 0, startingHour: int = 0xff, startingMinute: int = 0xff, endingHour: int = 0xff, endingMinute: int = 0xff, minInterval: int = 0xff, maxInterval: int = 0xff, color: Color = Color()) -> None:

        self.active: bool = active
        self.hour: int = hour
        self.minute: int = minute
        self.startingHour: int = startingHour
        self.startingMinute: int = startingMinute
        self.endingHour: int = endingHour
        self.endingMinute: int = endingMinute
        self.minInterval: int = minInterval
        self.maxInterval: int = maxInterval
        self.color: Color = color

    @staticmethod
    def fromBytes(ba: bytearray) -> 'Security':

        return Security(active=ba[0] != 0, hour=ba[1], minute=ba[2], startingHour=ba[3],
                        startingMinute=ba[4], endingHour=ba[5], endingMinute=ba[6],
                        minInterval=ba[7], maxInterval=ba[8], color=Color.fromBytes(ba=ba[9:13]))

    def toBytes(self, reset: bool = False) -> bytearray:

        bs = [0x00, self.minute, self.hour]
        if reset:
            bs.extend([0xff, 0xff, 0xff, 0xff, 0xff, 0xff])
            bs.extend(Color().toBytes())
        else:
            bs.extend([self.startingHour, self.startingMinute, self.endingHour,
                      self.endingMinute, self.minInterval, self.maxInterval])
            bs.extend(self.color.toBytes())

        return bytearray(bs)

    @staticmethod
    def time_str(hour: int, minute: int) -> str:

        return f"{hour:02}:{minute:02}" if hour != 0xff and minute != 0xff else "--:--"

    def __str__(self) -> str:

        return f"Security(hour={self.hour}, minute={self.minute}, startingHour={self.startingHour}, startingMinute={self.startingMinute}, endingHour={self.endingHour}, endingMinute={self.endingMinute}, minInterval={self.minInterval}, maxInterval={self.maxInterval}, color={str(self.color)})"

    def to_dict(self) -> dict:

        return {
            "hour": self.hour,
            "minute": self.minute,
            "time_str": Security.time_str(self.hour, self.minute),
            "startingHour": self.startingHour,
            "startingMinute": self.startingMinute,
            "start_str": Security.time_str(self.startingHour, self.startingMinute),
            "endingHour": self.endingHour,
            "endingMinute": self.endingMinute,
            "end_str": Security.time_str(self.endingHour, self.endingMinute),
            "minInterval": self.minInterval,
            "maxInterval": self.maxInterval,
            "color": self.color.to_dict()
        }


class Listener():

    def onScanSeen(self, device: BLEDevice) -> None:

        pass

    def onScanFound(self, device: BLEDevice) -> None:

        pass

    def onConnected(self, device: BLEDevice) -> None:

        pass

    def onDisconnected(self, device: BLEDevice) -> None:

        pass

    def onRequest(self, device: BLEDevice) -> None:

        pass

    def onNotify(self, device: BLEDevice, timerid: int, color: Color) -> None:

        pass


class MipowBulb(BleakClient):

    MAC_SUFFIX = ":AC:E6"

    CHARACTERISTIC_SERVICE_CHANGED = "00002a05-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_SERIAL_NUMBER_STRING = "00002a25-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_FIRMWARE_REVISION_STRING = "00002a26-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_HARDWARE_REVISION_STRING = "00002a27-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_SOFTWARE_REVISION_STRING = "00002a28-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_MANUFACTURER_NAME_STRING = "00002a29-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_HEART_RATE_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_HEART_RATE_CONTROL_POINT = "00002a39-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_PNP_ID = "00002a50-0000-1000-8000-00805f9b34fb"

    CHARACTERISTIC_PLAYBULB_PIN = "0000fff7-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_PLAYBULB_TIMER_EFFECT = "0000fff8-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_PLAYBULB_SECURITY_MODE = "0000fff9-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_PLAYBULB_FFFA = "0000fffa-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_PLAYBULB_EFFECT = "0000fffb-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_PLAYBULB_COLOR = "0000fffc-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_PLAYBULB_FACTORY_RESET = "0000fffd-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_PLAYBULB_TIMER_SCHEDULE = "0000fffe-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_PLAYBULB_GIVEN_NAME = "0000ffff-0000-1000-8000-00805f9b34fb"

    def __init__(self, address: str, listener: Listener = None) -> None:

        if listener:
            super().__init__(address, disconnected_callback=listener.onDisconnected, timeout=30.0)
        else:
            super().__init__(address, timeout=30.0)

        self.name: str = None
        self.serialNumber: str = None
        self.pin: str = None
        self.batteryLevel: int = None
        self.firmwareRevision: str = None
        self.hardwareRevision: str = None
        self.softwareRevision: str = None
        self.manufacturer: str = None
        self.pnpId: int = 0
        self.color: Color = None
        self.effect: Effect = None
        self.timers: Timers = None
        self.security: Security = None

        self.listener: Listener = listener

    async def read_gatt_char(self, characteristic) -> bytearray:

        LOGGER.debug(">>> %s: read_gatt_char(%s)" %
                     (self.address, characteristic))
        response = await super().read_gatt_char(characteristic)
        if response:
            LOGGER.debug("<<< %s: %s" %
                         (self.address, MyLogger.hexstr(response)))

        if self.listener:
            self.listener.onRequest(self)

        return response

    async def write_gatt_char(self, characteristic, data, response):

        LOGGER.debug(">>> %s: write_gatt_char(%s, %s)" %
                     (self.address, characteristic, MyLogger.hexstr(data)))
        response = await super().write_gatt_char(characteristic, data=data, response=response)
        if response:
            LOGGER.debug("<<< %s: %s" %
                         (self.address, MyLogger.hexstr(response)))

        if self.listener:
            self.listener.onRequest(self)

        return response

    async def connect(self):

        _listener = self.listener
        _self = self

        async def _notificationHandler(c, bytes: bytearray) -> None:

            _listener.onNotify(
                device=_self, timerid=bytes[6], color=Color.fromBytes(bytes[0:4]))

        LOGGER.info("Connecting to %s ..." % self.address)
        await super().connect()
        LOGGER.info("Successfully connected to %s." % self.address)
        if self.listener:
            self.listener.onConnected(self)
            try:
                await self.start_notify(MipowBulb.CHARACTERISTIC_HEART_RATE_MEASUREMENT, callback=_notificationHandler)
            except:
                LOGGER.warning("Unable to register listener for notifications. Maybe not supported")

    async def disconnect(self):

        LOGGER.info("Disconnecting from %s ..." % self.address)
        await super().disconnect()
        LOGGER.info("Successfully disconnected from %s." % self.address)

    async def requestLight(self) -> Color:

        LOGGER.info("request light for %s..." % self.address)
        ba = await self.read_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_COLOR)
        self.color = Color.fromBytes(ba=ba)
        LOGGER.info("light of %s is %s." %
                    (self.address, self.color.color_str()))
        return self.color

    async def setLight(self, color: Color) -> 'MipowBulb':

        LOGGER.info("set light %s for %s..." %
                    (color.color_str(), self.address))
        await self.write_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_COLOR, data=color.toBytes(), response=False)
        LOGGER.info("light set for %s." % self.address)
        self.color = color
        return self

    async def requestEffect(self) -> Effect:

        LOGGER.info("request effect for %s..." % self.address)
        ba = await self.read_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_EFFECT)
        self.effect = Effect.fromBytes(ba=ba)
        LOGGER.info("effect of %s is %s." % (self.address, str(self.effect)))
        return self.effect

    async def setEffect(self, effect: Effect) -> 'MipowBulb':

        LOGGER.info("set effect %s for %s..." % (str(effect), self.address))
        await self.write_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_EFFECT, data=effect.toBytes(), response=False)
        LOGGER.info("effect set for %s." % self.address)
        self.effect = effect
        return self

    async def setHold(self, delay: int, repetitions: int, pause: int) -> 'MipowBulb':

        effect = await self.requestEffect()
        effect = Effect(color=effect.color, type_=effect.type,
                        repetitions=repetitions, delay=delay, pause=pause)
        await self.setEffect(effect=effect)
        return self

    async def halt(self) -> 'MipowBulb':

        color = await self.requestLight()
        await self.setEffect(Effect(color=color, type_=Effect.TYPE_OFF, repetitions=0, delay=0, pause=0))
        return self

    async def toggle(self) -> 'MipowBulb':

        await self.requestLight()
        if self.color.isOff():
            await self.requestEffect()
            if not self.effect.color.isOff():
                await self.setLight(color=self.effect.color)
            else:
                await self.setLight(color=Color(white=255))
        else:
            await self.setEffect(Effect(color=self.color, type_=Effect.TYPE_OFF, repetitions=0, delay=0, pause=0))
            await self.setLight(color=Color())

        return self

    async def dim(self, factor) -> 'MipowBulb':

        await self.requestLight()
        await self.setLight(color=self.color.dim(factor=factor))

        return self

    async def requestTimers(self) -> Timers:

        LOGGER.info("request timer schedule for %s..." % self.address)
        schedule = await self.read_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_TIMER_SCHEDULE)

        LOGGER.info("request timer effect for %s..." % self.address)
        effect = await self.read_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_TIMER_EFFECT)

        self.timers = Timers.fromBytes(schedule=schedule, effect=effect)
        LOGGER.info("timers of %s are %s." % (self.address, str(self.timers)))
        return self.timers

    def _updateTimers(self, timer: Timer) -> None:

        if not self.timers:
            now = datetime.now()
            self.timers = Timers(hour=now.hour, minute=now.minute)

        self.timers.timers[timer.id] = timer

    async def resetTimer(self, id: int) -> 'MipowBulb':

        timer = Timer(id=id)
        LOGGER.info("set timer %s for %s..." % (str(timer), self.address))
        await self.write_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_TIMER_SCHEDULE, data=timer.toBytes(reset=True), response=True)
        LOGGER.info("timer reset for %s." % self.address)
        self._updateTimers(timer=timer)
        return self

    async def deactivateTimer(self, timer: Timer) -> 'MipowBulb':

        timer.type = Timer.TYPE_OFF
        LOGGER.info("deactivate timer %s for %s..." %
                    (str(timer), self.address))
        await self.write_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_TIMER_SCHEDULE, data=timer.toBytes(), response=True)
        LOGGER.info("timer deactivated for %s." % self.address)
        self._updateTimers(timer=timer)
        return self

    async def setTimer(self, timer: Timer) -> 'MipowBulb':

        LOGGER.info("set light %s for %s..." % (str(timer), self.address))
        await self.write_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_TIMER_SCHEDULE, data=timer.toBytes(), response=True)
        LOGGER.info("timer set for %s." % self.address)
        self._updateTimers(timer=timer)
        return self

    async def requestSecurity(self) -> Security:

        try:
            LOGGER.info("request security for %s..." % self.address)
            ba = await self.read_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_SECURITY_MODE)
            self.security = Security.fromBytes(ba=ba)
            LOGGER.info("security of %s is %s." %
                        (self.address, str(self.security)))
            return self.security

        except BleakError as e:
            LOGGER.warning(str(e))
            self.security = None

        return None

    async def setSecurity(self, security: Security) -> 'MipowBulb':

        try:
            LOGGER.info("set security %s for %s..." %
                        (str(security), self.address))
            await self.write_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_SECURITY_MODE, data=security.toBytes(), response=True)
            LOGGER.info("security set for %s." % self.address)
            self.security = security

        except BleakError as e:
            LOGGER.warning(str(e))
            self.security = None

        return self

    async def resetSecurity(self) -> 'MipowBulb':

        try:
            security = Security()
            LOGGER.info("reset security %s for %s..." %
                        (str(security), self.address))
            await self.write_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_SECURITY_MODE, data=security.toBytes(reset=True), response=True)
            LOGGER.info("security reset for %s." % self.address)
            self.security = security

        except BleakError as e:
            LOGGER.warning(str(e))
            self.security = None

        return self

    async def requestName(self) -> str:

        LOGGER.info("request name of %s..." % self.address)
        name = await self.read_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_GIVEN_NAME)
        self.name = name.decode()
        LOGGER.info("name of %s is %s." % (self.address, self.name))
        return self.name

    async def setName(self, name: str) -> 'MipowBulb':

        LOGGER.info("set name %s of %s..." % (name, self.address))
        await self.write_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_GIVEN_NAME, name[:14].encode(), response=True)
        LOGGER.info("name set of %s." % self.address)
        return self

    async def requestPin(self) -> str:

        try:
            LOGGER.info("request pin of %s..." % self.address)
            pin = await self.read_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_PIN)
            self.pin = pin.decode()
            LOGGER.info("pin of %s is %s." % (self.address, self.pin))
            return self.pin

        except BleakError as e:
            LOGGER.warning(str(e))

        return None

    async def setPin(self, pin: str) -> 'MipowBulb':

        try:
            LOGGER.info("set pin %s for %s..." % (pin, self.address))
            await self.write_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_PIN, pin[:4].encode(), response=True)
            LOGGER.info("pin set for %s." % self.address)
        except BleakError as e:
            LOGGER.warning(str(e))

        return self

    async def requestBatteryLevel(self) -> str:

        try:
            LOGGER.info("request batteryLevel of %s..." % self.address)
            raw = await self.read_gatt_char(MipowBulb.CHARACTERISTIC_BATTERY_LEVEL)
            self.batteryLevel = struct.unpack("<H", raw)[0]
            LOGGER.info(f"batteryLevel of {self.address} is {self.batteryLevel}%.")
            return self.batteryLevel

        except BleakError as e:
            LOGGER.warning(str(e))
            self.batteryLevel = None

        return None

    async def requestFirmwareRevision(self) -> str:

        LOGGER.info("request firmwareRevision of %s..." % self.address)
        firmwareRevision = await self.read_gatt_char(MipowBulb.CHARACTERISTIC_FIRMWARE_REVISION_STRING)
        self.firmwareRevision = firmwareRevision.decode()
        LOGGER.info("firmwareRevision of %s is %s." %
                    (self.address, self.firmwareRevision))
        return self.firmwareRevision

    async def requestSoftwareRevision(self) -> str:

        LOGGER.info("request softwareRevision of %s..." % self.address)
        softwareRevision = await self.read_gatt_char(MipowBulb.CHARACTERISTIC_SOFTWARE_REVISION_STRING)
        self.softwareRevision = softwareRevision.decode()
        LOGGER.info("softwareRevision of %s is %s." %
                    (self.address, self.softwareRevision))
        return self.softwareRevision

    async def requestHardwareRevision(self) -> str:

        LOGGER.info("request hardwareRevision of %s..." % self.address)
        hardwareRevision = await self.read_gatt_char(MipowBulb.CHARACTERISTIC_HARDWARE_REVISION_STRING)
        self.hardwareRevision = hardwareRevision.decode()
        LOGGER.info("hardwareRevision of %s is %s." %
                    (self.address, self.hardwareRevision))
        return self.hardwareRevision

    async def requestManufacturer(self) -> str:

        LOGGER.info("request manufacturer of %s..." % self.address)
        manufacturer = await self.read_gatt_char(MipowBulb.CHARACTERISTIC_MANUFACTURER_NAME_STRING)
        self.manufacturer = manufacturer.decode()
        LOGGER.info("manufacturer of %s is %s." %
                    (self.address, self.manufacturer))
        return self.manufacturer

    async def requestSerialNumber(self) -> str:

        LOGGER.info("request serialNumber of %s..." % self.address)
        serialNumber = await self.read_gatt_char(MipowBulb.CHARACTERISTIC_SERIAL_NUMBER_STRING)
        self.serialNumber = serialNumber.decode()
        LOGGER.info("serialNumber of %s is %s." %
                    (self.address, self.serialNumber))
        return self.serialNumber

    async def requestPnpId(self) -> int:

        LOGGER.info("request pnpId of %s..." % self.address)
        raw = await self.read_gatt_char(MipowBulb.CHARACTERISTIC_PNP_ID)
        unpacked = struct.unpack(">bHHH", raw)
        self.pnpId = f"pnpId(vendorIDSource={int(unpacked[0])},vendorID={hex(unpacked[1])},productID={hex(unpacked[2])},productVersion={hex(unpacked[3])})"
        LOGGER.info("pnpId of %s is %s." % (self.address, self.pnpId))
        return self.pnpId

    async def reset(self) -> None:

        LOGGER.info("perform factory reset for %s..." % self.address)
        await self.write_gatt_char(MipowBulb.CHARACTERISTIC_PLAYBULB_FACTORY_RESET, bytearray([3]), response=True)
        LOGGER.info("factory reset performed for %s." % self.address)

    def __str__(self) -> str:

        return f"MipowBulb(name={self.name}, serialNumber={self.serialNumber}, pin={self.pin}, batteryLevel={self.batteryLevel}, firmwareRevision={self.firmwareRevision}, hardwareRevision={self.hardwareRevision}, softwareRevision={self.softwareRevision}, manufacturer={self.manufacturer}, pnpId={self.pnpId}, color={str(self.color)}, effect={str(self.effect)}, timers={str(self.timers)}, Security={str(self.security)})"

    def to_dict(self) -> dict:

        return {
            "address": self.address,
            "name": self.name,
            "serialNumber": self.serialNumber,
            "pin": self.pin,
            "batteryLevel": self.batteryLevel,
            "firmwareRevision": self.firmwareRevision,
            "hardwareRevision": self.hardwareRevision,
            "softwareRevision": self.softwareRevision,
            "manufacturer": self.manufacturer,
            "pnpId": self.pnpId,
            "color": self.color.to_dict() if self.color else None,
            "effect": self.effect.to_dict() if self.effect else None,
            "timers": self.timers.to_dict() if self.timers else None,
            "security": self.security.to_dict() if self.security else None
        }


class MipowBulbController():

    def __init__(self, addresses: 'list[str]', listener: Listener = None) -> None:

        self.addresses: 'list[str]' = addresses
        self.bulbs: 'list[MipowBulb]' = list()
        self._listener = listener

    async def connect(self, timeout) -> None:

        LOGGER.info("Request to connect to %s" % ", ".join(self.addresses))
        devices = await MipowBulbController.scan(duration=timeout + len(self.addresses), filter_=self.addresses, listener=self._listener)
        LOGGER.info("Found devices are %s" % (
            ", ".join([f"{d.name} ({d.address})" for d in devices]) if devices else "n/a"))

        if len(devices) < len(self.addresses):
            raise MipowBulbException(
                message="Could not find all given addresses")
        else:
            self.bulbs = [MipowBulb(device, self._listener)
                          for device in devices]

        coros = [bulb.connect() for bulb in self.bulbs]
        await asyncio.gather(*coros)
        await asyncio.sleep(.2)

    async def disconnect(self) -> None:

        coros = [bulb.disconnect() for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)

    async def requestName(self) -> 'list[MipowBulb]':

        coros = [bulb.requestName()
                 for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def setName(self, name: str) -> 'list[MipowBulb]':

        coros = [bulb.setName(name=name)
                 for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def requestPin(self) -> 'list[MipowBulb]':

        coros = [bulb.requestPin() for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def setPin(self, pin: str) -> 'list[MipowBulb]':

        coros = [bulb.setPin(pin=pin)
                 for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def requestDeviceInfo(self) -> 'list[MipowBulb]':

        for bulb in self.bulbs:
            await bulb.requestName()
            await bulb.requestManufacturer()
            await bulb.requestSerialNumber()
            await bulb.requestHardwareRevision()
            await bulb.requestFirmwareRevision()
            await bulb.requestSoftwareRevision()
            await bulb.requestPnpId()
            await bulb.requestBatteryLevel()

        return self.bulbs

    async def setLight(self, color: Color) -> 'list[MipowBulb]':

        coros = [bulb.setLight(color=color)
                 for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def requestLight(self) -> 'list[MipowBulb]':

        coros = [bulb.requestLight()
                 for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def requestEffect(self) -> 'list[MipowBulb]':

        coros = [bulb.requestEffect()
                 for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def setEffect(self, effect: Effect) -> 'list[MipowBulb]':

        coros = [bulb.setEffect(effect=effect)
                 for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def setHold(self, delay: int, repetitions: int, pause: int) -> 'list[MipowBulb]':

        coros = [bulb.setHold(delay=delay, repetitions=repetitions, pause=pause)
                 for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def halt(self) -> 'list[MipowBulb]':

        coros = [bulb.halt() for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def toggle(self) -> 'list[MipowBulb]':

        coros = [bulb.toggle() for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def dim(self, factor: float) -> 'list[MipowBulb]':

        coros = [bulb.dim(factor=factor)
                 for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def requestTimers(self) -> 'list[MipowBulb]':

        coros = [bulb.requestTimers()
                 for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def resetTimers(self, ids: 'list[int]'):

        coros = list()
        for bulb in self.bulbs:
            for id in ids:
                coros.append(bulb.resetTimer(id=id))

        await asyncio.gather(*coros)
        return self.bulbs

    async def setTimer(self, timer: Timer) -> 'list[MipowBulb]':

        coros = [bulb.setTimer(timer=timer)
                 for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def setTimers(self, timers: 'list[Timer]') -> 'list[MipowBulb]':

        coros = list()
        for timer in timers:
            for bulb in self.bulbs:
                coros.append(bulb.setTimer(timer=timer))

        await asyncio.gather(*coros)
        return self.bulbs

    async def setSceneFade(self, runtime: int, color: Color) -> 'list[MipowBulb]':

        await self.resetTimers(ids=[0, 1, 2])

        now = datetime.now()
        then = now + timedelta(minutes=1)
        timer = Timer(id=3, type_=Timer.TYPE_WAKEUP, hour=then.hour,
                      minute=then.minute, runtime=runtime, color=color)
        await self.setTimer(timer=timer)

        return self.bulbs

    async def setSceneAmbient(self, runtime: int, hour: int = None, minute: int = None) -> 'list[MipowBulb]':

        await self.resetTimers(ids=[0, 1])

        start_3 = datetime(year=1970, month=1, day=1, hour=hour, minute=minute)
        timer_3 = Timer(id=2, type_=Timer.TYPE_WAKEUP, hour=start_3.hour,
                        minute=start_3.minute, runtime=1, color=Color(red=255, green=47))

        start_4 = start_3 + timedelta(minutes=runtime - 1)
        timer_4 = Timer(id=3, type_=Timer.TYPE_DOZE, hour=start_4.hour,
                        minute=start_4.minute, runtime=1, color=Color())

        await self.setTimers(timers=[timer_4, timer_3])

        return self.bulbs

    async def setSceneWakeup(self, runtime: int, hour: int = 0, minute: int = 0) -> 'list[MipowBulb]':

        start_1 = datetime(year=1970, month=1, day=1, hour=hour, minute=minute)
        runtime_1 = min(runtime * 16 // 60, 255)
        timer_1 = Timer(id=0, type_=Timer.TYPE_WAKEUP, hour=start_1.hour,
                        minute=start_1.minute, runtime=runtime_1, color=Color(blue=20))

        start_2 = start_1 + timedelta(minutes=runtime_1)
        runtime_2 = min(runtime * 8 // 60, 255)
        timer_2 = Timer(id=1, type_=Timer.TYPE_WAKEUP, hour=start_2.hour,
                        minute=start_2.minute, runtime=runtime_2, color=Color(green=60, blue=255))

        start_3 = start_2 + timedelta(minutes=runtime_2)
        timer_3 = Timer(id=2, type_=Timer.TYPE_WAKEUP, hour=start_3.hour,
                        minute=start_3.minute, runtime=1, color=Color(white=255))

        start_4 = start_3 + timedelta(minutes=runtime * 36 // 60)
        runtime_4 = 1
        timer_4 = Timer(id=3, type_=Timer.TYPE_DOZE, hour=start_4.hour,
                        minute=start_4.minute, runtime=runtime_4, color=Color())

        await self.setTimers(timers=[timer_4, timer_3, timer_2, timer_1])

        return self.bulbs

    async def setSceneDoze(self, runtime: int, hour: int = 0, minute: int = 0) -> 'list[MipowBulb]':

        await self.resetTimers(ids=[0, 1])

        start_3 = datetime(year=1970, month=1, day=1, hour=hour, minute=minute)
        runtime_3 = runtime * 2 // 3
        timer_3 = Timer(id=2, type_=Timer.TYPE_WAKEUP, hour=start_3.hour,
                        minute=start_3.minute, runtime=runtime_3, color=Color(red=255, green=47))

        start_4 = start_3 + timedelta(minutes=runtime_3)
        runtime_4 = runtime // 3
        timer_4 = Timer(id=3, type_=Timer.TYPE_DOZE, hour=start_4.hour,
                        minute=start_4.minute, runtime=runtime_4, color=Color())

        await self.setTimers(timers=[timer_4, timer_3])

        return self.bulbs

    async def setSceneWheel(self, order: str = "bgr", runtime: int = 0, hour: int = 0, minute: int = 0, brightness: int = 255) -> 'list[MipowBulb]':

        lap = min(runtime // 4, 480)
        runtime = min(lap, 255)

        starts: 'list[datetime]' = list()
        starts.append(datetime(year=1970, month=1,
                      day=1, hour=hour, minute=minute))
        starts.append(starts[-1] + timedelta(minutes=lap))
        starts.append(starts[-1] + timedelta(minutes=lap))
        starts.append(starts[-1] + timedelta(minutes=min(lap, 479)))

        timer_4 = Timer(id=3, type_=Timer.TYPE_DOZE,
                        hour=starts[-1].hour, minute=starts[-1].minute, runtime=runtime)

        for i, c in enumerate(order):

            if c.lower() == "r":
                timer_3 = Timer(id=2, type_=Timer.TYPE_WAKEUP,
                                hour=starts[i].hour, minute=starts[i].minute, runtime=runtime, color=Color(red=brightness))
            elif c.lower() == "g":
                timer_2 = Timer(id=1, type_=Timer.TYPE_WAKEUP,
                                hour=starts[i].hour, minute=starts[i].minute, runtime=runtime, color=Color(green=brightness))
            elif c.lower() == "b":
                timer_1 = Timer(id=0, type_=Timer.TYPE_WAKEUP,
                                hour=starts[i].hour, minute=starts[i].minute, runtime=runtime, color=Color(blue=brightness))

        await self.setTimers(timers=[timer_4, timer_3, timer_2, timer_1])
        return self.bulbs

    async def requestSecurity(self) -> 'list[MipowBulb]':

        coros = [bulb.requestSecurity()
                 for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def setSecurity(self, security: Security) -> 'list[MipowBulb]':

        coros = [bulb.setSecurity(security=security)
                 for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def resetSecurity(self) -> 'list[MipowBulb]':

        coros = [bulb.resetSecurity()
                 for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    async def reset(self) -> None:

        coros = [bulb.reset() for bulb in self.bulbs if bulb.is_connected]
        await asyncio.gather(*coros)
        return self.bulbs

    @staticmethod
    async def scan(duration: int = 20, filter_: 'list[str]' = None, listener: Listener = None) -> 'set[BLEDevice]':

        found_devices: 'set[BLEDevice]' = set()
        found_bulbs: 'set[BLEDevice]' = set()
        if filter_:
            consumed_filter = [m for m in filter_]
        else:
            consumed_filter = None

        def callback(device: BLEDevice, advertising_data: AdvertisementData):

            if device not in found_devices and device.name:
                found_devices.add(device)
                if device.address.upper().endswith(MipowBulb.MAC_SUFFIX):

                    if consumed_filter and device.address not in found_bulbs:
                        if device.address in consumed_filter or device.name in consumed_filter:
                            found_bulbs.add(device)
                            consumed_filter.remove(
                                device.address if device.address in consumed_filter else device.name)
                            if listener:
                                listener.onScanFound(device)

                    elif not filter_:
                        found_bulbs.add(device)
                        if listener:
                            listener.onScanFound(device)

            if listener:
                listener.onScanSeen(device)

        async with BleakScanner(callback) as scanner:
            if consumed_filter:
                start_time = time.time()
                while consumed_filter and (start_time + duration) > time.time():
                    await asyncio.sleep(.1)
            elif duration:
                await asyncio.sleep(duration)
            else:
                while True:
                    await asyncio.sleep(1)

        return found_bulbs


class Alias():

    _KNOWN_DEVICES_FILE = ".known_bulbs"
    MAC_PATTERN = r"^([0-9A-F]{2}):([0-9A-F]{2}):([0-9A-F]{2}):([0-9A-F]{2}):([0-9A-F]{2}):([0-9A-F]{2})$"

    def __init__(self) -> None:

        self.aliases: 'dict[str,str]' = dict()
        try:
            filename = os.path.join(os.environ['USERPROFILE'] if os.name == "nt" else os.environ['HOME']
                                    if "HOME" in os.environ else "~", Alias._KNOWN_DEVICES_FILE)

            if os.path.isfile(filename):
                with open(filename, "r") as ins:
                    for line in ins:
                        _m = re.match(
                            "([0-9A-Fa-f:]+) +(.*)$", line)
                        if _m and _m.groups()[0].upper().endswith(MipowBulb.MAC_SUFFIX):
                            self.aliases[_m.groups()[0]] = _m.groups()[1]

        except:
            pass

    def resolve(self, label: str) -> 'set[str]':

        if re.match(Alias.MAC_PATTERN, label.upper()):
            label = label.upper()
            if label.upper().endswith(MipowBulb.MAC_SUFFIX):
                return [label]
            else:
                return None
        else:
            macs = {a.upper()
                    for a in self.aliases if label in self.aliases[a]}
            if macs:
                LOGGER.debug("Found mac-addresses for aliases: %s" %
                             ", ".join(macs))
            else:
                LOGGER.debug("No aliases found")

            return macs if macs else None

    def __str__(self) -> str:

        return "\n".join([f"{a}\t{self.aliases[a]}" for a in self.aliases])


class MipowBulbCLI():

    _USAGE = "usage"
    _DESCR = "descr"
    _REGEX = "regex"
    _TYPES = "types"

    _COMMAND = "command"
    _ARGS = "args"
    _PARAMS = "params"

    COMMANDS = {
        "aliases": {
            _USAGE: "--aliases",
            _DESCR: "print known aliases from .known_bulbs file",
            _REGEX: None,
            _TYPES: None
        },
        "scan": {
            _USAGE: "--scan",
            _DESCR: "scan for Mipow bulbs",
            _REGEX: None,
            _TYPES: None
        },
        "status": {
            _USAGE: "--status",
            _DESCR: "just read and print the basic information of the bulb",
            _REGEX: None,
            _TYPES: None
        },
        "on": {
            _USAGE: "--on",
            _DESCR: "turn bulb on",
            _REGEX: None,
            _TYPES: None
        },
        "off": {
            _USAGE: "--off",
            _DESCR: "turn bulb off",
            _REGEX: None,
            _TYPES: None
        },
        "toggle": {
            _USAGE: "--toggle",
            _DESCR: "turn off / on (remembers color!)",
            _REGEX: None,
            _TYPES: None
        },
        "color": {
            _USAGE: "--color [<white> <red> <green> <blue>]",
            _DESCR: "set color\n- <color> each value 0 - 255\n- without parameters current color will be returned",
            _REGEX: r"^(%s %s %s %s)?$" % (_REG_255, _REG_255, _REG_255, _REG_255),
            _TYPES: [int, int, int, int]
        },
        "up": {
            _USAGE: "--up",
            _DESCR: "turn up light",
            _REGEX: None,
            _TYPES: None
        },
        "down": {
            _USAGE: "--down",
            _DESCR: "dim light",
            _REGEX: None,
            _TYPES: None
        },
        "effect": {
            _USAGE: "--effect",
            _DESCR: "request current effect of bulb",
            _REGEX: None,
            _TYPES: None
        },
        "pulse": {
            _USAGE: "--pulse <white> <red> <green> <blue> <hold>",
            _DESCR: "run build-in pulse effect.\n- <color> values: 0=off, 1=on\n- <hold> per step in ms: 0 - 255",
            _REGEX: r"^([01]) ([01]) ([01]) ([01]) %s$" % (_REG_255),
            _TYPES: [int, int, int, int, int]
        },
        "flash": {
            _USAGE: "--flash <white> <red> <green> <blue> <time> [<repetitions> <pause>]",
            _DESCR: "run build-in flash effect.\n- color values: 0 - 255\n- <time> in 1/100s: 0 - 255\n- <repetitions> (optional) before pause: 0 - 255\n- <pause> (optional) in 1/10s: 0 - 255",
            _REGEX: r"^%s %s %s %s %s( %s %s)?" % (_REG_255, _REG_255, _REG_255, _REG_255, _REG_255, _REG_255, _REG_255),
            _TYPES: [int, int, int, int, int, int, int]
        },
        "rainbow": {
            _USAGE: "--rainbow <hold>",
            _DESCR: "run build-in rainbow effect.\n- <hold> per step in ms: 0 - 255",
            _REGEX: r"^%s$" % (_REG_255),
            _TYPES: [int]
        },
        "candle": {
            _USAGE: "--candle <white> <red> <green> <blue>",
            _DESCR: "run build-in candle effect.\n- color values: 0 - 255",
            _REGEX: r"^%s %s %s %s$" % (_REG_255, _REG_255, _REG_255, _REG_255),
            _TYPES: [int, int, int, int]
        },
        "disco": {
            _USAGE: "--disco <hold>",
            _DESCR: "run build-in disco effect.\n- <hold> in 1/100s: 0 - 255",
            _REGEX: r"^%s$" % (_REG_255),
            _TYPES: [int]
        },
        "hold": {
            _USAGE: "--hold <hold> [<repetitions> <pause>]",
            _DESCR: "change hold value of current effect.\n- <repetitions> (optional) before pause: 0 - 255\n- <pause> (optional) in 1/10s: 0 - 255",
            _REGEX: r"^%s( %s %s)?" % (_REG_255, _REG_255, _REG_255),
            _TYPES: [int, int, int]
        },
        "halt": {
            _USAGE: "--halt",
            _DESCR: "halt build-in effect, keeps color",
            _REGEX: None,
            _TYPES: None
        },
        "timer": {
            _USAGE: "--timer [<n:1-4> <start> <minutes> [<white> <red> <green> <blue>]|[<n:1-4>] off]",
            _DESCR: "schedules timer\n- <timer>: No. of timer 1 - 4\n- <start>: starting time (hh:mm or in minutes)\n- <minutes>: runtime in minutes\n- (optional) color values: 0 - 255\n- [<timer>] off: deactivates single or all timers\n- <timer>: (optional) No. of timer 1 - 4\n- without parameters: request current timer settings",
            _REGEX: r"^(([1-4]) (%s|%s) %s( %s %s %s %s)?|([1-4] )?off)?$" % (_REG_1439, _REG_23COL59, _REG_255, _REG_255, _REG_255, _REG_255, _REG_255),
            _TYPES: [str, str, int, int, int, int, int]
        },
        "fade": {
            _USAGE: "--fade <minutes> <white> <red> <green> <blue>",
            _DESCR: "change color smoothly\n- <minutes>: runtime in minutes (max. 255)\n- color values: 0 - 255",
            _REGEX: r"^%s %s %s %s %s$" % (_REG_255, _REG_255, _REG_255, _REG_255, _REG_255),
            _TYPES: [int, int, int, int, int]
        },
        "ambient": {
            _USAGE: "--ambient <minutes> [<start>]",
            _DESCR: "schedules ambient program\n- <minutes>: runtime in minutes, best in steps of 15m\n- <start>: (optional) starting time (hh:mm or in minutes)",
            _REGEX: r"^(%s|%s)( (%s|%s))?$" % (_REG_1439, _REG_23COL59, _REG_1439, _REG_23COL59),
            _TYPES: [str, str]
        },
        "wakeup": {
            _USAGE: "--wakeup <minutes> [<start>]",
            _DESCR: "schedules wake-up program\n- <minutes>: runtime in minutes, best in steps of 15m\n- <start>: (optional) starting time (hh:mm or in minutes)",
            _REGEX: r"^(%s|%s)( (%s|%s))?$" % (_REG_1439, _REG_23COL59, _REG_1439, _REG_23COL59),
            _TYPES: [str, str]
        },
        "doze": {
            _USAGE: "--doze <minutes> [<start>]",
            _DESCR: "schedules doze program\n- <minutes>: runtime in minutes, best in steps of 15m\n- <start>: (optional) starting time (hh:mm or in minutes)",
            _REGEX: r"^(%s|%s)( (%s|%s))?$" % (_REG_1439, _REG_23COL59, _REG_1439, _REG_23COL59),
            _TYPES: [str, str]
        },
        "wheel": {
            _USAGE: "--wheel <bgr|grb|rbg> <minutes> [<start>] [<brightness>]",
            _DESCR: "schedules a program running through color wheel\n- <minutes>: runtime in minutes (best in steps of 4m, up to 1020m)\n- <start>: (optional) starting time (hh:mm or in minutes)\n- <brightness>: 0 - 255 (default: 255)",
            _REGEX: r"^(bgr|grb|rbg|BGR|GRB|RGB) (%s|%s|24:00|1440)( (%s|%s))?( %s)?$" % (_REG_1439, _REG_23COL59, _REG_1439, _REG_23COL59, _REG_255),
            _TYPES: [str, str, str, int]
        },
        "security": {
            _USAGE: "--security [<start> <stop> <min> <max> [<white> <red> <green> <blue>]|off]",
            _DESCR: "schedules security mode\n- <start>: starting time (hh:mm or in minutes)\n- <stop>: ending time (hh:mm or in minutes)\n- <min>: min. runtime in minutes\n- <max>: max. runtime in minutes\n- (optional) color values: 0 - 255\n- off: deactivates security mode\n- without parameters: request current security mode",
            _REGEX: r"^((%s|%s) (%s|%s) %s %s( %s %s %s %s)?|off)?$" % (_REG_1439, _REG_23COL59, _REG_1439, _REG_23COL59, _REG_255, _REG_255, _REG_255, _REG_255, _REG_255, _REG_255),
            _TYPES: [str, str, int, int, int, int, int, int]
        },
        "help": {
            _USAGE: "--help [<command>]",
            _DESCR: "prints help optionally for given command",
            _REGEX: r"^([a-z-]+)?$",
            _TYPES: None
        },
        "name": {
            _USAGE: "--name <name>",
            _DESCR: "set the name of the bulb, max. 14 characters\n- without parameters current name will be returned",
            _REGEX: r"^([0-9A-Za-z_+-]{1,19})?$",
            _TYPES: [str]
        },
        "pin": {
            _USAGE: "--pin <1234>",
            _DESCR: "set the pin for the bulb. Must be 4 digits\n- without parameters current pin will be returned",
            _REGEX: r"^([0-9]{4})?$",
            _TYPES: [str]
        },
        "sleep": {
            _USAGE: "--sleep <n>",
            _DESCR: "pause processing for n milliseconds",
            _REGEX: r"^[0-9]+$",
            _TYPES: [int]
        },
        "dump": {
            _USAGE: "--dump",
            _DESCR: "request full state of bulb",
            _REGEX: None,
            _TYPES: None
        },
        "print": {
            _USAGE: "--print",
            _DESCR: "prints collected data of bulb",
            _REGEX: None,
            _TYPES: None
        },
        "json": {
            _USAGE: "--json",
            _DESCR: "prints information in json format",
            _REGEX: None,
            _TYPES: None
        },
        "verbose": {
            _USAGE: "--verbose",
            _DESCR: "print information about processing",
            _REGEX: None,
            _TYPES: None
        },
        "log": {
            _USAGE: "--log <DEBUG|INFO|WARN|ERROR>",
            _DESCR: "set loglevel",
            _REGEX: r"^(DEBUG|INFO|WARN|ERROR)$",
            _TYPES: [str]
        },
        "reset": {
            _USAGE: "--reset",
            _DESCR: "perform factory reset",
            _REGEX: None,
            _TYPES: None
        }
    }

    def __init__(self, argv: 'list[str]') -> None:

        self.alias: Alias = Alias()
        try:

            argv.pop(0)
            if "--log" in sys.argv:
                LOGGER.level = MyLogger.LEVELS[sys.argv[sys.argv.index(
                    "--log") + 1]]

            if argv and (argv[0] == "--help" or argv[0] == "-h"):
                if len(argv) == 2:
                    print(self._build_help(
                        command=argv[1], header=True), file=sys.stderr)
                else:
                    self.print_help()

            elif argv and argv[0] == "--scan":
                self.scan()

            elif argv and argv[0] == "--aliases":
                print(str(self.alias))

            else:
                addresses, commands = self.parse_args(sys.argv)
                if addresses and len(addresses) > _MAX_BLE_CONNECTIONS:
                    raise MipowBulbException(message="Too many simultaneous connections requested, i.e. max. %i but requested %i" % (
                        _MAX_BLE_CONNECTIONS, len(addresses)))
                elif addresses and commands:
                    asyncio.run(self.process(
                        addresses=addresses, commands=commands))
                elif not addresses:
                    raise MipowBulbException(
                        message="Mac address or alias unknown")

        except MipowBulbException as e:
            LOGGER.error(e.message)

        except TimeoutError:
            LOGGER.error(
                f"TimeoutError! Maybe too many connections simultaneously?")

        except KeyboardInterrupt:
            pass

    def _build_help(self, command=None, header=False, msg="") -> None:

        s = ""

        if header == True:
            s = """Mipow Bulb bluetooth command line interface for Linux / Raspberry Pi / Windows

USAGE:   mipow.py <mac_1/alias_1> [<mac_2/alias_2>] ... --<command_1> [<param_1> <param_2> ... --<command_2> ...]
         <mac_N>   : bluetooth mac address of bulb
         <alias_N> : you can use aliases instead of mac address if there is a ~/.known_bulbs file
         <command> : a list of commands and parameters
         """

        if msg != "":
            s += "\n " + msg

        if command is not None and command in MipowBulbCLI.COMMANDS:
            s += "\n " + \
                MipowBulbCLI.COMMANDS[command][MipowBulbCLI._USAGE].ljust(32)
            for i, d in enumerate(MipowBulbCLI.COMMANDS[command][MipowBulbCLI._DESCR].split("\n")):
                s += ("\n " + (" " * 32) + d if i > 0 or len(MipowBulbCLI.COMMANDS[command]
                                                             [MipowBulbCLI._USAGE]) >= 32 else d)

        if msg != "":
            s += "\n"

        return s

    def scan(self):

        class ScanListener(Listener):

            def __init__(self) -> None:
                self._seen: 'set[BLEDevice]' = set()

            def onScanSeen(self, device: BLEDevice) -> None:
                self._seen.add(device)
                print(' %i bluetooth devices seen' %
                      len(self._seen), end='\r', file=sys.stderr)

            def onScanFound(self, device: BLEDevice) -> None:
                print(f"{device.address}     {device.name}", flush=True)

        print("MAC-Address           Bulb name", flush=True)
        asyncio.run(MipowBulbController.scan(listener=ScanListener()))

    def print_help(self):

        help = self._build_help(header=True)

        help += "\nBasic commands:"
        help += self._build_help(command="status")
        help += self._build_help(command="on")
        help += self._build_help(command="off")
        help += self._build_help(command="toggle")
        help += self._build_help(command="color")
        help += self._build_help(command="up")
        help += self._build_help(command="down")

        help += "\n\nBuild-in effects:"
        help += self._build_help(command="effect")
        help += self._build_help(command="pulse")
        help += self._build_help(command="flash")
        help += self._build_help(command="rainbow")
        help += self._build_help(command="candle")
        help += self._build_help(command="disco")
        help += self._build_help(command="hold")
        help += self._build_help(command="halt")

        help += "\n\nTimer commands:"
        help += self._build_help(command="timer")

        help += "\n\nScene commands:"
        help += self._build_help(command="fade")
        help += self._build_help(command="ambient")
        help += self._build_help(command="wakeup")
        help += self._build_help(command="doze")
        help += self._build_help(command="wheel")

        help += "\n\nSecurity commands:"
        help += self._build_help(command="security")

        help += "\n\nOther commands:"
        help += self._build_help(command="help")
        help += self._build_help(command="name")
        help += self._build_help(command="pin")
        help += self._build_help(command="sleep")
        help += self._build_help(command="dump")
        help += self._build_help(command="print")
        help += self._build_help(command="json")
        help += self._build_help(command="verbose")
        help += self._build_help(command="log")
        help += self._build_help(command="reset")

        help += "\n\nSetup commands:"
        help += self._build_help(command="scan")
        help += self._build_help(command="aliases")

        help += "\n"
        print(help, file=sys.stderr)

    def print(self, bulbs: 'list[MipowBulb]', json_: bool = False) -> None:

        if json_:
            print(json.dumps([b.to_dict() for b in bulbs], indent=2))
            return

        s = list()
        for b in bulbs:
            s.append("-" * 47)
            s.append("Device mac:                   %s" % b.address)
            s.append("Device name:                  %s" % (b.name or "n/a"))
            s.append("Alias:                        %s" % (
                self.alias.aliases[b.address] if b.address in self.alias.aliases else "n/a"))
            s.append("")
            s.append("Device PIN:                   %s" % (b.pin or "n/a"))
            s.append("Battery level:                %s" %
                     (f"{b.batteryLevel}%" if b.batteryLevel else "n/a"))
            s.append("")
            s.append("Manufacturer:                 %s" %
                     (b.manufacturer or "n/a"))
            s.append("Serial no.:                   %s" %
                     (b.serialNumber or "n/a"))
            s.append("Hardware:                     %s" %
                     (b.hardwareRevision or "n/a"))
            s.append("Software:                     %s" %
                     (b.softwareRevision or "n/a"))
            s.append("Firmware:                     %s" %
                     (b.firmwareRevision or "n/a"))
            s.append("pnpID:                        %s" % (b.pnpId or "n/a"))
            s.append("")
            s.append("Light:                        %s" %
                     (b.color.color_str() if b.color else "n/a"))
            s.append("")
            if b.effect:
                s.append("Effect:                       %s" %
                         b.effect.type_str())
                s.append("- Light:                      %s" %
                         b.effect.color.color_str())
                s.append("- Delay:                      %i" % b.effect.delay)
                s.append("- Repititions:                %i" %
                         b.effect.repetitions)
                s.append("- Pause:                      %i" % b.effect.pause)
            else:
                s.append("Effect:                       %s" % "n/a")

            s.append("")
            if b.timers and len(b.timers.timers) > 0:
                for t in b.timers.timers:
                    if not t:
                        continue

                    s.append("\nTimer %i:                      %s" %
                             (t.id + 1, t.type_str()))
                    s.append("- Time:                       %s" %
                             (t.time_str()))
                    s.append("- Runtime:                    %s" %
                             (t.runtime_str()))
                    s.append("- Light:                      %s" %
                             (t.color.color_str()))

                s.append("")
                s.append("Time:                         %s" %
                         b.timers.time_str())

            else:
                s.append("Timers:                       %s" % "n/a")

            s.append("")
            if b.security:
                s.append("Security:                     %s" %
                         ("running" if b.security.active else "inactive"))
                s.append("- Start:                      %s" %
                         b.security.time_str(b.security.startingHour, b.security.startingMinute))
                s.append("- End:                        %s" %
                         b.security.time_str(b.security.endingHour, b.security.endingMinute))
                s.append("- min. interval:              %s" %
                         b.security.minInterval)
                s.append("- max. interval:              %s" %
                         b.security.maxInterval)
                s.append("- Light:                      %s" %
                         b.security.color.color_str())
            else:
                s.append("Security:                     %s" % "n/a")

            s.append("")

        print("\n".join(s))

    def printStatus(self, bulbs: 'list[MipowBulb]') -> None:

        s = list()
        for b in bulbs:
            s.append("-" * 47)
            s.append(f"Address:    {b.address}")
            if b.address in self.alias.aliases:
                s.append(f"Alias:      {self.alias.aliases[b.address]}\n")

            if b.effect.type == Effect.TYPE_OFF:
                s.append(f"Light:      {b.color.color_str()}")
            else:
                s.append(f"Effect:     {str(b.effect)}")

            for i, t in enumerate(b.timers.timers):
                if t is None:
                    continue

                if t.hour in [None, 0xff]:
                    continue
                if i == 0:
                    s.append("")
                s.append(
                    f"Timer {i + 1}:    {t.time_str()}, {t.color.color_str()}, {t.runtime_str()}m")

            if b.security.startingHour not in [None, 0xff]:
                s.append(f"\nSecurity:    {b.security.time_str(b.security.startingHour, b.security.startingMinute)} - {b.security.time_str(b.security.endingHour, b.security.endingMinute)}, {b.security.color.color_str()}, {b.security.minInterval} - {b.security.maxInterval}m")

        print("\n".join(s))

    def _parseTime(self, s) -> 'tuple[int, int]':

        time = s.split(":")
        if len(time) == 1:
            dt = datetime.now() + timedelta(minutes=int(time[0]))
            hour = dt.hour
            minute = dt.minute
        else:
            hour = int(time[0])
            minute = int(time[1])

        return hour, minute

    def _parseRuntime(self, s) -> int:

        runtime = s.split(":")
        if len(runtime) == 1:
            return int(runtime[0])
        else:
            return int(runtime[0]) * 60 + int(runtime[1])

    def _cutScheduleNRuntimeToMaxADay(self, startHour: int, startMinute: int, runtime: int) -> int:

        return (1440 - 60 * startHour - startMinute) if (60 * startHour + startMinute + runtime) >= 1440 else runtime

    def _then(self) -> 'tuple[int, int]':
        then = datetime.now() + timedelta(minutes=1)
        return then.hour, then.minute

    async def process(self, addresses: 'list[str]', commands: 'list[dict]') -> None:

        try:
            controller = MipowBulbController(
                addresses=addresses, listener=Listener())

            await controller.connect(timeout=10)

            for command in commands:
                if command[MipowBulbCLI._COMMAND] == "status":
                    # 8 steps
                    bulbs = await asyncio.gather(controller.requestLight(), controller.requestEffect(), controller.requestTimers(), controller.requestSecurity())
                    self.printStatus(bulbs=bulbs[0])

                elif command[MipowBulbCLI._COMMAND] == "color" and command[MipowBulbCLI._PARAMS]:

                    # 4 steps
                    color = Color(*tuple(command[MipowBulbCLI._PARAMS]))
                    await asyncio.gather(controller.setLight(color=color))

                elif command[MipowBulbCLI._COMMAND] == "color" and not command[MipowBulbCLI._PARAMS]:

                    # 4 steps
                    await asyncio.gather(controller.requestLight())

                elif command[MipowBulbCLI._COMMAND] == "on":

                    # 4 steps
                    await asyncio.gather(controller.setLight(color=Color(white=255)))

                elif command[MipowBulbCLI._COMMAND] == "off":

                    # 4 steps
                    await asyncio.gather(controller.setLight(color=Color()))

                elif command[MipowBulbCLI._COMMAND] == "toggle":

                    # 6 steps
                    await asyncio.gather(controller.toggle())

                elif command[MipowBulbCLI._COMMAND] == "up":

                    # 5 steps
                    await asyncio.gather(controller.dim(factor=2))

                elif command[MipowBulbCLI._COMMAND] == "down":

                    # 5 steps
                    await asyncio.gather(controller.dim(factor=.5))

                elif command[MipowBulbCLI._COMMAND] == "effect":

                    # 4 steps
                    await asyncio.gather(controller.requestEffect())

                elif command[MipowBulbCLI._COMMAND] == "pulse":

                    # 4 steps
                    color = Color(*tuple(command[MipowBulbCLI._PARAMS][0:4]))
                    delay = command[MipowBulbCLI._PARAMS][4]

                    effect = Effect(
                        color=color, type_=Effect.TYPE_PULSE, delay=delay)
                    await asyncio.gather(controller.setEffect(effect=effect))

                elif command[MipowBulbCLI._COMMAND] == "flash":

                    # 4 steps
                    color = Color(*tuple(command[MipowBulbCLI._PARAMS][0:4]))
                    delay = command[MipowBulbCLI._PARAMS][4]
                    repetitions = command[MipowBulbCLI._PARAMS][5] if len(
                        command[MipowBulbCLI._PARAMS]) > 5 else 0
                    pause = command[MipowBulbCLI._PARAMS][6] if len(
                        command[MipowBulbCLI._PARAMS]) > 6 else 0

                    effect = Effect(color=color, type_=Effect.TYPE_FLASH,
                                    repetitions=repetitions, delay=delay, pause=pause)
                    await asyncio.gather(controller.setEffect(effect=effect))

                elif command[MipowBulbCLI._COMMAND] == "rainbow":

                    # 4 steps
                    delay = command[MipowBulbCLI._PARAMS][0]
                    effect = Effect(type_=Effect.TYPE_RAINBOW, delay=delay)
                    await asyncio.gather(controller.setEffect(effect=effect))

                elif command[MipowBulbCLI._COMMAND] == "candle":

                    # 4 steps
                    color = Color(*tuple(command[MipowBulbCLI._PARAMS][0:4]))
                    effect = Effect(color=color, type_=Effect.TYPE_CANDLE)
                    await asyncio.gather(controller.setEffect(effect=effect))

                elif command[MipowBulbCLI._COMMAND] == "disco":

                    # 4 steps
                    delay = command[MipowBulbCLI._PARAMS][0]
                    effect = Effect(type_=Effect.TYPE_DISCO, delay=delay)
                    await asyncio.gather(controller.setEffect(effect=effect))

                elif command[MipowBulbCLI._COMMAND] == "hold":

                    # 5 steps
                    delay = command[MipowBulbCLI._PARAMS][0]
                    repetitions = command[MipowBulbCLI._PARAMS][1] if len(
                        command[MipowBulbCLI._PARAMS]) > 1 else 0
                    pause = command[MipowBulbCLI._PARAMS][2] if len(
                        command[MipowBulbCLI._PARAMS]) > 2 else 0
                    await asyncio.gather(controller.setHold(
                        delay=delay, repetitions=repetitions, pause=pause))

                elif command[MipowBulbCLI._COMMAND] == "halt":

                    # 5 steps
                    await asyncio.gather(controller.halt())

                elif command[MipowBulbCLI._COMMAND] == "timer" and not command[MipowBulbCLI._PARAMS]:

                    # 5 steps
                    await asyncio.gather(controller.requestTimers())

                elif command[MipowBulbCLI._COMMAND] == "timer" and command[MipowBulbCLI._PARAMS] == ["off"]:

                    # 7 steps
                    await asyncio.gather(controller.resetTimers(ids=[0, 1, 2, 3]))

                elif command[MipowBulbCLI._COMMAND] == "timer" and len(command[MipowBulbCLI._PARAMS]) == 2 and command[MipowBulbCLI._PARAMS][1] == "off":

                    # 4 steps
                    await asyncio.gather(controller.resetTimers(ids=[int(command[MipowBulbCLI._PARAMS][0]) - 1]))

                elif command[MipowBulbCLI._COMMAND] == "timer" and len(command[MipowBulbCLI._PARAMS]) in [3, 7]:

                    # 4 steps
                    id = int(command[MipowBulbCLI._PARAMS][0]) - 1
                    hour, minute = self._parseTime(
                        command[MipowBulbCLI._PARAMS][1])
                    runtime = int(command[MipowBulbCLI._PARAMS][2])

                    if len(command[MipowBulbCLI._PARAMS]) == 7:
                        color = Color(
                            *tuple(command[MipowBulbCLI._PARAMS][3:7]))
                    else:
                        color = Color(white=255)

                    timer = Timer(id=id, hour=hour, minute=minute,
                                  runtime=runtime, color=color)

                    await asyncio.gather(controller.setTimer(timer=timer))

                elif command[MipowBulbCLI._COMMAND] == "fade":

                    # 7 steps
                    await asyncio.gather(controller.setSceneFade(runtime=min(255, int(command[MipowBulbCLI._PARAMS][0])), color=Color(
                        *tuple(command[MipowBulbCLI._PARAMS][1:5]))))

                elif command[MipowBulbCLI._COMMAND] == "ambient":

                    # 7 steps
                    if len(command[MipowBulbCLI._PARAMS]) == 2:
                        hour, minute = self._parseTime(
                            command[MipowBulbCLI._PARAMS][1])
                    else:
                        hour, minute = self._then()

                    runtime = self._parseRuntime(
                        command[MipowBulbCLI._PARAMS][0])
                    runtime = self._cutScheduleNRuntimeToMaxADay(
                        startHour=hour, startMinute=minute, runtime=runtime)
                    await asyncio.gather(controller.setSceneAmbient(runtime=runtime, hour=hour, minute=minute))

                elif command[MipowBulbCLI._COMMAND] == "wakeup":

                    # 7 steps
                    if len(command[MipowBulbCLI._PARAMS]) == 2:
                        hour, minute = self._parseTime(
                            command[MipowBulbCLI._PARAMS][1])
                    else:
                        hour, minute = self._then()

                    runtime = self._parseRuntime(
                        command[MipowBulbCLI._PARAMS][0])

                    runtime = self._cutScheduleNRuntimeToMaxADay(
                        startHour=hour, startMinute=minute, runtime=runtime)
                    await asyncio.gather(controller.setSceneWakeup(runtime=runtime, hour=hour, minute=minute))

                elif command[MipowBulbCLI._COMMAND] == "doze":

                    # 7 steps
                    if len(command[MipowBulbCLI._PARAMS]) == 2:
                        hour, minute = self._parseTime(
                            command[MipowBulbCLI._PARAMS][1])
                    else:
                        hour, minute = self._then()

                    runtime = self._parseRuntime(
                        command[MipowBulbCLI._PARAMS][0])
                    runtime = self._cutScheduleNRuntimeToMaxADay(
                        startHour=hour, startMinute=minute, runtime=runtime)
                    await asyncio.gather(controller.setSceneDoze(runtime=runtime, hour=hour, minute=minute))

                elif command[MipowBulbCLI._COMMAND] == "wheel":

                    # 7 steps
                    if len(command[MipowBulbCLI._PARAMS]) > 2:
                        hour, minute = self._parseTime(
                            command[MipowBulbCLI._PARAMS][2])
                    else:
                        hour, minute = self._then()

                    runtime = self._parseRuntime(
                        command[MipowBulbCLI._PARAMS][1])
                    runtime = self._cutScheduleNRuntimeToMaxADay(
                        startHour=hour, startMinute=minute, runtime=runtime)

                    brightness = int(command[MipowBulbCLI._PARAMS][3]) if len(
                        command[MipowBulbCLI._PARAMS]) == 4 else 255
                    await asyncio.gather(controller.setSceneWheel(order=command[MipowBulbCLI._PARAMS][0], runtime=runtime, hour=hour, minute=minute, brightness=brightness))

                elif command[MipowBulbCLI._COMMAND] == "security" and len(command[MipowBulbCLI._PARAMS]) in [4, 8]:

                    now = datetime.now()
                    startingHour, startingMinute = self._parseTime(
                        command[MipowBulbCLI._PARAMS][0])
                    endingHour, endingMinute = self._parseTime(
                        command[MipowBulbCLI._PARAMS][1])
                    minInterval = int(command[MipowBulbCLI._PARAMS][2])
                    maxInterval = int(command[MipowBulbCLI._PARAMS][3])

                    if len(command[MipowBulbCLI._PARAMS]) == 8:
                        color = Color(
                            *tuple(command[MipowBulbCLI._PARAMS][4:8]))
                    else:
                        color = Color(white=255)

                    security = Security(
                        active=True, hour=now.hour, minute=now.minute, startingHour=startingHour, startingMinute=startingMinute, endingHour=endingHour, endingMinute=endingMinute, minInterval=minInterval, maxInterval=maxInterval, color=color)
                    await asyncio.gather(controller.setSecurity(security=security))

                elif command[MipowBulbCLI._COMMAND] == "security" and command[MipowBulbCLI._PARAMS] == ["off"]:

                    await asyncio.gather(controller.resetSecurity())

                elif command[MipowBulbCLI._COMMAND] == "security":

                    await asyncio.gather(controller.requestSecurity())

                elif command[MipowBulbCLI._COMMAND] == "name" and not command[MipowBulbCLI._PARAMS]:

                    # 4 steps
                    await asyncio.gather(controller.requestName())

                elif command[MipowBulbCLI._COMMAND] == "name":

                    # 4 steps
                    name = command[MipowBulbCLI._PARAMS][0]
                    await asyncio.gather(controller.setName(name=name))

                elif command[MipowBulbCLI._COMMAND] == "pin" and not command[MipowBulbCLI._PARAMS]:

                    # 4 steps
                    await asyncio.gather(controller.requestPin())

                elif command[MipowBulbCLI._COMMAND] == "pin":

                    # 4 steps
                    pin = command[MipowBulbCLI._PARAMS][0]
                    await asyncio.gather(controller.setPin(pin=pin))

                elif command[MipowBulbCLI._COMMAND] == "sleep":

                    await asyncio.sleep(command[MipowBulbCLI._PARAMS][0] / 1000)

                elif command[MipowBulbCLI._COMMAND] == "dump":

                    # 15 steps
                    await asyncio.gather(controller.requestDeviceInfo(), controller.requestLight(), controller.requestEffect(), controller.requestTimers(), controller.requestSecurity())

                elif command[MipowBulbCLI._COMMAND] == "reset":

                    # 4 steps
                    await asyncio.gather(controller.reset())

                elif command[MipowBulbCLI._COMMAND] == "print":

                    self.print(bulbs=controller.bulbs)

                elif command[MipowBulbCLI._COMMAND] == "json":

                    self.print(bulbs=controller.bulbs, json_=True)

        except MipowBulbException as ex:
            LOGGER.error(ex.message)

        except BleakError as ex:
            LOGGER.error(str(ex))

        finally:
            if controller:
                await controller.disconnect()

    def transform_commands(self, commands: 'list[dict]'):

        errors: 'list[str]' = list()

        for command in commands:

            cmd = command[MipowBulbCLI._COMMAND]
            if cmd not in MipowBulbCLI.COMMANDS:
                errors.append("ERROR: Unknown command <%s>" % cmd)
                continue

            cmd_def = MipowBulbCLI.COMMANDS[cmd]

            regex: str = cmd_def[MipowBulbCLI._REGEX]
            if regex and not re.match(regex, " ".join(command[MipowBulbCLI._ARGS])):
                errors.append(
                    self._build_help(cmd, False,
                                     "ERROR: Please check parameters of command\n")
                )
                continue

            if cmd_def[MipowBulbCLI._TYPES]:
                params = []
                for i, arg in enumerate(command[MipowBulbCLI._ARGS]):
                    params.append(cmd_def[MipowBulbCLI._TYPES][i](arg))

                command["params"] = params

        if len(commands) == 0:
            errors.append(
                "No commands given. Use --help in order to get help")

        if len(errors) > 0:
            raise MipowBulbException("\n".join(errors))

        return commands

    def parse_args(self, argv: 'list[str]') -> 'tuple[set[str], list[dict]]':

        addresses: 'set[str]' = set()
        commands: 'list[tuple[str, list[str]]]' = list()

        cmd_group = False
        for arg in argv:

            is_cmd = arg.startswith("--")
            cmd_group |= is_cmd
            if not cmd_group:
                _addresses = self.alias.resolve(arg)
                if _addresses:
                    for a in _addresses:
                        addresses.add(a)
                else:
                    addresses.add(arg)

            elif is_cmd:
                commands.append({
                    "command": arg[2:],
                    "args": list()
                })

            else:
                commands[-1]["args"].append(arg)

        self.transform_commands(commands)

        return addresses, commands


if __name__ == '__main__':

    MipowBulbCLI(argv=sys.argv)
