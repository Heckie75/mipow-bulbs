# A Mipow Bulb bluetooth command line interface for Linux / Raspberry Pi / Windows
Python script and lib in order to control Mipow Playbulbs via Bluetooth LE with Raspberry Pi, any Linux distribution and MS Windows.

Full-featured CLI and API based on [bleak](https://github.com/hbldh/bleak) for Mipow Playbulb. It is (should be compatible) with the following models:
* Mipow Playbulb Rainbow (BTL200), tested rev. BTL200_v7 / Application version 2.4.3.26 (no candle effect)
* Mipow Playbulb Smart (BTL201), tested rev. BTL201_v2 / Application version 2.4.3.26 (no candle effect)
* Mipow Playbulb Spot Mesh (BTL203), tested rev. BTL203M_V1.6 / Application version 2.4.5.13 (no candle effect, remembers whole state, light, effect etc. after power off!)
* Mipow Playbulb Candle (BTL300, BTL305), confirmed by other users
* MiPow Playbulb String (BTL505-GN), confirmed by other users (device does not have random- / security mode)

Not tested yet:
* MiPow Playbulb Sphere (BTL301W), untested, unconfirmed, feedback is welcome!
* MiPow Playbulb Garden (BTL400), untested, unconfirmed, feedback is welcome!
* MiPow Playbulb Comet (BTL501A), untested, unconfirmed, feedback is welcome!
* MiPow Playbulb Solar (BTL601), untested, unconfirmed, feedback is welcome!

It's NOT compatible with bulbs of series BTL1xx:
* MiPow Playbulb Lite (BTL100S)
* MiPow Playbulb Color (BTL100C)

## Command line tool
```
$ ./mipow.py --help
Mipow Bulb bluetooth command line interface for Linux / Raspberry Pi / Windows

USAGE:   mipow.py <mac_1/alias_1> [<mac_2/alias_2>] ... --<command_1> [<param_1> <param_2> ... --<command_2> ...]
         <mac_N>   : bluetooth mac address of bulb
         <alias_N> : you can use aliases instead of mac address if there is a ~/.known_bulbs file
         <command> : a list of commands and parameters

Basic commands:
 --status                        just read and print the basic information of the bulb
 --on                            turn bulb on
 --off                           turn bulb off
 --toggle                        turn off / on (remembers color!)
 --color [<white> <red> <green> <blue>]
                                 set color
                                 - <color> each value 0 - 255
                                 - without parameters current color will be returned
 --up                            turn up light
 --down                          dim light

Build-in effects:
 --effect                        request current effect of bulb
 --pulse <white> <red> <green> <blue> <hold>
                                 run build-in pulse effect.
                                 - <color> values: 0=off, 1=on
                                 - <hold> per step in ms: 0 - 255
 --flash <white> <red> <green> <blue> <time> [<repetitions> <pause>]
                                 run build-in flash effect.
                                 - color values: 0 - 255
                                 - <time> in 1/100s: 0 - 255
                                 - <repetitions> (optional) before pause: 0 - 255
                                 - <pause> (optional) in 1/10s: 0 - 255
 --rainbow <hold>                run build-in rainbow effect.
                                 - <hold> per step in ms: 0 - 255
 --candle <white> <red> <green> <blue>
                                 run build-in candle effect.
                                 - color values: 0 - 255
 --disco <hold>                  run build-in disco effect.
                                 - <hold> in 1/100s: 0 - 255
 --hold <hold> [<repetitions> <pause>]
                                 change hold value of current effect.
                                 - <repetitions> (optional) before pause: 0 - 255
                                 - <pause> (optional) in 1/10s: 0 - 255
 --halt                          halt build-in effect, keeps color

Timer commands:
 --timer [<n:1-4> <start> <minutes> [<white> <red> <green> <blue>]|[<n:1-4>] off]
                                 schedules timer
                                 - <timer>: No. of timer 1 - 4
                                 - <start>: starting time (hh:mm or in minutes)
                                 - <minutes>: runtime in minutes
                                 - (optional) color values: 0 - 255
                                 - [<timer>] off: deactivates single or all timers
                                 - <timer>: (optional) No. of timer 1 - 4
                                 - without parameters: request current timer settings

Scene commands:
 --fade <minutes> <white> <red> <green> <blue>
                                 change color smoothly
                                 - <minutes>: runtime in minutes (max. 255)
                                 - color values: 0 - 255
 --ambient <minutes> [<start>]   schedules ambient program
                                 - <minutes>: runtime in minutes, best in steps of 15m
                                 - <start>: (optional) starting time (hh:mm or in minutes)
 --wakeup <minutes> [<start>]    schedules wake-up program
                                 - <minutes>: runtime in minutes, best in steps of 15m
                                 - <start>: (optional) starting time (hh:mm or in minutes)
 --doze <minutes> [<start>]      schedules doze program
                                 - <minutes>: runtime in minutes, best in steps of 15m
                                 - <start>: (optional) starting time (hh:mm or in minutes)
 --wheel <bgr|grb|rbg> <minutes> [<start>] [<brightness>]
                                 schedules a program running through color wheel
                                 - <minutes>: runtime in minutes (best in steps of 4m, up to 1020m)
                                 - <start>: (optional) starting time (hh:mm or in minutes)
                                 - <brightness>: 0 - 255 (default: 255)

Security commands:
 --security [<start> <stop> <min> <max> [<white> <red> <green> <blue>]|off]
                                 schedules security mode
                                 - <start>: starting time (hh:mm or in minutes)
                                 - <stop>: ending time (hh:mm or in minutes)
                                 - <min>: min. runtime in minutes
                                 - <max>: max. runtime in minutes
                                 - (optional) color values: 0 - 255
                                 - off: deactivates security mode
                                 - without parameters: request current security mode

Other commands:
 --help [<command>]              prints help optionally for given command
 --name <name>                   set the name of the bulb, max. 14 characters
                                 - without parameters current name will be returned
 --pin <1234>                    set the pin for the bulb. Must be 4 digits
                                 - without parameters current pin will be returned
 --sleep <n>                     pause processing for n milliseconds
 --dump                          request full state of bulb
 --print                         prints collected data of bulb
 --json                          prints information in json format
 --verbose                       print information about processing
 --log <DEBUG|INFO|WARN|ERROR>   set loglevel
 --reset                         perform factory reset

Setup commands:
 --scan                          scan for Mipow bulbs
 --aliases                       print known aliases from .known_bulbs file
```

## Preparation / Preconditions
The CLI / API is written in Python 3. It utilizes the Python module [bleak](https://github.com/hbldh/bleak) which can be installed as follows:

```
$ pip3 install bleak
```

Make sure that script is executable:
```
$ chmod +x mipow.py
```
## Give bulb a new name
In order to be able to distinguish multiple bulbs you should rename your bulb. 

```
$ ./mipow.py AF:66:4B:0D:AC:E6 --name Livingroom
```

## Find bulbs and adding aliases
First of all you should scan for Mipow Playbulbs. This can be done by calling the scan command:
```
$ ./mipow.py --scan
MAC-Address           Bulb name
AF:66:4B:0D:AC:E6     Schlafzimmer
6A:B1:4B:0F:AC:E6     Flur
6A:9C:4B:0F:AC:E6     Wohnzimmer
A9:D5:4B:0D:AC:E6     Bad
6D:70:4B:0F:AC:E6     Lampe Rechts
6F:CB:4B:0F:AC:E6     Lampe Links
6A:3D:4B:0F:AC:E6     Kueche
```

You can call the script by using the Bluetooth address:
```
$ ./mipow.py 6A:9C:4B:0F:AC:E6 --status
-----------------------------------------------
Address:    6A:9C:4B:0F:AC:E6
Alias:      Wohnzimmer|WZ|LRWFK

Light:      WRGB(255,0,0,0)
```

Since this isn't very handy it is recommended to create a file in your home directory called ```.known_bulbs```. My file looks as follows:
```
$ cat ~/.known_bulbs 
6A:9C:4B:0F:AC:E6 Wohnzimmer|WZ|LRWFK
6D:70:4B:0F:AC:E6 Lampe Links|WZ|LRWFK
6F:CB:4B:0F:AC:E6 Lampe Rechts|WZ|LRWFK
AF:66:4B:0D:AC:E6 Schlafzimmer|SFKB
6A:B1:4B:0F:AC:E6 Flur|SFKB|LRWFK
6A:3D:4B:0F:AC:E6 Kueche|SFKB|LRWFK
A9:D5:4B:0D:AC:E6 Bad|SFKB
```

This allows me to call the script by using an alias, e.g.
```
$ ./mipow.py Wohnz --status
-----------------------------------------------
Address:    6A:9C:4B:0F:AC:E6
Alias:      Wohnzimmer|WZ|LRWFK

Light:      WRGB(255,0,0,0)
```

Note, that I have just written ```Wohnz``` instead of the fullname. The alias is like a pattern. Every line that matches in ```.known_bulbs``` will be connected. This allows also to build groups. The following command line will be performed for 3 devices at once caused by the alias set:
```
$ ./mipow.py WZ --status
-----------------------------------------------
Address:    6F:CB:4B:0F:AC:E6
Alias:      Lampe Rechts|WZ|LRWFK

Light:      WRGB(255,0,0,0)
-----------------------------------------------
Address:    6A:9C:4B:0F:AC:E6
Alias:      Wohnzimmer|WZ|LRWFK

Light:      WRGB(255,0,0,0)
-----------------------------------------------
Address:    6D:70:4B:0F:AC:E6
Alias:      Lampe Links|WZ|LRWFK

Light:      WRGB(255,0,0,0)
```

## Multiple devices and command queueing
Connections to multiple devices are supported. In addition you can send multiple commands by queueing these commands.

Example:
```
$ ./mipow.py Wohnzimmer Kueche Bad --on --sleep 5000 --off
```

This commands connects to three bulbs, i.e. 'Wohnzimmer', 'Kueche' and 'Bad'. Then it sends three commands:
1. Turn on these three bulbs
2. Wait 5000ms
3. Turn on these three bulbs

## Basic commands
### Ask for help
Type the following in order to get help for all commands 
``` 
$ ./mipow.py --help
...
```

In order to get help for just one command you can do it like this:
```
$ ./mipow.py --help color
Mipow Bulb bluetooth command line interface for Linux / Raspberry Pi / Windows

USAGE:   mipow.py <mac_1/alias_1> [<mac_2/alias_2>] ... --<command_1> [<param_1> <param_2> ... --<command_2> ...]
         <mac_N>   : bluetooth mac address of bulb
         <alias_N> : you can use aliases instead of mac address if there is a ~/.known_bulbs file
         <command> : a list of commands and parameters

 --color [<white> <red> <green> <blue>]
                                 set color
                                 - <color> each value 0 - 255
                                 - without parameters current color will be returned
```

### Print status
To print the status you can use the ```--status```-command. It directly prints some basic information like 'mac-address', *alias*, currect color and effect, scheduled timers and security mode. 

```
$ ./mipow.py Wohnzimer --status
-----------------------------------------------
Address:    6A:9C:4B:0F:AC:E6
Alias:      Wohnzimmer|WZ|LRWFK

Effect:     Effect(type=rainbow, color=Color(white=0, red=158, green=255, blue=0), repetitions=0, delay=255, pause=255)

Timer 1:    22:00, WRGB(0,0,0,255), 01:00m
Timer 2:    23:00, WRGB(0,0,255,0), 01:00m
Timer 3:    00:00, WRGB(0,255,0,0), 01:00m
Timer 4:    01:00, off, 01:00m

Security:    06:00 - 10:00, WRGB(255,0,0,0), 6 - 20m
```

### Queueing commands / sleep command

Since it takes some time to establish the bluetooth connection each time you start the script, I have introduced command queuing. Each command starts with a double-dash. The _sleep_ command pauses processing before the next command starts. 

```
$ ./mipow.py Kueche --off --sleep 1000 --on --sleep 500 --off --sleep 250 --on --sleep 100 --off
```

### Set color
The color of the light will be set by passing 4 values for white, red, green and blue light. The values must be between 0 and 255.

Example:
```
$ ./mipow.py Kuech --color 0 0 255 0
```
The light is set to green.

### Turn on, turn off and toggle

Turn the light on and off:
```
$ ./mipow.py Kuech --on
$ ./mipow.py Kuech --off
```

You can also toggle which means that if the bulb is turned on at this moment it will be turned off and vice versa. 

Example:
```
$ ./mipow.py Kuech --color 0 255 0 0
$ ./mipow.py Kuech --toggle
$ ./mipow.py Kuech --toggle
```

In first step bulb is turned on. Color is red. In second step the bulb is turned off by utilizing the toggle command. In last step the bulb is turned on by using the toggle command again. The color is red again! 

### Up and down
You can dim the light by using the ```down```-command. All values will be set to 50% of the previous values.

You can turn up the light by using the ```up```-command. All values will be set to 200% of the previous values.

Example:
```
$ ./mipow.py Kuech --color 0 255 255 0 --down --status --sleep 5 --up --status
-----------------------------------------------
Address:    6A:3D:4B:0F:AC:E6
Alias:      Kueche|SFKB|LRWFK

Light:      WRGB(0,127,127,0)
-----------------------------------------------
Address:    6A:3D:4B:0F:AC:E6
Alias:      Kueche|SFKB|LRWFK

Light:      WRGB(0,254,254,0)
```

In first step color is set to yellow and immediately dimmed. Therefore the color is 50%, i.e. 127. After five seconds light is turned up again. Values are 254. Note that caused by rounding values haven't their initial values of 255. 

### Request current color
To request the current light simple call ```--color``` without any values. 

**Note:** This request just requests the current color but does not print anything. In order to print all gathered information use the ```--print```-command as well.

```
$ ./mipow.py Kuech --color --print
-----------------------------------------------
Device mac:                   6A:3D:4B:0F:AC:E6
Device name:                  n/a
Alias:                        Kueche|SFKB|LRWFK

Device PIN:                   n/a
Battery level:                n/a

Manufacturer:                 n/a
Vendor:                       n/a
Serial no.:                   n/a
Hardware:                     n/a
Software:                     n/a
Firmware:                     n/a
pnpID:                        n/a

Light:                        WRGB(0,254,254,0)

Effect:                       n/a

Timers:                       n/a

Security:                     n/a
```

Since the only gathered information was the color, the values of all other properties of the bulb are empty (not available).

## Effect commands

The Mipow Playbulbs have build-in effect, i.e.
- Pulse
- Flash
- Rainbow
- Candle
- Disco

Example:
```
$ ./mipow.py AF:66:4B:0D:AC:E6 --pulse 10 0 0 0 0
$ ./mipow.py AF:66:4B:0D:AC:E6 --blink 20 20 0 0 0
$ ./mipow.py AF:66:4B:0D:AC:E6 --rainbow 20
$ ./mipow.py AF:66:4B:0D:AC:E6 --disco 30
$ ./mipow.py AF:66:4B:0D:AC:E6 --hold 100
```

## Timers commands
### Timers 
```
$ ./mipow.py AF:66:4B:0D:AC:E6 --timer 1 22:40 10 0 0 255 255
$ ./mipow.py AF:66:4B:0D:AC:E6 --timer 1 off
$ ./mipow.py AF:66:4B:0D:AC:E6 --timer 2 22 1 0 0 255 255
$ ./mipow.py AF:66:4B:0D:AC:E6 --timer off
```

## Scenes 
```
$ ./mipow.py AF:66:4B:0D:AC:E6 --wakeup 8
$ ./mipow.py AF:66:4B:0D:AC:E6 --doze 60
$ ./mipow.py AF:66:4B:0D:AC:E6 --bgr 60 0 64
```

## Security 
```
$ ./mipow.py AF:66:4B:0D:AC:E6 --security 22:45 23:50 1 1 255 0 0 0
$ ./mipow.py AF:66:4B:0D:AC:E6 --security off
```

## Device information
### Dump full state of your bulb

```
$ ./mipow.py Kueche --dump --print
WARN    [org.bluez.Error.NotPermitted] Read not permitted
-----------------------------------------------
Device mac:                   6A:3D:4B:0F:AC:E6
Device name:                  Kueche
Alias:                        Kueche|SFKB|LRFK

Device PIN:                   n/a
Battery level:                n/a

Manufacturer:                 Mipow Limited
Serial no.:                   BTL201
Hardware:                     CSR101x A05
Software:                     Application version 2.4.3.26
Firmware:                     BTL201_v2
pnpID:                        pnpId(vendorIDSource=1,vendorID=0xa00,productID=0x4c01,productVersion=0x1)

Light:                        WRGB(0,49,47,0)

Effect:                       off
- Light:                      off
- Delay:                      0
- Repititions:                0
- Pause:                      0


Timer 1:                      off
- Time:                       --:--
- Runtime:                    00:00
- Light:                      off

Timer 2:                      off
- Time:                       --:--
- Runtime:                    00:00
- Light:                      off

Timer 3:                      wakeup
- Time:                       --:--
- Runtime:                    01:20
- Light:                      WRGB(0,255,47,0)

Timer 4:                      doze
- Time:                       22:15
- Runtime:                    00:40
- Light:                      off

Time:                         21:10

Security:                     running
- Start:                      --:--
- End:                        --:--
- min. interval:              0
- max. interval:              0
- Light:                      off
```

Or in json format

```
$ mipow Kueche --dump --json
WARN    [org.bluez.Error.NotPermitted] Read not permitted
[
  {
    "address": "6A:3D:4B:0F:AC:E6",
    "name": "Kueche",
    "serialNumber": "BTL201",
    "pin": null,
    "batteryLevel": null,
    "firmwareRevision": "BTL201_v2",
    "hardwareRevision": "CSR101x A05",
    "softwareRevision": "Application version 2.4.3.26",
    "manufacturer": "Mipow Limited",
    "pnpId": "pnpId(vendorIDSource=1,vendorID=0xa00,productID=0x4c01,productVersion=0x1)",
    "color": {
      "white": 0,
      "red": 51,
      "green": 47,
      "blue": 0,
      "color_str": "WRGB(0,51,47,0)"
    },
    "effect": {
      "color": {
        "white": 0,
        "red": 0,
        "green": 0,
        "blue": 0,
        "color_str": "off"
      },
      "type": 255,
      "type_str": "off",
      "repetitions": 0,
      "delay": 0,
      "pause": 0
    },
    "timers": {
      "hour": 21,
      "minute": 10,
      "time_str": "21:10",
      "timers": [
        {
          "id": 0,
          "type": 4,
          "type_str": "off",
          "hour": 255,
          "minute": 255,
          "time_str": "--:--",
          "runtime": 0,
          "runtime_str": "00:00",
          "color": {
            "white": 0,
            "red": 0,
            "green": 0,
            "blue": 0,
            "color_str": "off"
          }
        },
        {
          "id": 1,
          "type": 4,
          "type_str": "off",
          "hour": 255,
          "minute": 255,
          "time_str": "--:--",
          "runtime": 0,
          "runtime_str": "00:00",
          "color": {
            "white": 0,
            "red": 0,
            "green": 0,
            "blue": 0,
            "color_str": "off"
          }
        },
        {
          "id": 2,
          "type": 0,
          "type_str": "wakeup",
          "hour": 255,
          "minute": 255,
          "time_str": "--:--",
          "runtime": 80,
          "runtime_str": "01:20",
          "color": {
            "white": 0,
            "red": 255,
            "green": 47,
            "blue": 0,
            "color_str": "WRGB(0,255,47,0)"
          }
        },
        {
          "id": 3,
          "type": 2,
          "type_str": "doze",
          "hour": 22,
          "minute": 15,
          "time_str": "22:15",
          "runtime": 40,
          "runtime_str": "00:40",
          "color": {
            "white": 0,
            "red": 0,
            "green": 0,
            "blue": 0,
            "color_str": "off"
          }
        }
      ]
    },
    "security": {
      "hour": 10,
      "minute": 21,
      "time_str": "10:21",
      "startingHour": 255,
      "startingMinute": 255,
      "start_str": "--:--",
      "endingHour": 255,
      "endingMinute": 255,
      "end_str": "--:--",
      "minInterval": 0,
      "maxInterval": 0,
      "color": {
        "white": 0,
        "red": 0,
        "green": 0,
        "blue": 0,
        "color_str": "off"
      }
    }
  }
]
```

## Mipow Playbulb Bluetooth API
see [mipow-playbulb-btl201-bt-api.md](https://github.com/Heckie75/mipow-bulbs/blob/main/mipow-playbulb-btl201-bt-api.md)