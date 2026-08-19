from blkcache.file.device import Device


def test_device_can_be_constructed():
    device = Device("/dev/null", "rb")
    assert device.path.name == "null"
