"""Constants and ioctl helpers for the ENEK5130 keyboard RGB controller"""

# Acer ENEK5130 HID RGB controller used by newer Nitro/Predator models where
# linuwu_sense exposes RGB sysfs files but color writes do not affect hardware.
ENEK5130_HID_ID = "HID_ID=0018:00000CF2:00005130"
ENEK5130_HID_NAME = "HID_NAME=ENEK5130:00 0CF2:5130"

_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS
_IOC_WRITE = 1
_IOC_READ = 2


def _IOC(direction, type_, nr, size):
    return (
        (direction << _IOC_DIRSHIFT)
        | (ord(type_) << _IOC_TYPESHIFT)
        | (nr << _IOC_NRSHIFT)
        | (size << _IOC_SIZESHIFT)
    )


def HIDIOCSFEATURE(length):
    # linux/hidraw.h: _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x06, len)
    return _IOC(_IOC_WRITE | _IOC_READ, 'H', 0x06, length)
