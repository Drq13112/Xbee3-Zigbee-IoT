# Dictionary for coordinator devices with format: 'nickname': address_bytes
COORDINATORS = {
    "COORD": b'\x00\x13\xA2\x00\x42\x3D\x8B\x99',  # Original C_ADDR
}

# Dictionary for end devices with format: 'nickname': address_bytes
DEVICES = {
    "CAMARA1": b'\x00\x13\xA2\x00\x42\x3D\x8A\xAC',  # Original D_ADDR
    "CAMARA2": b'\x00\x13\xA2\x00\x42\x3D\x8A\xAD',
    "SENSOR1": b'\x00\x13\xA2\x00\x42\x3D\x8D\x6E',
    "ROUTER1": b'\x00\x13\xA2\x00\x42\x3D\x8A\xAE',
}

# Default device identifier
DEFAULT_DID = "XBEE_TELEMANDO"

# Get coordinator address by nickname
def get_coordinator(nickname):
    return COORDINATORS.get(nickname, None)

# Get device address by nickname
def get_device(nickname):
    return DEVICES.get(nickname, None)

# Get all coordinator nicknames as a list
def get_coordinator_names():
    return list(COORDINATORS.keys())

# Get all device nicknames as a list
def get_device_names():
    return list(DEVICES.keys())

def add_device(nickname, address_bytes):
    DEVICES.update({nickname: address_bytes})
    
def add_coordinator(nickname, address_bytes):
    COORDINATORS.update({nickname: address_bytes})
    
def remove_device(nickname):
    if nickname in DEVICES:
        del DEVICES[nickname]
    
# Get default coordinator (first one)
def get_default_coordinator():
    """Get first coordinator name or None"""
    names = get_coordinator_names()
    return names[0] if names else None

def get_default_device():
    """Get first device name or None"""
    names = get_device_names()
    return names[0] if names else None